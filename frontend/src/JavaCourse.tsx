import { useEffect, useState } from 'react';
import { api, notifyUser, type Obj } from './api';
import './java-course.css';

type Step = { scope: string; title: string; hint: string };
const STEPS: Step[] = [
  { scope: 'practice', title: '綜合實作：比賽報名系統', hint: '在自己電腦完成 Java 功能與測試，上傳檢查。滿分 100，至少 70。' },
  { scope: 'shop-products', title: '模擬實習 · 查詢商品', hint: '接手網上商店，完成商品查詢與關鍵字篩選。' },
  { scope: 'shop-orders-create', title: '模擬實習 · 建立訂單', hint: '檢查商品與庫存，扣庫存並計算總價。' },
  { scope: 'shop-orders-list', title: '模擬實習 · 查看訂單', hint: '只顯示自己的訂單，並提供訂單明細。' },
];
const TITLES: Record<string, string> = Object.fromEntries(STEPS.map(s => [s.scope, s.title]));

function statusOf(step: Obj | undefined) {
  if (!step) return { label: '尚未開始', tone: 'idle' };
  if (step.passed) return { label: '已通過', tone: 'done' };
  if (step.locked) return { label: '已暫停檢查', tone: 'locked' };
  if (step.attempts_used > 0) return { label: `待通過 · 剩 ${step.attempts_left} 次`, tone: 'active' };
  return { label: '尚未開始', tone: 'idle' };
}

export default function JavaCourse({ onBack }: { onBack: () => void }) {
  const [overview, setOverview] = useState<Obj | null>(null);
  const [scope, setScope] = useState('practice');
  const [detail, setDetail] = useState<Obj | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [design, setDesign] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [explain, setExplain] = useState('');

  async function loadOverview() {
    try { setOverview(await api('/java/course')); } catch (e) { setError(e instanceof Error ? e.message : '載入失敗'); }
  }
  async function loadDetail(target = scope) {
    try { setDetail(await api('/java/' + target)); } catch (e) { setError(e instanceof Error ? e.message : '載入失敗'); }
  }
  useEffect(() => { void loadOverview(); }, []);
  useEffect(() => { setDetail(null); setExplain(''); setFile(null); setMessage(''); setError(''); void loadDetail(scope); }, [scope]);

  const summary = detail?.summary;
  const state = detail?.state;
  const latest = summary?.latest;
  const shopUnlocked = overview?.shop_unlocked;

  async function submit() {
    if (!file) { notifyUser('請先選擇要上傳的 ZIP。'); return; }
    if (!/\.zip$/i.test(file.name)) { notifyUser('只接受 ZIP 格式：請選擇副檔名為 .zip 的壓縮檔。'); return; }
    if (scope === 'practice' && design.trim().length < 200) { notifyUser('請填寫至少 200 字的設計解釋。'); return; }
    setBusy(true); setError(''); setMessage(''); setExplain('');
    try {
      const form = new FormData();
      form.append('file', file);
      if (scope === 'practice') form.append('design', design.trim());
      const uploaded = await api(`/java/${scope}/upload`, form);
      setMessage('上傳完成，開始在隔離環境檢查，通常需要 1–3 分鐘…');
      const result = await api(`/java/${scope}/check`, { submission_id: uploaded.submission.id });
      setDetail({ ...detail, summary: result.summary, state: result.state });
      setFile(null);
      setMessage(result.check.counted ? '檢查完成，結果已記錄。' : '本次未完成檢查，不計次，可以稍後重試。');
      await loadOverview();
    } catch (e) {
      setError(e instanceof Error ? e.message : '上傳或檢查失敗');
    } finally { setBusy(false); }
  }

  async function askExplain() {
    if (!latest) return;
    setBusy(true); setError('');
    try {
      const result = await api(`/java/${scope}/explain`, { check_id: latest.id });
      setExplain(`${result.message}\n\n今日 AI 剩餘 ${result.remaining} 次。`);
      if (result.status !== 'ok') notifyUser(result.message, 'AI 未完成解釋');
    } catch (e) { setError(e instanceof Error ? e.message : 'AI 解釋失敗'); }
    finally { setBusy(false); }
  }

  async function askDesign() {
    const submission = state?.submissions?.at(-1);
    if (!submission) return;
    setBusy(true); setError('');
    try {
      const result = await api('/java/practice/design', { submission_id: submission.id });
      setMessage(result.review ? `設計解釋評分：${result.review.score}/15` : 'AI 未完成評分。');
      if (result.status !== 'ok') notifyUser(result.message, 'AI 未完成評分');
      await loadDetail('practice');
    } catch (e) { setError(e instanceof Error ? e.message : '評分失敗'); }
    finally { setBusy(false); }
  }

  const designReview = state && latest ? state.design?.[latest.submission_id] : null;
  const grade = latest?.grade;

  return <div className="java-shell">
    <header className="jc-top">
      <button className="jc-back" onClick={onBack}>← 返回學習路線</button>
      <span className="jc-remaining">今日 AI 剩餘 {overview?.remaining ?? '—'} / 10 次</span>
    </header>
    <main className="jc-main">
      <section className="jc-intro">
        <h1>從學習，走到模擬實習</h1>
        <p>先在綜合實作完成一個真實小系統（核心功能、你自己的測試、程式結構與設計解釋都會計分），通過後接手網上商店。所有檢查都在隔離環境實際執行你的程式，AI 只解釋結果，不能替你判定通過。</p>
        {overview && !overview.runtime.available && <div className="jc-alert">檢查環境暫時不可用：{overview.runtime.reason} 這段時間的檢查不會消耗次數。</div>}
      </section>

      <div className="jc-layout">
        <nav className="jc-rail" aria-label="實習交接軌">
          <ol>
            {STEPS.map((step, index) => {
              const data = step.scope === 'practice' ? overview?.practice : overview?.shop?.[step.scope];
              const status = statusOf(data);
              const locked = step.scope !== 'practice' && shopUnlocked !== step.scope && !data?.passed;              return <li key={step.scope} className={`jc-stage ${scope === step.scope ? 'selected' : ''} ${status.tone}`}>
                <span className="jc-stage-index">{index + 1}</span>
                <button className="jc-stage-body" disabled={locked} onClick={() => setScope(step.scope)}>
                  <strong>{step.title}</strong>
                  <small>{step.hint}</small>
                </button>
                <span className={`jc-stamp ${status.tone}`}>{locked ? (step.scope === 'shop-products' ? '通過綜合實作後開放' : '完成前一項後開放') : status.label}</span>
              </li>;
            })}
          </ol>
          <p className="jc-rail-note">綜合實作與每一項實習各自最多 3 次有效檢查；環境故障不計次。用完後請教師或管理員重設。</p>
        </nav>

        <section className="jc-work">
          <div className="jc-work-head">
            <div>
              <h2>{TITLES[scope]}</h2>
              <p>檢查只使用你上傳的 ZIP，不會在你的電腦以外執行其他操作。</p>
            </div>
            {summary && <div className="jc-attempts"><strong>{summary.attempts_left}</strong><small>次有效檢查剩餘</small></div>}
          </div>

          {error && <div className="alert" role="alert">{error}</div>}
          {message && <div className="toast" role="status">{message}</div>}

          {summary?.locked ? <div className="jc-locked">
            <h3>已用完 3 次有效檢查</h3>
            <p>請先複習 README 的規則，再請教師或管理員重設次數。重設不會刪除先前的提交與結果。</p>
          </div> : <div className="jc-upload">
            <a className="button secondary" href={`/api/java/${scope}/starter`}>下載起始專案 ZIP</a>
            <label>你的 ZIP<input type="file" accept=".zip" disabled={busy} onChange={e => {
              const picked = e.target.files?.[0] || null;
              if (picked && !/\.zip$/i.test(picked.name)) {
                setFile(null);
                e.target.value = '';
                notifyUser('只接受 ZIP 格式：請選擇副檔名為 .zip 的壓縮檔。');
                return;
              }
              setFile(picked);
            }} /></label>
            {scope === 'practice' && <label>設計解釋（200–2000 字）
              <textarea value={design} maxLength={2000} disabled={busy} onChange={e => setDesign(e.target.value)}
                placeholder="說明你如何處理重複報名、名額與截止時間，以及目前的限制。這段文字會用於設計評分，也會與你的測試一起被檢查。" />
            </label>}
            <div className="jc-actions">
              <button className="button" disabled={busy || !file} onClick={submit}>{busy ? '正在上傳並檢查…' : '上傳並執行檢查'}</button>
              <small>{file ? `已選擇：${file.name}` : '尚未選擇檔案'}</small>
            </div>
          </div>}

          {grade && <div className={`jc-result ${grade.passed ? 'passed' : ''}`}>
            <header>
              <h3>{grade.passed ? '本次檢查通過' : '本次檢查未通過'}</h3>
              <span className="jc-score">{grade.total !== undefined ? `${grade.total} / 100` : `${grade.score} / ${grade.max_score}`}</span>
            </header>
            {grade.total !== undefined && <p className="jc-score-split">
              客觀＋結構 <strong>{grade.objective_score ?? grade.score}/{grade.max_score}</strong>
              <span>·</span>
              設計解釋 <strong className={grade.design_graded ? '' : 'pending'}>{grade.design_graded ? `${grade.design_score}/15` : '0/15（待評分）'}</strong>
            </p>}
            <p className="jc-result-note">{grade.message}</p>
            {grade.design_pending && <p className="jc-result-note jc-design-pending">設計解釋尚未評分，因此本次不能通過，商店也不會解鎖。請按下方「請 AI 評分設計解釋」，或等教師人工評分。</p>}
            <table>
              <thead><tr><th>項目</th><th>結果</th><th>說明</th></tr></thead>
              <tbody>{grade.checks.map((c: Obj) => <tr key={c.key} className={c.passed ? 'ok' : 'bad'}>
                <td><strong>{c.label}</strong><small>{c.key}</small></td>
                <td>{c.passed ? '通過' : '未通過'}</td>
                <td>{c.actual}</td>
              </tr>)}</tbody>
            </table>
          </div>}

          {latest && <div className="jc-ai">
            <div>
              <h3>需要時再請 AI 解釋</h3>
              <p>AI 會閱讀這次檢查的實際結果，說明原因與下一步。每次解釋使用每日共用額度。</p>
            </div>
            <div className="jc-ai-actions">
              <button className="button secondary" disabled={busy || !overview?.ai_enabled} onClick={askExplain}>請 AI 解釋這次結果</button>
              {scope === 'practice' && latest.counted && <button className="button secondary" disabled={busy || !overview?.ai_enabled} onClick={askDesign}>請 AI 評分設計解釋</button>}
            </div>
            {!overview?.ai_enabled && <p className="jc-muted">AI 尚未配置；程式檢查仍可正常使用。</p>}
            {explain && <pre className="jc-explain">{explain}</pre>}
            {designReview && <div className="jc-design">
              <h4>設計解釋評分 {designReview.score} / 15 · {designReview.source === 'ai' ? 'AI 評分' : '人工評分'}{designReview.source !== 'ai' && designReview.grader ? `（${designReview.grader}）` : ''}</h4>
              {designReview.note && <p className="jc-design-note">{designReview.note}</p>}
              {(designReview.criteria || []).map((c: Obj) => <p key={c.criterion}><strong>{c.criterion} {c.score}/5</strong> {c.reason}<br /><em>「{c.quote}」</em></p>)}
              {(designReview.history || []).length > 0 && <p className="jc-muted">這份設計解釋曾重新評分 {designReview.history.length} 次，以最新一次為準；已通過的舊檢查紀錄不會因此撤銷。</p>}
            </div>}
          </div>}

          {state && <details className="jc-history">
            <summary>查看提交與檢查紀錄（{state.submissions.length} 個版本 · {state.checks.length} 次檢查）</summary>
            <ul>
              {state.checks.slice().reverse().map((c: Obj) => <li key={c.id}>
                版本 {c.version} · {c.status === 'completed' ? (c.grade?.passed ? '通過' : '未通過') : '未完成（不計次）'}
                {c.grade?.total !== undefined && ` · ${c.grade.total}/100`}
                {c.grade?.design_pending && ' · 設計解釋待評分'}
                {c.grade?.score !== undefined && c.grade?.total === undefined && ` · ${c.grade.score}/${c.grade.max_score}`}
                {c.resets ? '' : ''} <small>{new Date(c.created * 1000).toLocaleString('zh-TW')}</small>
              </li>)}
              {state.resets.map((r: Obj, i: number) => <li key={'reset' + i} className="jc-reset">次數重設：{r.actor} · 原本已用 {r.previous_attempts} 次 <small>{new Date(r.created * 1000).toLocaleString('zh-TW')}</small></li>)}
            </ul>
          </details>}
        </section>
      </div>
    </main>
  </div>;
}
