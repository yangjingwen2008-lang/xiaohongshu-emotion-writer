import { useEffect, useState } from 'react'
import { CalendarClock, ChevronRight, ExternalLink, LoaderCircle, Plus, RotateCcw, Save, Sparkles } from 'lucide-react'
import type { Content, SetupStatus, TrendCandidate, TrendRun, ManualTrendSource, TrendSchedule, OcrStatus, OcrRun } from '../types'
import { API, request, uploadRequest } from '../lib/api'

export function TrendPanel({ status, onCreated }: { status: SetupStatus | null; onCreated: (content: Content) => void }) {
  const [candidates, setCandidates] = useState<TrendCandidate[]>([])
  const [runs, setRuns] = useState<TrendRun[]>([])
  const [manualSources, setManualSources] = useState<ManualTrendSource[]>([])
  const [schedule, setSchedule] = useState<TrendSchedule | null>(null)
  const [ocrStatus, setOcrStatus] = useState<OcrStatus | null>(null)
  const [pendingOcr, setPendingOcr] = useState<OcrRun | null>(null)
  const [ocrLabel, setOcrLabel] = useState('截图讨论')
  const [ocrText, setOcrText] = useState('')
  const [ocrConfirmed, setOcrConfirmed] = useState(false)
  const [sourceType, setSourceType] = useState<'topic' | 'url'>('topic')
  const [sourceLabel, setSourceLabel] = useState('')
  const [sourceValue, setSourceValue] = useState('')
  const [sourceConfirmed, setSourceConfirmed] = useState(false)
  const [showManual, setShowManual] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  async function load() {
    const [candidateRows, runRows, manualRows, scheduleValue, ocrValue, ocrRows] = await Promise.all([
      request<TrendCandidate[]>('/trends/candidates'),
      request<TrendRun[]>('/trends/runs?limit=1'),
      request<ManualTrendSource[]>('/trends/manual-sources'),
      request<TrendSchedule>('/trends/schedule/status'),
      request<OcrStatus>('/ocr/status'),
      request<OcrRun[]>('/ocr/runs?purpose=trend'),
    ])
    setCandidates(candidateRows); setRuns(runRows); setManualSources(manualRows); setSchedule(scheduleValue)
    setOcrStatus(ocrValue)
    const pending = ocrRows.find((item) => item.status === 'pending_confirmation') || null
    setPendingOcr(pending); if (pending) setOcrText(pending.corrected_text || pending.recognized_text || '')
  }
  useEffect(() => { void Promise.resolve().then(load).catch((e) => setError((e as Error).message)) }, [])

  async function refresh() {
    setBusy('refresh'); setError('')
    try { await request('/trends/refresh', { method: 'POST' }); await load() }
    catch (e) { setError((e as Error).message); await load().catch(() => undefined) }
    finally { setBusy('') }
  }

  async function saveManual(event: React.FormEvent) {
    event.preventDefault(); setBusy('manual'); setError('')
    try {
      await request('/trends/manual-sources', { method: 'POST', body: JSON.stringify({ source_type: sourceType, label: sourceLabel, source_value: sourceValue, confirm: sourceConfirmed }) })
      setSourceLabel(''); setSourceValue(''); setSourceConfirmed(false); await load()
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }

  async function uploadScreenshot(file?: File) {
    if (!file) return
    setBusy('ocr-upload'); setError('')
    const body = new FormData(); body.append('file', file)
    try {
      const result = await uploadRequest<OcrRun>('/ocr/trends', body)
      setPendingOcr(result); setOcrText(result.corrected_text || result.recognized_text || ''); setOcrConfirmed(false)
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }

  async function confirmOcr() {
    if (!pendingOcr) return
    setBusy('ocr-confirm'); setError('')
    try {
      await request(`/ocr/runs/${pendingOcr.id}/confirm`, { method: 'POST', body: JSON.stringify({ label: ocrLabel, corrected_text: ocrText, confirm: ocrConfirmed }) })
      setPendingOcr(null); setOcrText(''); setOcrConfirmed(false); await load()
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }

  async function discardOcr() {
    if (!pendingOcr || !window.confirm('永久删除这张截图并清除识别文字？此操作不能撤销。')) return
    setBusy('ocr-discard'); setError('')
    try {
      await request(`/ocr/runs/${pendingOcr.id}/discard`, { method: 'POST', body: JSON.stringify({ confirm: true }) })
      setPendingOcr(null); setOcrText(''); setOcrConfirmed(false)
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }

  async function startFromCandidate(candidate: TrendCandidate) {
    if (!window.confirm(`确认用“${candidate.title}”创建一篇新文章？热点只作为私人情绪入口，不会复制原标题。`)) return
    setBusy(`use-${candidate.id}`); setError('')
    try {
      const content = await request<Content>(`/trends/candidates/${candidate.id}/use`, { method: 'POST', body: JSON.stringify({ confirm: true }) })
      onCreated(content)
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }

  async function toggleSchedule(action: 'install' | 'uninstall') {
    const wording = action === 'install' ? '创建每天 09:00 和 20:00 两个 Windows 计划任务' : '删除两个热点计划任务'
    if (!window.confirm(`确认${wording}？`)) return
    setBusy(`schedule-${action}`); setError('')
    try {
      const result = await request<TrendSchedule>(`/trends/schedule/${action}`, { method: 'POST', body: JSON.stringify({ confirm: true }) })
      setSchedule(result)
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }

  const latestRun = runs[0]
  return <div className="panel wide trend-panel">
    <div className="panel-title"><span>今日热点候选</span><small>{latestRun ? `${new Date(latestRun.started_at).toLocaleString('zh-CN')} · ${latestRun.data_status === 'sufficient' ? `${latestRun.candidate_count} 个候选` : '本次数据不足'}` : status?.tavily_configured ? '可手动刷新' : '等待公开来源或手工补充'}</small></div>
    <div className="trend-toolbar">
      <p>只提取公开来源中可转化为私人随笔的情绪内核；搜索结果数量和 Provider 分数都不会被当作真实平台热度。</p>
      <div><button className="ghost" disabled={!!busy} onClick={() => setShowManual(!showManual)}><Plus size={14} />补充话题或链接</button><button className="primary" disabled={!!busy || (!status?.deepseek_configured)} onClick={refresh}>{busy === 'refresh' ? <LoaderCircle className="spin" size={15} /> : <RotateCcw size={15} />}手动刷新</button></div>
    </div>
    {error && <div className="error-banner">{error}</div>}
    {latestRun?.error_summary && !error && <div className={latestRun.status === 'failed' ? 'error-banner' : 'trend-limit'}>{latestRun.error_summary}</div>}
    {candidates.length ? <div className="trend-cards">{candidates.map((candidate) => <article key={candidate.id}>
      <header><div>{candidate.source_platforms.map((platform) => <span key={platform}>{platform}</span>)}</div><small>{candidate.trend_signal} · {candidate.confidence}可信度</small></header>
      <h3>{candidate.title}</h3><p className="trend-angle">{candidate.female_emotional_angle}</p>
      <dl><dt>趋势依据</dt><dd>{candidate.trend_basis}</dd><dt>账号匹配</dt><dd>{candidate.account_fit}</dd><dt>同质化风险</dt><dd>{candidate.homogeneity_risk}</dd>{candidate.cultural_association && <><dt>文化联想</dt><dd>{candidate.cultural_association}</dd></>}<dt>数据边界</dt><dd>{candidate.data_limitations}</dd></dl>
      {candidate.source_links.length > 0 && <div className="trend-links">{candidate.source_links.map((link) => <a key={link.url} href={link.url} target="_blank" rel="noreferrer"><ExternalLink size={12} />{link.platform}来源</a>)}</div>}
      <button className="quality-button" disabled={!!busy} onClick={() => startFromCandidate(candidate)}>{busy === `use-${candidate.id}` ? <LoaderCircle className="spin" size={14} /> : <ChevronRight size={14} />}用这个选题开始写作</button>
    </article>)}</div> : <div className="empty-note"><Sparkles size={22} /><p>{latestRun ? '本次数据不足，没有硬凑候选。可补充一个公开话题或链接后再刷新。' : '还没有热点记录。配置 Tavily 后手动刷新，或先补充你看到的话题。'}</p></div>}
    {showManual && <form className="trend-manual-form" onSubmit={saveManual}>
      <label>补充类型<select value={sourceType} onChange={(e) => setSourceType(e.target.value as 'topic' | 'url')}><option value="topic">手工话题</option><option value="url">公开链接</option></select></label>
      <label>来源标签<input required maxLength={240} value={sourceLabel} onChange={(e) => setSourceLabel(e.target.value)} placeholder="例如：最近反复看到的讨论" /></label>
      <label>{sourceType === 'url' ? '公开链接（系统不会抓取登录内容）' : '话题或讨论摘要'}<textarea required maxLength={4000} value={sourceValue} onChange={(e) => setSourceValue(e.target.value)} /></label>
      <label className="confirm-line"><input type="checkbox" checked={sourceConfirmed} onChange={(e) => setSourceConfirmed(e.target.checked)} />我确认保存这条手工来源；未使用记录 30 天后清理</label>
      <button className="primary" disabled={!sourceConfirmed || !!busy}>{busy === 'manual' ? <LoaderCircle className="spin" size={14} /> : <Save size={14} />}保存手工来源</button>
      <section className="ocr-fallback">
        <header><strong>截图本地识别</strong><small>{ocrStatus?.available ? 'Windows 中文 OCR 可用' : ocrStatus?.reason || '正在检查本地 OCR'}</small></header>
        <p>图片只交给本机 Windows OCR，不发送到云端。识别后必须人工修正并确认；确认或放弃时原截图永久删除。</p>
        {!pendingOcr && <label className="ocr-file">选择 PNG/JPEG 截图<input aria-label="选择热点截图" type="file" accept="image/png,image/jpeg" disabled={!ocrStatus?.available || !!busy} onChange={(e) => uploadScreenshot(e.target.files?.[0])} /></label>}
        {busy === 'ocr-upload' && <span className="ocr-progress"><LoaderCircle className="spin" size={14} />正在本地识别，失败不会自动重试……</span>}
        {pendingOcr && <div className="ocr-review">
          <img src={`${API}/ocr/runs/${pendingOcr.id}/image`} alt="待确认的热点截图" />
          <label>来源标签<input required maxLength={240} value={ocrLabel} onChange={(e) => setOcrLabel(e.target.value)} /></label>
          <label>识别文字（请人工核对和修改）<textarea required maxLength={12000} value={ocrText} onChange={(e) => setOcrText(e.target.value)} /></label>
          <label className="confirm-line"><input type="checkbox" checked={ocrConfirmed} onChange={(e) => setOcrConfirmed(e.target.checked)} />我已核对文字，并确认保存为热点来源；保存后原截图永久删除</label>
          <div className="ocr-actions"><button type="button" className="primary" disabled={!ocrConfirmed || !ocrText.trim() || !ocrLabel.trim() || !!busy} onClick={confirmOcr}>{busy === 'ocr-confirm' && <LoaderCircle className="spin" size={14} />}确认并保存</button><button type="button" className="ghost" disabled={!!busy} onClick={discardOcr}>放弃并永久删除</button></div>
        </div>}
      </section>
      {manualSources.length > 0 && <div className="trend-manual-list">已保存：{manualSources.slice(0, 3).map((item) => item.label).join('、')}</div>}
    </form>}
    <div className="trend-schedule"><CalendarClock size={18} /><div><strong>Windows 计划任务 · 09:00 / 20:00</strong><small>{schedule?.missed_run_policy || '电脑关机或错过时不补跑。'} {schedule?.installed ? '当前已安装。' : '当前未安装。'}</small></div>{schedule?.supported && (schedule.installed ? <button className="ghost" disabled={!!busy} onClick={() => toggleSchedule('uninstall')}>卸载计划任务</button> : <button className="ghost" disabled={!!busy} onClick={() => toggleSchedule('install')}>安装计划任务</button>)}</div>
  </div>
}
