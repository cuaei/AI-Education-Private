"""Java 綜合實作與商店模擬實習：上傳校驗、隔離檢查、計次、評分與按需 AI 解釋。

設計邊界：
- 學生上傳內容永遠不在主服務程序執行；只以 Docker、無網路、唯讀掛載、資源限制的容器檢查。
- 有效檢查才計次；容器不可用、逾時等環境問題不計次。
- 客觀通過條件全部由程式檢查決定；AI 只解釋結果、評分設計說明，不改成績。
"""
import hashlib
import io
from io import BytesIO
from pathlib import Path
import json
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
import time
import zipfile
from zipfile import ZIP_DEFLATED, ZipFile
from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from .agent import run_agent
from .engineering_runner import docker, flags, safe_log
from .java_route import china_day, reserve_ai_quota

ROOT = Path(__file__).resolve().parents[1]
PRACTICE_DIR = ROOT / 'training' / 'java-practice'
SHOP_DIR = ROOT / 'training' / 'java-shop'
IMAGE = 'course-platform-java:2026.11.5'
SHOP_TASKS = ['shop-products', 'shop-orders-create', 'shop-orders-list']
SCOPES = {
    'practice': {'title': '綜合實作：比賽報名系統', 'course': PRACTICE_DIR, 'required': {'src/competition/RegistrationService.java', 'test/competition/RegistrationServiceTest.java'}, 'suffixes': {'.java', '.md'}, 'task': None},
    'shop-products': {'title': '模擬實習 · 查詢商品', 'course': SHOP_DIR, 'required': {'src/shop/ShopService.java', 'src/shop/ShopServer.java'}, 'suffixes': {'.java', '.md', '.html', '.css', '.js'}, 'task': 'products'},
    'shop-orders-create': {'title': '模擬實習 · 建立訂單', 'course': SHOP_DIR, 'required': {'src/shop/ShopService.java', 'src/shop/ShopServer.java'}, 'suffixes': {'.java', '.md', '.html', '.css', '.js'}, 'task': 'orders-create'},
    'shop-orders-list': {'title': '模擬實習 · 查看訂單', 'course': SHOP_DIR, 'required': {'src/shop/ShopService.java', 'src/shop/ShopServer.java'}, 'suffixes': {'.java', '.md', '.html', '.css', '.js'}, 'task': 'orders-list'},
}
FIXED_FILES = {'src/competition/Competition.java', 'src/competition/Registration.java',
               'src/competition/CompetitionRepository.java', 'src/competition/RegistrationException.java',
               'src/shop/Product.java', 'src/shop/Order.java', 'src/shop/ShopRepository.java',
               'src/shop/ShopException.java', 'src/shop/Json.java', 'src/shop/ShopServer.java'}
RESERVED_NAMES = {'CoreChecks.java', 'Json.java', 'PracticeHarness.java', 'ShopChecks.java', 'ShopHarness.java'}
MAX_ATTEMPTS = 3
PRACTICE_MAX = 85  # 核心 45＋學生測試 20＋結構 20；設計解釋 15 另計
DESIGN_MAX = 15


def initial_scope():
    return {'submissions': [], 'checks': [], 'resets': [], 'design': {}}


_runtime_cache = {'at': 0.0, 'value': None}


def runtime_status():
    """快取 30 秒，避免每次開頁都呼叫 Docker；檢查前會重新確認。"""
    now = time.monotonic()
    if _runtime_cache['value'] and now - _runtime_cache['at'] < 30:
        return _runtime_cache['value']
    try:
        result = docker(['image', 'inspect', IMAGE], 20)
        if result.returncode == 0:
            value = {'available': True, 'image': IMAGE, 'reason': ''}
        else:
            value = {'available': False, 'image': IMAGE, 'reason': 'Java 檢查鏡像尚未建立，請在本機執行 scripts/setup-java.ps1。'}
    except (OSError, subprocess.TimeoutExpired):
        value = {'available': False, 'image': IMAGE, 'reason': 'Docker 服務不可用，請啟動 Docker Desktop 後重試。'}
    _runtime_cache.update(at=now, value=value)
    return value


def last_reset(state):
    return max([item['created'] for item in state['resets']], default=0.0)


def attempts_used(state):
    boundary = last_reset(state)
    return len([c for c in state['checks'] if c['counted'] and c['created'] > boundary])


def passed_after_reset(state):
    boundary = last_reset(state)
    return next((c for c in reversed(state['checks']) if c['counted'] and c['created'] > boundary and c['grade']['passed']), None)


def scope_summary(state, scope):
    used, passed = attempts_used(state), passed_after_reset(state)
    latest = state['checks'][-1] if state['checks'] else None
    return {'scope': scope, 'title': SCOPES[scope]['title'], 'attempts_used': used, 'attempts_left': max(0, MAX_ATTEMPTS - used),
            'locked': used >= MAX_ATTEMPTS and not passed, 'passed': bool(passed),
            'latest': latest, 'submission_count': len(state['submissions']), 'resets': len(state['resets'])}


def public_state(state):
    return {'submissions': [{'id': s['id'], 'version': s['version'], 'files': s['files'], 'created': s['created'],
                             'design_text': s.get('design_text', ''), 'has_design': bool(s.get('design_text'))}
                            for s in state['submissions']],
            'checks': state['checks'], 'design': state['design'], 'resets': state['resets'],
            'attempts_used': attempts_used(state), 'attempts_left': max(0, MAX_ATTEMPTS - attempts_used(state)),
            'max_attempts': MAX_ATTEMPTS, 'passed': bool(passed_after_reset(state)),
            'locked': attempts_used(state) >= MAX_ATTEMPTS and not passed_after_reset(state)}


def validate_archive(content, scope, folder, course_dir, data_root):
    if not content or len(content) > 2 * 1024 * 1024:
        raise HTTPException(422, '壓縮檔不得為空或超過 2MB。')
    try:
        archive = ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(422, '文件不是有效 ZIP。請壓縮整個專案資料夾，勿上傳 RAR 或單一檔案。')
    entries = [i for i in archive.infolist() if not i.is_dir()]
    if len(entries) > 120 or sum(i.file_size for i in entries) > 5 * 1024 * 1024:
        raise HTTPException(422, '展開後最多 120 個檔案、5MB。')
    names = [i.filename.replace('\\', '/') for i in entries]
    prefix = ''
    if names and not any(n in SCOPES[scope]['required'] for n in names):
        first = names[0].split('/')[0]
        if all(n.startswith(first + '/') for n in names):
            prefix = first + '/'
    files, seen = {}, set()
    for info, name in zip(entries, names):
        path = Path(name)
        if name.startswith('/') or '..' in path.parts or ':' in name or '\x00' in name or any(p.startswith('.') for p in path.parts):
            raise HTTPException(422, '壓縮檔包含不允許的路徑：' + name[:100])
        if stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG):
            raise HTTPException(422, '壓縮檔只接受普通檔案，不接受連結。')
        relative = name[len(prefix):] if prefix and name.startswith(prefix) else name
        relative = relative.lstrip('/')
        if not relative:
            continue
        if path.suffix.lower() not in SCOPES[scope]['suffixes']:
            raise HTTPException(422, '不支援的檔案類型：' + relative[:100])
        if relative.casefold() in seen:
            raise HTTPException(422, '壓縮檔存在重複或大小寫衝突路徑：' + relative)
        seen.add(relative.casefold())
        try:
            text = archive.read(info).decode('utf-8-sig')
        except (UnicodeError, RuntimeError):
            raise HTTPException(422, '原始碼必須是 UTF-8，且 ZIP 不可加密：' + relative[:100])
        # 平台檢查器位於預設套件；只禁止學生在預設套件冒用同名類別，套件內的正常檔案不受影響。
        if path.name in RESERVED_NAMES and not re.search(r'(?m)^\s*package\s+', text):
            raise HTTPException(422, '不可使用平台保留的檔名：' + relative[:100])
        files[relative] = text
    missing = SCOPES[scope]['required'] - set(files)
    if missing:
        raise HTTPException(422, '缺少必需檔案：' + '、'.join(sorted(missing)))
    for name in FIXED_FILES & set(files):
        original = (course_dir / 'starter' / name)
        if original.exists() and hashlib.sha256(original.read_text(encoding='utf-8').encode()).hexdigest() != \
                hashlib.sha256(files[name].encode()).hexdigest():
            raise HTTPException(422, '課程提供的固定檔案不可修改：' + name)
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    try:
        safe_root = data_root.resolve(strict=True)
        if data_root.is_symlink() or not safe_root.is_dir():
            raise ValueError('提交数据根目录不是安全目录。')
        if folder.exists() or folder.is_symlink():
            raise FileExistsError('提交目录已存在，拒绝复用。')
        safe_folder = folder.resolve(strict=False)
        if not safe_folder.is_relative_to(safe_root):
            raise ValueError('提交目录超出安全数据根目录。')
        folder.parent.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as error:
        raise HTTPException(409, '提交目录已存在或不在安全数据目录内。') from error
    folder.mkdir(mode=0o755)
    for name, text in files.items():
        destination = (folder / name).resolve()
        if not destination.is_relative_to(folder.resolve()):
            raise HTTPException(422, '原始碼路徑越界。')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding='utf-8', newline='\n')
        # 检查容器固定使用 UID 10001，并以只读方式挂载提交目录。
        # 某些云环境的 umask 会把新文件建成 0600，导致容器无法读取，
        # 进而把正确代码误报成编译失败。提交内容不需要写权限或执行权限。
        try:
            destination.chmod(0o644)
            parent = destination.parent
            while parent != folder.parent:
                parent.chmod(0o755)
                parent = parent.parent
        except OSError as error:
            raise HTTPException(503, '无法准备隔离检查所需的提交文件权限。') from error
    try:
        folder.chmod(0o755)
    except OSError as error:
        raise HTTPException(503, '无法准备隔离检查所需的提交目录权限。') from error
    return digest, sorted(files)


def _copy_bundle(source, target, relative_paths):
    """Build a minimal read-only checker bundle; never mount the whole course tree."""
    for relative in relative_paths:
        src = source / relative
        dst = target / relative
        if src.is_dir():
            shutil.copytree(src, dst)
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        else:
            raise FileNotFoundError(str(src))


def checker_bundle(scope, course):
    """Return a temporary bundle containing only files the trusted harness needs.

    The harness currently executes in the same JVM as student code, so this
    narrows data exposure but cannot make harness source unreadable to that JVM.
    A separate trusted/untrusted process boundary is still required for that.
    """
    bundle = tempfile.TemporaryDirectory(prefix='java-checker-')
    root = Path(bundle.name)
    if scope == 'practice':
        paths = ('checks/run.sh', 'checks/harness', 'checks/base', 'checks/faults', 'starter/src')
    else:
        paths = ('checks/run.sh', 'checks/harness')
    _copy_bundle(course, root, paths)
    # The managed checkout can carry restrictive source modes. The bundle is
    # disposable and read-only mounted, so expose only its copied files to the
    # container UID; never chmod the source course tree.
    for path in root.rglob('*'):
        path.chmod(0o755 if path.is_dir() else 0o644)
    root.chmod(0o755)
    (root / 'checks' / 'run.sh').chmod(0o755)
    return bundle, root


def run_check(scope, folder):
    """回傳 (status, payload)；status 為 completed / environment_failed / timeout。"""
    status = runtime_status()
    if not status['available']:
        return 'environment_failed', {'message': status['reason']}
    course = SCOPES[scope]['course']
    name = 'java-check-' + secrets.token_hex(5)
    started = time.monotonic()
    try:
        bundle_lifetime, bundle = checker_bundle(scope, course)
        try:
            command = ['run', '--rm', '--name', name, *flags('600m'), '--network', 'none',
                       '--mount', f'type=bind,source={Path(folder).resolve()},target=/submission,readonly',
                       '--mount', f'type=bind,source={bundle.resolve()},target=/course,readonly',
                       '-e', 'HOME=/tmp', IMAGE, 'sh', '/course/checks/run.sh']
            if SCOPES[scope]['task']:
                command.append(SCOPES[scope]['task'])
            result = docker(command, 240)
        finally:
            bundle_lifetime.cleanup()
    except subprocess.TimeoutExpired:
        try:
            docker(['rm', '-f', name], 10)
        except Exception:
            pass
        return 'timeout', {'message': '檢查超過時限，環境可能繁忙；本次不計次。'}
    except OSError as error:
        return 'environment_failed', {'message': safe_log(str(error))}
    output = (result.stdout or '') + (result.stderr or '')
    line = output.strip().splitlines()[-1] if output.strip() else ''
    try:
        payload = json.loads(line)
    except ValueError:
        return 'environment_failed', {'message': '未取得可信檢查結果。' + safe_log(output[-800:])}
    if payload.get('environment_error'):
        return 'environment_failed', {'message': payload['environment_error']}
    if result.returncode != 0 or payload.get('status') != 'completed':
        return 'environment_failed', {'message': '檢查容器未正常結束。' + safe_log(output[-600:])}
    return 'completed', {'checks': payload['checks'], 'elapsed_ms': round((time.monotonic() - started) * 1000)}


def grade_practice(checks, design):
    """設計解釋必須完成評分（0 分也有效）才可能通過；未評分時一律不通過。"""
    score = sum(c['weight'] for c in checks if c['passed'])
    core = [c for c in checks if c['dimension'] == 'core']
    tests = [c for c in checks if c['dimension'] == 'student_tests']
    necessary = bool(core) and all(c['passed'] for c in core) and bool(tests) and all(c['passed'] for c in tests)
    graded = design is not None
    design_score = design['score'] if graded else None
    total = score + (design_score if graded else 0)
    passed = necessary and graded and total >= 70
    reason = []
    if not all(c['passed'] for c in core):
        reason.append('核心功能未全部通過')
    if not all(c['passed'] for c in tests):
        reason.append('你自己的測試未達成必要條件')
    if not graded:
        reason.append('設計解釋尚未評分（0/15 待評分）')
    elif total < 70:
        reason.append(f'總分 {total}/100 未達 70')
    message = '通過綜合實作檢查。' if passed else '；'.join(reason) + '。'
    return {'score': score, 'max_score': PRACTICE_MAX, 'objective_score': score,
            'design_score': design_score, 'design_max': DESIGN_MAX, 'design_graded': graded,
            'total': total, 'necessary': necessary, 'passed': passed,
            'checks': checks, 'source': 'runtime', 'message': message,
            'design_pending': not graded}


def save_design_record(state, submission_id, record):
    """同一提交可重新評分；最新一次生效，先前的評分保存在 history。"""
    previous = state['design'].get(submission_id)
    history = list(previous.get('history') or []) if previous else []
    if previous:
        history.append({k: v for k, v in previous.items() if k != 'history'})
    record['history'] = history
    state['design'][submission_id] = record


def apply_design_scores(state, submission_id):
    """重算該提交最新一次有效檢查；已通過紀錄保留，不追溯撤銷。"""
    design = state['design'].get(submission_id)
    latest = next((record for record in reversed(state['checks'])
                   if record.get('counted') and record.get('submission_id') == submission_id and record.get('grade')), None)
    if latest and not latest['grade'].get('passed'):
        latest['grade'] = grade_practice(latest['grade'].get('checks', []), design)


def grade_shop(checks):
    passed = bool(checks) and all(c['passed'] for c in checks)
    return {'score': sum(1 for c in checks if c['passed']), 'max_score': len(checks), 'passed': passed,
            'checks': checks, 'source': 'runtime',
            'message': '本項工作檢查通過。' if passed else '本項工作尚有未通過的檢查。'}


def mount_java_course(app, store, student, founder, teacher):
    with store.connect() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS java_work_states(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            scope TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(user_id,scope));''')
    data_root = Path(store.path).parent / 'java'
    data_root.mkdir(parents=True, exist_ok=True)

    def load(uid, scope):
        with store.connect() as db:
            row = db.execute('SELECT body FROM java_work_states WHERE user_id=? AND scope=?', (uid, scope)).fetchone()
        state = json.loads(row['body']) if row else initial_scope()
        for key, value in initial_scope().items():
            state.setdefault(key, value)
        return state

    def save(uid, scope, state):
        with store.connect() as db:
            db.execute('INSERT INTO java_work_states VALUES(?,?,?) ON CONFLICT(user_id,scope) DO UPDATE SET body=excluded.body',
                       (uid, scope, json.dumps(state, ensure_ascii=False, allow_nan=False)))

    def require_scope(scope):
        if scope not in SCOPES:
            raise HTTPException(404, '沒有這項工作。')

    def shop_unlocked(uid):
        """模擬實習要等綜合實作通過後才開始，之後三項工作依序解鎖。"""
        if not passed_after_reset(load(uid, 'practice')):
            return {'scope': 'practice', 'index': 0}
        for index, scope in enumerate(SHOP_TASKS):
            if not passed_after_reset(load(uid, scope)):
                return {'scope': scope, 'index': index + 1}
        return {'scope': None, 'index': len(SHOP_TASKS) + 1}

    def practice_submission(state, submission_id):
        item = next((s for s in state['submissions'] if s['id'] == submission_id), None)
        if not item:
            raise HTTPException(404, '找不到這個提交版本，請重新上傳。')
        return item

    def design_summary(state):
        """教師端顯示最近一份含設計解釋的提交與目前評分狀態。"""
        latest = next((s for s in reversed(state['submissions']) if s.get('design_text')), None)
        if not latest:
            return None
        record = state['design'].get(latest['id'])
        check = next((c for c in reversed(state['checks'])
                      if c.get('counted') and c.get('submission_id') == latest['id']), None)
        grade = check.get('grade') if check else None
        return {'submission_id': latest['id'], 'version': latest['version'], 'text': latest['design_text'],
                'score': record.get('score') if record else None,
                'source': record.get('source') if record else None,
                'grader': record.get('grader') if record else None,
                'graded_at': record.get('created') if record else None,
                'history': len(record.get('history') or []) if record else 0,
                'note': record.get('note', '') if record else '',
                'check_total': grade.get('total') if grade else None,
                'check_passed': bool(grade and grade.get('passed'))}

    def save_manual_design(student_id, payload, grader):
        """教師／管理員人工評分：0–15 整數，保存評分者與歷史，重算未通過的檢查。"""
        score = payload.get('score')
        if type(score) is not int or not 0 <= score <= DESIGN_MAX:
            raise HTTPException(422, f'設計解釋分數必須是 0–{DESIGN_MAX} 的整數。')
        submission_id = str(payload.get('submission_id') or '')
        note = str(payload.get('reason') or '').strip()[:1000]
        with store.user_lock(student_id):
            state = load(student_id, 'practice')
            submission = practice_submission(state, submission_id)
            if not submission.get('design_text'):
                raise HTTPException(422, '這個版本沒有設計解釋。')
            record = {'criteria': [], 'score': score, 'source': 'manual', 'created': time.time(),
                      'grader': grader, 'note': note}
            save_design_record(state, submission_id, record)
            apply_design_scores(state, submission_id)
            save(student_id, 'practice', state)
        return {'design': state['design'][submission_id], 'summary': scope_summary(state, 'practice'),
                'state': public_state(state)}

    @app.get('/api/java/{scope}/starter')
    def starter(scope: str, current=Depends(student)):
        """下載課程起始專案；與學生提交無關，可重複下載。"""
        require_scope(scope)
        base = SCOPES[scope]['course'] / 'starter'
        if not base.is_dir():
            raise HTTPException(404, '起始專案尚未就緒。')
        output = BytesIO()
        with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
            for file in sorted(base.rglob('*')):
                if file.is_file():
                    archive.writestr(str(file.relative_to(base)).replace('\\', '/'), file.read_bytes())
        filename = 'java-practice-starter.zip' if scope == 'practice' else 'java-shop-starter.zip'
        return Response(content=output.getvalue(), media_type='application/zip',
                        headers={'Content-Disposition': f'attachment; filename="{filename}"'})

    @app.get('/api/java/course')
    def overview(current=Depends(student)):
        practice = load(current['id'], 'practice')
        shop = {scope: scope_summary(load(current['id'], scope), scope) for scope in SHOP_TASKS}
        unlock = shop_unlocked(current['id'])
        with store.connect() as db:
            row = db.execute('SELECT used FROM ai_daily_quota WHERE user_id=? AND day=?', (current['id'], china_day())).fetchone()
        return {'practice': scope_summary(practice, 'practice'), 'shop': shop, 'shop_unlocked': unlock['scope'],
                'shop_finished': unlock['scope'] is None, 'runtime': runtime_status(),
                'remaining': 10 - (row['used'] if row else 0),
                'ai_enabled': app.state.model_config.enabled}

    @app.get('/api/java/{scope}')
    def detail(scope: str, current=Depends(student)):
        require_scope(scope)
        return {'summary': scope_summary(load(current['id'], scope), scope), 'state': public_state(load(current['id'], scope)),
                'runtime': runtime_status(), 'title': SCOPES[scope]['title']}

    @app.post('/api/java/{scope}/upload')
    async def upload(scope: str, file: UploadFile = File(...), design: str = Form(''), current=Depends(student)):
        require_scope(scope)
        if scope in SHOP_TASKS and shop_unlocked(current['id'])['scope'] != scope:
            raise HTTPException(409, '請先通過前一項工作；模擬實習需要按順序完成。')
        if scope == 'practice':
            design = (design or '').strip()
            if not 200 <= len(design) <= 2000:
                raise HTTPException(422, '請填寫 200–2000 字的設計解釋。')
        content = await file.read()
        with store.user_lock(current['id']):
            state = load(current['id'], scope)
            if scope_summary(state, scope)['locked']:
                raise HTTPException(409, '已用完 3 次有效檢查，請先複習並請教師或管理員重設次數。')
            submission_id = secrets.token_hex(6)
            folder = data_root / current['id'] / scope / submission_id
            digest, files = validate_archive(content, scope, folder, SCOPES[scope]['course'], data_root)
            submission = {'id': submission_id, 'version': len(state['submissions']) + 1, 'hash': digest,
                          'archive_path': str(folder), 'files': files, 'created': time.time(),
                          'design_text': design if scope == 'practice' else ''}
            state['submissions'].append(submission)
            save(current['id'], scope, state)
            return {'submission': {k: v for k, v in submission.items() if k != 'archive_path'},
                    'summary': scope_summary(state, scope)}

    @app.post('/api/java/{scope}/check')
    def check(scope: str, payload: dict, current=Depends(student)):
        require_scope(scope)
        with store.user_lock(current['id']):
            state = load(current['id'], scope)
            if scope_summary(state, scope)['locked']:
                raise HTTPException(409, '已用完 3 次有效檢查，請先複習並請教師或管理員重設次數。')
            submission = practice_submission(state, payload.get('submission_id'))
            status, result = run_check(scope, submission['archive_path'])
            counted = status == 'completed'
            record = {'id': secrets.token_hex(6), 'submission_id': submission['id'], 'version': submission['version'],
                      'hash': submission['hash'], 'status': status, 'counted': counted, 'created': time.time(),
                      'message': result.get('message', ''),
                      'elapsed_ms': result.get('elapsed_ms')}
            if counted:
                design = state['design'].get(submission['id']) if scope == 'practice' else None
                record['grade'] = grade_practice(result['checks'], design) if scope == 'practice' else grade_shop(result['checks'])
            state['checks'].append(record)
            save(current['id'], scope, state)
            return {'check': record, 'summary': scope_summary(state, scope), 'state': public_state(state)}

    @app.post('/api/java/practice/design')
    def design_review(payload: dict, current=Depends(student)):
        if not app.state.model_config.enabled:
            raise HTTPException(503, 'AI 尚未配置；設計解釋可請教師人工評分。')
        with store.user_lock(current['id']):
            state = load(current['id'], 'practice')
            submission = practice_submission(state, payload.get('submission_id'))
            text = submission.get('design_text', '')
            if not text:
                raise HTTPException(422, '這個版本沒有設計解釋。')
            check = next((c for c in reversed(state['checks']) if c['submission_id'] == submission['id'] and c['counted']), None)
            design_id = 'design:' + submission['id']
            evidence = [design_id]
            if check:
                evidence += [f"check:{check['id']}:{c['key']}" for c in check['grade']['checks'][:12]]
            facts = {'design_text': text, 'check_summary': check['grade']['message'] if check else '尚未檢查',
                     'failed_checks': [{'key': c['key'], 'label': c['label'], 'actual': c['actual']}
                                       for c in (check['grade']['checks'] if check else []) if not c['passed']],
                     'rubric': '三項各 0–5 分，合計 15 分'}
            captured = []

            def review(args):
                criteria = args.get('criteria')
                if not isinstance(criteria, list) or len(criteria) != 3:
                    raise ValueError('需要三項評價')
                cleaned = []
                for item in criteria:
                    if not isinstance(item, dict):
                        raise ValueError('評價格式無效')
                    score = item.get('score')
                    quote = item.get('quote')
                    if type(score) is not int or not 0 <= score <= 5 or not isinstance(quote, str) or not quote.strip():
                        raise ValueError('每項需 0–5 分並摘錄學生原文')
                    if quote.strip() not in text and quote.strip()[:30] not in text:
                        raise ValueError('引文不屬於本人設計解釋')
                    if item.get('evidence_id') not in evidence:
                        raise ValueError('證據編號無效')
                    cleaned.append({'criterion': str(item.get('criterion', ''))[:60], 'score': score,
                                    'reason': str(item.get('reason', ''))[:800], 'quote': quote.strip()[:400]})
                captured.append({'criteria': cleaned, 'score': sum(c['score'] for c in cleaned),
                                 'source': 'ai', 'created': time.time()})
                return {'saved': True}

            reserve_ai_quota(store, current['id'])
            context = {'purpose': 'java_design', 'evidence_ids': evidence, 'facts': facts,
                       'policy': '只評分設計說明，不修改程式檢查結果，不聲稱已運行或已通過。'}
            result = run_agent('java_design', context, app.state.model_config, {'review_design': review})
            if result.get('status') == 'ok' and captured:
                record = captured[-1]
                record.update(source='ai', grader='ai')
                save_design_record(state, submission['id'], record)
                apply_design_scores(state, submission['id'])
                save(current['id'], 'practice', state)
            with store.connect() as db:
                row = db.execute('SELECT used FROM ai_daily_quota WHERE user_id=? AND day=?', (current['id'], china_day())).fetchone()
            return {'review': captured[-1] if captured else None, 'status': result.get('status'),
                    'message': result.get('message'), 'remaining': 10 - (row['used'] if row else 0),
                    'state': public_state(load(current['id'], 'practice'))}

    @app.post('/api/java/{scope}/explain')
    def explain(scope: str, payload: dict, current=Depends(student)):
        require_scope(scope)
        if not app.state.model_config.enabled:
            raise HTTPException(503, 'AI 尚未配置，請聯絡管理員。')
        question = str(payload.get('question') or '請解釋這次檢查的結果，以及下一步應該修改什麼。')[:1000]
        state = load(current['id'], scope)
        record = next((c for c in reversed(state['checks']) if c['id'] == payload.get('check_id')), None)
        if not record:
            raise HTTPException(404, '找不到這次檢查。')
        evidence, facts = [], {'status': record['status'], 'counted': record['counted']}
        if 'grade' in record:
            evidence = [f"check:{record['id']}:{c['key']}" for c in record['grade']['checks']]
            facts.update(score=record['grade']['score'], max_score=record['grade']['max_score'],
                         passed=record['grade']['passed'], message=record['grade']['message'],
                         checks=[{'key': c['key'], 'label': c['label'], 'passed': c['passed'],
                                  'expected': c['expected'], 'actual': c['actual']} for c in record['grade']['checks']])
        else:
            facts.update(message=record['message'], note='本次未完成檢查，不計次。')
        answers = []

        def answer(args):
            text = args.get('text')
            ids = args.get('evidence_ids')
            if not isinstance(text, str) or not 1 <= len(text) <= 4000:
                raise ValueError('回覆格式無效')
            if not isinstance(ids, list) or any(i not in evidence for i in ids):
                raise ValueError('引用無效')
            answers.append(text)
            return {'saved': True}

        reserve_ai_quota(store, current['id'])
        context = {'purpose': 'question', 'question': question, 'evidence_ids': evidence, 'facts': facts,
                   'policy': '只解釋程式實際檢查結果，不改變通過判定，不聲稱已運行未運行的檢查。'}
        result = run_agent('question', context, app.state.model_config, {'answer_question': answer})
        with store.connect() as db:
            row = db.execute('SELECT used FROM ai_daily_quota WHERE user_id=? AND day=?', (current['id'], china_day())).fetchone()
        return {'message': answers[-1] if result.get('status') == 'ok' and answers else result.get('message', 'AI 未完成回覆。'),
                'status': result.get('status'), 'remaining': 10 - (row['used'] if row else 0)}

    def reset_work(student_id, scope, actor_label):
        require_scope(scope)
        with store.user_lock(student_id):
            state = load(student_id, scope)
            used = attempts_used(state)
            if not scope_summary(state, scope)['locked']:
                raise HTTPException(409, f'目前還有 {MAX_ATTEMPTS - used} 次有效檢查，不需要重設。')
            state['resets'].append({'created': time.time(), 'actor': actor_label, 'previous_attempts': used})
            save(student_id, scope, state)
        return {'ok': True, 'summary': scope_summary(load(student_id, scope), scope)}

    @app.get('/api/teacher/java/learners')
    def teacher_learners(class_id: str, scope: str = 'all', current=Depends(teacher)):
        """教師查看本班學生的 Java 實作進度，供必要時重設檢查次數。"""
        classes = getattr(app.state, 'classrooms', None)
        if not classes:
            raise HTTPException(409, '班級功能尚未就緒。')
        item = classes.get(class_id)
        if not item or item['teacher_id'] != current['id']:
            raise HTTPException(404, '班級不存在或不屬於你。')
        wanted = SHOP_TASKS + ['practice'] if scope == 'all' else [scope]
        for name in wanted:
            require_scope(name)
        learners = []
        for member in classes.members(class_id):
            if member.get('role', 'student') != 'student':
                continue
            summaries = {name: scope_summary(load(member['id'], name), name) for name in wanted}
            learners.append({'id': member['id'], 'username': member['username'], 'scopes': summaries,
                             'design': design_summary(load(member['id'], 'practice'))})
        return {'learners': learners, 'scopes': [{'scope': name, 'title': SCOPES[name]['title']} for name in wanted],
                'max_attempts': MAX_ATTEMPTS, 'design_max': DESIGN_MAX}

    @app.get('/api/java/operator/learners')
    def operator_learners(current=Depends(founder)):
        """創業者/管理員查看所有學生的 Java 進度，供必要時重設。"""
        learners = []
        for user in store.list_users():
            if user['role'] != 'student':
                continue
            practice = load(user['id'], 'practice')
            design = design_summary(practice)
            summaries = {'practice': scope_summary(practice, 'practice'),
                         **{name: scope_summary(load(user['id'], name), name) for name in SHOP_TASKS}}
            if design or any(s['attempts_used'] or s['passed'] for s in summaries.values()):
                learners.append({'id': user['id'], 'username': user['username'], 'is_demo': bool(user['is_demo']),
                                 'scopes': summaries, 'design': design})
        return {'learners': learners, 'max_attempts': MAX_ATTEMPTS, 'design_max': DESIGN_MAX}

    @app.post('/api/java/reset')
    def founder_reset(payload: dict, current=Depends(founder)):
        return reset_work(str(payload.get('student_id')), str(payload.get('scope')), 'admin:' + current['username'])

    @app.post('/api/teacher/java/reset')
    def teacher_reset(payload: dict, current=Depends(teacher)):
        classes = getattr(app.state, 'classrooms', None)
        if not classes:
            raise HTTPException(409, '班級功能尚未就緒。')
        class_id, student_id = str(payload.get('class_id')), str(payload.get('student_id'))
        item = classes.get(class_id)
        if not item or item['teacher_id'] != current['id']:
            raise HTTPException(404, '班級不存在或不屬於你。')
        if not classes.member(class_id, student_id):
            raise HTTPException(404, '這位學生不在你的班級中。')
        return reset_work(student_id, str(payload.get('scope')), 'teacher:' + current['username'])

    @app.post('/api/teacher/java/design')
    def teacher_design(payload: dict, current=Depends(teacher)):
        """教師只能評自己班級學生的設計解釋；0–15 整數，可重新評分。"""
        classes = getattr(app.state, 'classrooms', None)
        if not classes:
            raise HTTPException(409, '班級功能尚未就緒。')
        class_id, student_id = str(payload.get('class_id')), str(payload.get('student_id'))
        item = classes.get(class_id)
        if not item or item['teacher_id'] != current['id']:
            raise HTTPException(404, '班級不存在或不屬於你。')
        if not classes.member(class_id, student_id):
            raise HTTPException(404, '這位學生不在你的班級中。')
        return save_manual_design(student_id, payload, 'teacher:' + current['username'])

    @app.post('/api/java/design')
    def founder_design(payload: dict, current=Depends(founder)):
        """管理員可評任何學生的設計解釋。"""
        student_id = str(payload.get('student_id') or '')
        target = next((u for u in store.list_users() if u['id'] == student_id), None)
        if not target or target['role'] != 'student':
            raise HTTPException(404, '找不到這位學生。')
        return save_manual_design(student_id, payload, 'admin:' + current['username'])
