"""Java 綜合實作與模擬實習：上傳、計次、門檻、重設、隔離與 AI 額度。

多數案例以假的檢查結果驗證業務規則，避免依賴 Docker；最後一個案例使用真實隔離容器，
Docker 或鏡像不可用時明確跳過，不把模擬結果當成真實執行。
"""
import io
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
PRACTICE = ROOT / 'training' / 'java-practice'
SHOP = ROOT / 'training' / 'java-shop'
FIXED_PRACTICE = ['src/competition/Competition.java', 'src/competition/Registration.java',
                  'src/competition/CompetitionRepository.java', 'src/competition/RegistrationException.java']


def zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def practice_files(service=None, test=None, fixed=True):
    files = {}
    if fixed:
        for name in FIXED_PRACTICE:
            files[name] = (PRACTICE / 'starter' / name).read_text(encoding='utf-8')
    files['src/competition/RegistrationService.java'] = service if service is not None else \
        (PRACTICE / 'starter/src/competition/RegistrationService.java').read_text(encoding='utf-8')
    files['test/competition/RegistrationServiceTest.java'] = test if test is not None else \
        (PRACTICE / 'starter/test/competition/RegistrationServiceTest.java').read_text(encoding='utf-8')
    files['README.md'] = '# 提交\n'
    return files


def shop_files(service=None):
    files = {}
    for item in (SHOP / 'starter/src/shop').iterdir():
        if item.name != 'ShopService.java':
            files['src/shop/' + item.name] = item.read_text(encoding='utf-8')
    files['src/shop/ShopService.java'] = service if service is not None else \
        (SHOP / 'starter/src/shop/ShopService.java').read_text(encoding='utf-8')
    files['README.md'] = '# 提交\n'
    return files


def fake_checks(core=True, tests=True, structure=True):
    checks = [{'key': f'CORE-{i}', 'label': f'核心{i}', 'dimension': 'core', 'weight': 5, 'passed': core,
               'expected': '符合', 'actual': 'ok' if core else '未通過'} for i in range(9)]
    checks += [{'key': k, 'label': k, 'dimension': 'student_tests', 'weight': 5, 'passed': tests,
                'expected': '符合', 'actual': 'ok' if tests else '未通過'}
               for k in ('TEST-CORRECT', 'TEST-FAULT-DUPLICATE', 'TEST-FAULT-CAPACITY', 'TEST-FAULT-OWNERSHIP')]
    checks += [{'key': f'STRUCT-{i}', 'label': f'結構{i}', 'dimension': 'structure', 'weight': 5, 'passed': structure,
                'expected': '符合', 'actual': 'ok' if structure else '未通過'} for i in range(4)]
    return checks


@pytest.fixture
def app(tmp_path, monkeypatch):
    from backend.main import create_app
    import backend.java_course as module
    monkeypatch.setattr(module, 'runtime_status', lambda: {'available': True, 'image': 'stub', 'reason': ''})
    application = create_app(tmp_path, demo=True)
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def login(client, username='student', password='Study2026!'):
    assert client.post('/api/auth/login', json={'username': username, 'password': password}).status_code == 200


def upload(client, scope, files, design=None):
    data = {'design': design} if design is not None else {}
    return client.post(f'/api/java/{scope}/upload', files={'file': ('project.zip', zip_bytes(files), 'application/zip')}, data=data)


def pass_practice(client, monkeypatch):
    """先讓綜合實作通過（設計解釋由管理員評分），之後才測商店工作。"""
    import backend.java_course as module
    original = module.run_check
    monkeypatch.setattr(module, 'run_check', lambda scope, folder: ('completed', {'checks': fake_checks(core=True, tests=True)}))
    submission = upload(client, 'practice', practice_files(), '說' * 200).json()['submission']
    result = client.post('/api/java/practice/check', json={'submission_id': submission['id']}).json()
    assert result['summary']['passed'] is False  # 設計解釋尚未評分
    student_id = client.get('/api/me').json()['id']
    login(client, 'founder', 'Founder2026!')
    graded = client.post('/api/java/design', json={'student_id': student_id, 'submission_id': submission['id'], 'score': 15})
    assert graded.status_code == 200, graded.text
    login(client)
    assert client.get('/api/java/practice').json()['summary']['passed'] is True
    monkeypatch.setattr(module, 'run_check', original)


def make_class_with_student(client, student_id, teacher='teacher'):
    """教師建立班級，學生確認加入。"""
    login(client, teacher, 'Teach2026!')
    class_id = client.post('/api/teacher/classes', json={'name': 'Java 評分班'}).json()['id']
    join_code = next(c['join_code'] for c in client.get('/api/teacher/classes').json()['classes'] if c['id'] == class_id)
    login(client)
    assert client.post('/api/student/classes/join', json={'code': join_code, 'consent': True}).status_code == 200
    return class_id


def test_upload_validation_and_fixed_files(client):
    login(client)
    assert client.post('/api/java/practice/upload', files={'file': ('x.zip', b'not-a-zip', 'application/zip')},
                       data={'design': '說' * 200}).status_code == 422
    missing = practice_files()
    del missing['test/competition/RegistrationServiceTest.java']
    assert upload(client, 'practice', missing, '說' * 200).status_code == 422
    tampered = practice_files()
    tampered[FIXED_PRACTICE[0]] = 'public class Competition {}'
    assert upload(client, 'practice', tampered, '說' * 200).status_code == 422
    assert upload(client, 'practice', practice_files(), '太短').status_code == 422
    assert upload(client, 'practice', practice_files(), '說' * 200).status_code == 200
    assert upload(client, 'practice', practice_files(), '說' * 200).status_code == 200
    detail = client.get('/api/java/practice').json()
    assert len(detail['state']['submissions']) == 2
    assert detail['summary']['attempts_used'] == 0  # 上傳不扣次


def test_passing_gate_and_attempt_limit_then_reset(client, app, monkeypatch):
    import backend.java_course as module
    login(client)
    submission = upload(client, 'practice', practice_files(), '說' * 200).json()['submission']
    monkeypatch.setattr(module, 'run_check', lambda scope, folder: ('completed', {'checks': fake_checks(core=True, tests=False)}))
    result = client.post('/api/java/practice/check', json={'submission_id': submission['id']}).json()
    assert result['check']['grade']['necessary'] is False
    assert result['check']['grade']['passed'] is False
    assert result['summary']['attempts_used'] == 1

    monkeypatch.setattr(module, 'run_check', lambda scope, folder: ('completed', {'checks': fake_checks(core=True, tests=True)}))
    submission = upload(client, 'practice', practice_files(), '說' * 200).json()['submission']
    result = client.post('/api/java/practice/check', json={'submission_id': submission['id']}).json()
    # 核心 45＋測試 20＋結構 20＝85；設計解釋未評分時即使已達 70 也不通過。
    assert result['check']['grade']['total'] == 85
    assert result['check']['grade']['passed'] is False
    assert result['check']['grade']['design_pending'] is True
    assert '設計解釋尚未評分' in result['check']['grade']['message']
    assert result['summary']['passed'] is False

    student_id = client.get('/api/me').json()['id']
    login(client, 'founder', 'Founder2026!')
    graded = client.post('/api/java/design', json={'student_id': student_id, 'submission_id': submission['id'], 'score': 15}).json()
    assert graded['design']['score'] == 15 and graded['design']['source'] == 'manual'
    assert graded['design']['grader'] == 'admin:founder'
    assert graded['summary']['passed'] is True
    login(client)
    assert client.get('/api/java/practice').json()['summary']['passed'] is True


def test_teacher_design_grading_unlocks_shop(client, app, monkeypatch):
    import backend.java_course as module
    login(client)
    monkeypatch.setattr(module, 'run_check', lambda scope, folder: ('completed', {'checks': fake_checks(core=True, tests=True)}))
    submission = upload(client, 'practice', practice_files(), '設計' * 100).json()['submission']
    checked = client.post('/api/java/practice/check', json={'submission_id': submission['id']}).json()
    assert checked['summary']['attempts_used'] == 1
    assert checked['summary']['passed'] is False
    assert client.get('/api/java/course').json()['shop_unlocked'] == 'practice'
    student_id = client.get('/api/me').json()['id']
    class_id = make_class_with_student(client, student_id)

    login(client, 'teacher', 'Teach2026!')
    learners = client.get(f'/api/teacher/java/learners?class_id={class_id}').json()
    design = learners['learners'][0]['design']
    assert design['submission_id'] == submission['id'] and design['score'] is None
    assert '設計' in design['text']
    for bad in (16, -1, 7.5, '12'):
        assert client.post('/api/teacher/java/design', json={'class_id': class_id, 'student_id': student_id,
                                                             'submission_id': submission['id'], 'score': bad}).status_code == 422
    graded = client.post('/api/teacher/java/design', json={'class_id': class_id, 'student_id': student_id,
                                                           'submission_id': submission['id'], 'score': 15, 'reason': '說明清楚'})
    assert graded.status_code == 200
    body = graded.json()
    assert body['design']['source'] == 'manual' and body['design']['grader'] == 'teacher:teacher'
    assert body['design']['note'] == '說明清楚'
    assert body['summary']['passed'] is True
    assert client.get(f'/api/teacher/java/learners?class_id={class_id}').json()['learners'][0]['design']['score'] == 15

    login(client)
    course = client.get('/api/java/course').json()
    assert course['shop_unlocked'] == 'shop-products'
    assert course['practice']['passed'] is True
    latest = client.get('/api/java/practice').json()['summary']['latest']
    assert latest['grade']['total'] == 100 and latest['grade']['design_score'] == 15
    assert latest['grade']['passed'] is True


def test_teacher_design_rejects_non_class_students(client, app, monkeypatch):
    import backend.java_course as module
    login(client)
    monkeypatch.setattr(module, 'run_check', lambda scope, folder: ('completed', {'checks': fake_checks(core=True, tests=True)}))
    submission = upload(client, 'practice', practice_files(), '說' * 200).json()['submission']
    client.post('/api/java/practice/check', json={'submission_id': submission['id']})
    student_id = client.get('/api/me').json()['id']

    login(client, 'teacher', 'Teach2026!')
    empty_class = client.post('/api/teacher/classes', json={'name': '沒有這位學生'}).json()['id']
    payload = {'class_id': empty_class, 'student_id': student_id, 'submission_id': submission['id'], 'score': 15}
    assert client.post('/api/teacher/java/design', json=payload).status_code == 404

    login(client, 'founder', 'Founder2026!')
    assert client.post('/api/operator/users', json={'username': 'teacher2', 'password': 'Teach2026!', 'role': 'teacher'}).status_code == 200
    class_id = make_class_with_student(client, student_id, teacher='teacher2')
    login(client, 'teacher', 'Teach2026!')
    assert client.post('/api/teacher/java/design', json={**payload, 'class_id': class_id}).status_code == 404
    login(client, 'student', 'Study2026!')
    assert client.get('/api/java/practice').json()['summary']['passed'] is False


def test_zero_design_score_and_total_below_70_still_fails(client, app, monkeypatch):
    import backend.java_course as module
    login(client)
    monkeypatch.setattr(module, 'run_check', lambda scope, folder: ('completed', {'checks': fake_checks(core=True, tests=True, structure=False)}))
    submission = upload(client, 'practice', practice_files(), '說' * 200).json()['submission']
    result = client.post('/api/java/practice/check', json={'submission_id': submission['id']}).json()
    assert result['check']['grade']['objective_score'] == 65
    student_id = client.get('/api/me').json()['id']
    login(client, 'founder', 'Founder2026!')
    graded = client.post('/api/java/design', json={'student_id': student_id, 'submission_id': submission['id'], 'score': 0}).json()
    assert graded['design']['score'] == 0 and graded['design']['source'] == 'manual'
    assert graded['summary']['passed'] is False
    assert graded['summary']['latest']['grade']['design_graded'] is True
    assert graded['summary']['latest']['grade']['total'] == 65
    assert '未達 70' in graded['summary']['latest']['grade']['message']


def test_regrading_keeps_passed_record_and_history(client, app, monkeypatch):
    import backend.java_course as module
    login(client)
    monkeypatch.setattr(module, 'run_check', lambda scope, folder: ('completed', {'checks': fake_checks(core=True, tests=True)}))
    submission = upload(client, 'practice', practice_files(), '說' * 200).json()['submission']
    result = client.post('/api/java/practice/check', json={'submission_id': submission['id']}).json()
    assert result['summary']['passed'] is False
    student_id = client.get('/api/me').json()['id']

    login(client, 'founder', 'Founder2026!')
    first = client.post('/api/java/design', json={'student_id': student_id, 'submission_id': submission['id'], 'score': 15}).json()
    assert first['summary']['passed'] is True and first['design']['history'] == []
    second = client.post('/api/java/design', json={'student_id': student_id, 'submission_id': submission['id'], 'score': 0}).json()
    assert second['design']['score'] == 0
    assert second['design']['history'][0]['score'] == 15
    assert second['summary']['passed'] is True  # 已通過的舊紀錄不被追溯撤銷
    assert second['summary']['latest']['grade']['passed'] is True
    assert second['summary']['latest']['grade']['total'] == 100



def test_three_attempts_environment_failure_and_founder_reset(client, app, monkeypatch):
    import backend.java_course as module
    login(client)
    monkeypatch.setattr(module, 'run_check', lambda scope, folder: ('environment_failed', {'message': 'Docker 不可用'}))
    for _ in range(3):
        submission = upload(client, 'practice', practice_files(), '說' * 200).json()['submission']
        result = client.post('/api/java/practice/check', json={'submission_id': submission['id']}).json()
        assert result['check']['counted'] is False
    assert client.get('/api/java/practice').json()['summary']['attempts_used'] == 0

    monkeypatch.setattr(module, 'run_check', lambda scope, folder: ('completed', {'checks': fake_checks(core=False, tests=False)}))
    for _ in range(3):
        submission = upload(client, 'practice', practice_files(), '說' * 200).json()['submission']
        client.post('/api/java/practice/check', json={'submission_id': submission['id']})
    summary = client.get('/api/java/practice').json()['summary']
    assert summary['attempts_used'] == 3 and summary['locked'] is True
    assert upload(client, 'practice', practice_files(), '說' * 200).status_code == 409

    student_id = client.get('/api/me').json()['id']
    client.post('/api/auth/login', json={'username': 'student2', 'password': 'Study2026!'})
    assert client.post('/api/java/reset', json={'student_id': student_id, 'scope': 'practice'}).status_code == 403
    client.post('/api/auth/login', json={'username': 'founder', 'password': 'Founder2026!'})
    reset = client.post('/api/java/reset', json={'student_id': student_id, 'scope': 'practice'})
    assert reset.status_code == 200
    client.post('/api/auth/login', json={'username': 'student', 'password': 'Study2026!'})
    detail = client.get('/api/java/practice').json()
    assert detail['summary']['attempts_left'] == 3
    assert detail['summary']['locked'] is False
    assert len(detail['state']['checks']) == 6  # 歷史保留，含未計次的環境失敗
    assert detail['state']['resets'][-1]['previous_attempts'] == 3


def test_teacher_reset_requires_class_membership(client, app, monkeypatch):
    import backend.java_course as module
    login(client)
    pass_practice(client, monkeypatch)
    monkeypatch.setattr(module, 'run_check', lambda scope, folder: ('completed', {'checks': fake_checks(core=False, tests=False)}))
    for _ in range(3):
        submission = upload(client, 'shop-products', shop_files()).json()['submission']
        client.post('/api/java/shop-products/check', json={'submission_id': submission['id']})
    assert client.get('/api/java/shop-products').json()['summary']['locked'] is True
    student_id = client.get('/api/me').json()['id']

    client.post('/api/auth/login', json={'username': 'teacher', 'password': 'Teach2026!'})
    class_id = client.post('/api/teacher/classes', json={'name': 'Java 班'}).json()['id']
    # 學生尚未加入班級：教師不能重設
    assert client.post('/api/teacher/java/reset', json={'class_id': class_id, 'student_id': student_id, 'scope': 'shop-products'}).status_code == 404

    client.post('/api/auth/login', json={'username': 'student', 'password': 'Study2026!'})
    code = client.get('/api/teacher/classes').status_code  # 學生無權讀教師列表
    assert code == 403
    client.post('/api/auth/login', json={'username': 'teacher', 'password': 'Teach2026!'})
    join_code = client.get('/api/teacher/classes').json()['classes'][0]['join_code']
    client.post('/api/auth/login', json={'username': 'student', 'password': 'Study2026!'})
    assert client.post('/api/student/classes/join', json={'code': join_code, 'consent': True}).status_code == 200

    client.post('/api/auth/login', json={'username': 'teacher', 'password': 'Teach2026!'})
    learners = client.get(f'/api/teacher/java/learners?class_id={class_id}').json()
    assert learners['learners'][0]['scopes']['shop-products']['locked'] is True
    assert client.post('/api/teacher/java/reset', json={'class_id': class_id, 'student_id': student_id, 'scope': 'shop-products'}).status_code == 200
    client.post('/api/auth/login', json={'username': 'student', 'password': 'Study2026!'})
    assert client.get('/api/java/shop-products').json()['summary']['attempts_left'] == 3


def test_shop_requires_previous_task_and_student_isolation(client, monkeypatch):
    login(client)
    assert upload(client, 'shop-products', shop_files()).status_code == 409  # 綜合實作未通過
    assert upload(client, 'shop-orders-create', shop_files()).status_code == 409
    assert client.get('/api/java/course').json()['shop_unlocked'] == 'practice'

    pass_practice(client, monkeypatch)
    assert upload(client, 'shop-products', shop_files()).status_code == 200
    assert upload(client, 'shop-orders-create', shop_files()).status_code == 409  # 前一項工作尚未通過
    detail = client.get('/api/java/shop-products').json()
    assert detail['state']['submissions'][0]['files']

    client.post('/api/auth/login', json={'username': 'student2', 'password': 'Study2026!'})
    other = client.get('/api/java/shop-products').json()
    assert other['state']['submissions'] == []
    assert client.get('/api/java/course').json()['shop_unlocked'] == 'practice'


def test_explain_uses_shared_daily_quota(client, app, monkeypatch):
    import backend.java_course as module
    import backend.java_route as route_module
    from backend.agent import ModelConfig
    app.state.model_config = ModelConfig('dummy', 'https://example.test/v1', 'dummy')
    monkeypatch.setattr(module, 'run_check', lambda scope, folder: ('completed', {'checks': fake_checks(core=False, tests=False)}))

    def fake_agent(purpose, context, config, tools, transport=None):
        if 'answer_question' in tools:
            tools['answer_question']({'text': '請先檢查重複報名與名額。', 'evidence_ids': []})
        return {'status': 'ok', 'mode': 'ai', 'message': '完成', 'usage': {}, 'actions': [], 'model': 'stub', 'cost': None}
    monkeypatch.setattr(module, 'run_agent', fake_agent)
    monkeypatch.setattr(route_module, 'run_agent', fake_agent)
    login(client)
    submission = upload(client, 'practice', practice_files(), '說' * 200).json()['submission']
    check = client.post('/api/java/practice/check', json={'submission_id': submission['id']}).json()['check']
    assert client.post('/api/java/practice/explain', json={'check_id': check['id']}).json()['remaining'] == 9
    for _ in range(9):
        assert client.post('/api/java-route/ask', json={'question': '什麼是類？'}).status_code == 200
    with app.state.store.connect() as db:
        used = db.execute('SELECT used FROM ai_daily_quota WHERE user_id=(SELECT id FROM users WHERE username=?)',
                          ('student',)).fetchone()['used']
    assert used == 10
    assert client.post('/api/java/practice/explain', json={'check_id': check['id']}).status_code == 429


def test_design_review_requires_real_quotes(client, app, monkeypatch):
    import backend.java_course as module
    from backend.agent import ModelConfig
    app.state.model_config = ModelConfig('dummy', 'https://example.test/v1', 'dummy')
    monkeypatch.setattr(module, 'run_check', lambda scope, folder: ('completed', {'checks': fake_checks(core=True, tests=True)}))
    design = '我用 competitionLock 保護名額檢查與建立，重複報名直接回傳原紀錄；限制是尚未加入持久化儲存。' + '補' * 160

    def invalid_agent(purpose, context, config, tools, transport=None):
        try:
            tools['review_design']({'criteria': [{'criterion': '事實', 'score': 4, 'reason': 'x',
                                                  'quote': '我沒有寫過這句', 'evidence_id': context['evidence_ids'][0]}] * 3})
        except ValueError:
            return {'status': 'error', 'mode': 'ai', 'message': '回覆格式無效', 'usage': {}, 'actions': [], 'model': 'stub', 'cost': None}
        return {'status': 'ok', 'mode': 'ai', 'message': '完成', 'usage': {}, 'actions': [], 'model': 'stub', 'cost': None}

    def valid_agent(purpose, context, config, tools, transport=None):
        criteria = [{'criterion': name, 'score': 4, 'reason': '有具體說明',
                     'quote': design[:40], 'evidence_id': context['evidence_ids'][0]}
                    for name in ('對本人實現的事實描述', '關鍵技術取捨的理由', '已識別的限制與下一步')]
        tools['review_design']({'criteria': criteria})
        return {'status': 'ok', 'mode': 'ai', 'message': '完成', 'usage': {}, 'actions': [], 'model': 'stub', 'cost': None}

    login(client)
    submission = upload(client, 'practice', practice_files(), design).json()['submission']
    client.post('/api/java/practice/check', json={'submission_id': submission['id']})
    monkeypatch.setattr(module, 'run_agent', invalid_agent)
    assert client.post('/api/java/practice/design', json={'submission_id': submission['id']}).json()['review'] is None
    monkeypatch.setattr(module, 'run_agent', valid_agent)
    result = client.post('/api/java/practice/design', json={'submission_id': submission['id']}).json()
    assert result['review']['score'] == 12
    grade = client.get('/api/java/practice').json()['state']['checks'][-1]['grade']
    assert grade['design_score'] == 12 and grade['total'] == 97  # 85 客觀＋12 設計


def test_real_container_check_on_reference_solution(tmp_path):
    pytest.importorskip('fastapi')
    try:
        probe = subprocess.run(['docker', 'image', 'inspect', 'course-platform-java:2026.11.5'], capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip('本機沒有 Docker，略過真實容器檢查。')
    if probe.returncode != 0:
        pytest.skip('Java 檢查鏡像未建立，略過真實容器檢查。')
    from backend.main import create_app
    app = create_app(tmp_path, demo=True)
    with TestClient(app) as client:
        login(client)
        files = practice_files(
            service=(PRACTICE / 'checks/base/competition/RegistrationService.java').read_text(encoding='utf-8'),
            test=(PRACTICE / 'checks/reference/competition/RegistrationServiceTest.java').read_text(encoding='utf-8'))
        submission = upload(client, 'practice', files, '說' * 200).json()['submission']
        result = client.post('/api/java/practice/check', json={'submission_id': submission['id']}).json()
        assert result['check']['status'] == 'completed'
        assert result['check']['counted'] is True
        assert result['check']['grade']['necessary'] is True
        assert result['check']['grade']['design_pending'] is True
        assert result['check']['grade']['passed'] is False
        assert len(result['check']['grade']['checks']) >= 13
        student_id = client.get('/api/me').json()['id']
        login(client, 'founder', 'Founder2026!')
        graded = client.post('/api/java/design', json={'student_id': student_id, 'submission_id': submission['id'], 'score': 15})
        assert graded.status_code == 200
        assert graded.json()['summary']['passed'] is True


def test_submission_archive_rejects_traversal_absolute_and_duplicate_paths(tmp_path):
    from backend.java_course import validate_archive
    root = tmp_path / 'java'; root.mkdir()
    base = practice_files()
    for names in ({'../escape.txt': 'x'}, {'/absolute.txt': 'x'},
                  {'src/competition/Competition.java': 'x', 'src/competition/competition.java': 'y'}):
        with pytest.raises(HTTPException):
            validate_archive(zip_bytes(names), 'practice', root / 'u' / 'practice' / 'one', PRACTICE, root)


def test_submission_directory_collision_and_symlink_are_rejected(tmp_path):
    from backend.java_course import validate_archive
    root = tmp_path / 'java'; root.mkdir()
    folder = root / 'u' / 'practice' / 'fixed'
    folder.mkdir(parents=True)
    with pytest.raises(HTTPException):
        validate_archive(zip_bytes(practice_files()), 'practice', folder, PRACTICE, root)
    outside = tmp_path / 'outside'; outside.mkdir()
    link = root / 'u' / 'practice' / 'link'
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('当前系统不支持创建目录符号链接')
    with pytest.raises(HTTPException):
        validate_archive(zip_bytes(practice_files()), 'practice', link, PRACTICE, root)


def test_checker_bundle_excludes_reference_answers(tmp_path):
    from backend.java_course import checker_bundle
    lifetime, bundle = checker_bundle('practice', PRACTICE)
    try:
        assert not (bundle / 'checks' / 'reference').exists()
        assert (bundle / 'checks' / 'harness').is_dir()
        assert (bundle / 'checks' / 'base').is_dir()
    finally:
        lifetime.cleanup()
