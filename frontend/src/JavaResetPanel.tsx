import { useCallback, useEffect, useState } from 'react';
import { api, notifyUser, reportError, type Obj } from './api';
import './java-course.css';

const SCOPE_LABELS: Record<string, string> = {
  practice: '綜合實作',
  'shop-products': '查詢商品',
  'shop-orders-create': '建立訂單',
  'shop-orders-list': '查看訂單',
};

function sourceLabel(design: Obj) {
  if (design.score == null) return '待評分';
  return `${design.score}/15 · ${design.source === 'ai' ? 'AI 評分' : '人工評分'}`;
}

/** 教師／管理員查看 Java 實作進度、重設次數，並人工評分綜合實作的設計解釋。 */
export default function JavaResetPanel({ classId, admin = false }: { classId?: string; admin?: boolean }) {
  const [data, setData] = useState<Obj | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState('');
  const [drafts, setDrafts] = useState<Record<string, { score: string; reason: string }>>({});

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!admin && !classId) { setData(null); return; }
    const path = admin ? '/java/operator/learners' : '/teacher/java/learners?class_id=' + encodeURIComponent(classId!);
    const result = await api(path, undefined, undefined, signal);
    setData(result); setError('');
  }, [admin, classId]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).catch(e => { if (!controller.signal.aborted) setError(reportError(e, '讀取 Java 進度失敗')); });
    return () => controller.abort();
  }, [load]);

  async function reset(studentId: string, scope: string) {
    setBusy(studentId + scope); setError(''); setMessage('');
    try {
      if (admin) await api('/java/reset', { student_id: studentId, scope });
      else await api('/teacher/java/reset', { class_id: classId, student_id: studentId, scope });
      setMessage('已重設這項工作的檢查次數；先前的提交與結果仍保留。');
      await load();
    } catch (e) { setError(reportError(e, '重設未完成')); }
    finally { setBusy(''); }
  }

  async function gradeDesign(learner: Obj) {
    const design = learner.design;
    const draft = drafts[learner.id] || { score: '', reason: '' };
    const score = Number(draft.score);
    if (draft.score.trim() === '' || !Number.isInteger(score) || score < 0 || score > 15) {
      notifyUser('設計解釋分數必須是 0–15 的整數（可以是 0 分）。'); return;
    }
    setBusy(learner.id + design.submission_id); setError(''); setMessage('');
    try {
      const payload = { student_id: learner.id, submission_id: design.submission_id, score, reason: draft.reason };
      const result = admin
        ? await api('/java/design', payload)
        : await api('/teacher/java/design', { ...payload, class_id: classId });
      const summary = result.summary;
      setMessage(`已保存 ${learner.username} 的設計解釋評分 ${score}/15；目前總分 ${summary.latest?.grade?.total ?? '—'}/100${summary.passed ? '，綜合實作已通過。' : '，尚未通過。'}`);
      setDrafts(previous => ({ ...previous, [learner.id]: { score: '', reason: '' } }));
      await load();
    } catch (e) { setError(reportError(e, '評分未保存')); }
    finally { setBusy(''); }
  }

  if (!admin && !classId) return null;
  if (!data) return <section className="panel jr-panel"><h2>Java 實作檢查次數</h2><p className="muted">{error || '正在讀取學生的 Java 進度…'}</p></section>;
  if (data.learners.length === 0) return null;
  const designs = data.learners.filter((learner: Obj) => learner.design);

  return <section className="panel jr-panel">
    <div className="section-head"><div><h2>Java 實作檢查次數與設計評分</h2>
      <p className="muted">綜合實作與每項實習各自最多 3 次有效檢查；環境故障不計次。用完後由教師或管理員在此重設，重設不移除歷史紀錄。設計解釋（0–15 分）必須完成評分才可能通過綜合實作。</p></div></div>
    {error && <div className="alert" role="alert">{error}</div>}
    {message && <div className="notice" role="status">{message}</div>}
    <div className="table-scroll"><table className="jr-table"><thead><tr><th>學生</th><th>工作</th><th>已用 / 上限</th><th>狀態</th><th>處理</th></tr></thead>
      <tbody>{data.learners.flatMap((learner: Obj) => Object.entries(learner.scopes).map(([scope, summary]: [string, any]) => <tr key={learner.id + scope}>
        <td><strong>{learner.username}</strong>{learner.is_demo && <small>演示學生</small>}</td>
        <td>{SCOPE_LABELS[scope] || scope}</td>
        <td>{summary.attempts_used} / {data.max_attempts}</td>
        <td>{summary.passed ? '已通過' : summary.locked ? '已暫停，需重設' : summary.attempts_used ? '待通過' : '尚未開始'}</td>
        <td>{summary.locked ? <button className="button secondary" disabled={Boolean(busy)} onClick={() => reset(learner.id, scope)}>{busy === learner.id + scope ? '正在重設…' : '重設次數'}</button> : <span className="muted">—</span>}</td>
      </tr>))}</tbody></table></div>

    {designs.length > 0 && <div className="jr-designs">
      <h3>綜合實作 · 設計解釋人工評分</h3>
      <p className="muted">分數 0–15，可以是 0 分；未評分時即使其他項目合計達 85 分，綜合實作仍不通過、商店不會解鎖。重新評分以最新一次生效，舊評分保留在歷史。</p>
      {designs.map((learner: Obj) => {
        const design = learner.design;
        const draft = drafts[learner.id] || { score: '', reason: '' };
        const working = busy === learner.id + design.submission_id;
        return <article className="jr-design" key={learner.id}>
          <div className="jr-design-head">
            <div><strong>{learner.username}</strong>{learner.is_demo && <small>演示學生</small>}
              <small>提交版本 {design.version} · 已檢查：{design.check_total != null ? `${design.check_total}/100` : '尚無有效檢查'}</small></div>
            <span className={'pill ' + (design.score == null ? 'amber' : '')}>{sourceLabel(design)}</span>
          </div>
          <details>
            <summary>查看設計解釋原文（{design.text.length} 字）</summary>
            <p className="jr-design-text">{design.text}</p>
          </details>
          <div className="jr-design-form">
            <label>分數（0–15）<input type="number" min="0" max="15" step="1" disabled={working}
              value={draft.score} onChange={e => setDrafts(previous => ({ ...previous, [learner.id]: { ...draft, score: e.target.value } }))} /></label>
            <label>評語（選填）<input maxLength={1000} disabled={working} value={draft.reason}
              placeholder="例如：已說明重複報名與名額處理，限制描述具體。"
              onChange={e => setDrafts(previous => ({ ...previous, [learner.id]: { ...draft, reason: e.target.value } }))} /></label>
            <button className="button" disabled={Boolean(busy)} onClick={() => gradeDesign(learner)}>{working ? '正在保存…' : design.score == null ? '保存評分' : '重新評分'}</button>
          </div>
          {design.grader && <small className="jr-design-meta">上次評分：{design.grader} · {new Date(design.graded_at * 1000).toLocaleString('zh-TW')}{design.history > 0 ? ` · 之前已有 ${design.history} 次評分紀錄` : ''}{design.note ? ` · 評語：${design.note}` : ''}</small>}
        </article>;
      })}
    </div>}
  </section>;
}
