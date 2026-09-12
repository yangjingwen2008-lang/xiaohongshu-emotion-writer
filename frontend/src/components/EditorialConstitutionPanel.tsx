import { useEffect, useState } from 'react'
import { LoaderCircle, RotateCcw, Save, ShieldCheck } from 'lucide-react'
import type { ConstitutionSections, EditorialConstitution } from '../types'
import { request } from '../lib/api'
import { RuleDiff } from './RuleDiff'

const constitutionSectionLabels: Array<[keyof ConstitutionSections, string]> = [
  ['core_principles', '核心风格边界'],
  ['title_structure_rules', '标题与结构基线'],
  ['ai_tone_prohibitions', '明确禁止的 AI 腔'],
  ['evaluation_dimensions', '风格评估维度'],
]

export function EditorialConstitutionPanel() {
  const [constitution, setConstitution] = useState<EditorialConstitution | null>(null)
  const [versions, setVersions] = useState<EditorialConstitution[]>([])
  const [fields, setFields] = useState<Record<keyof ConstitutionSections, string>>({ core_principles: '', title_structure_rules: '', ai_tone_prohibitions: '', evaluation_dimensions: '' })
  const [editing, setEditing] = useState(false)
  const [changeNote, setChangeNote] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const lines = (value: string) => value.split('\n').map((item) => item.trim()).filter(Boolean)
  async function loadConstitution() {
    setError('')
    const [current, history] = await Promise.all([
      request<EditorialConstitution>('/editorial-constitution'),
      request<EditorialConstitution[]>('/editorial-constitution/versions'),
    ])
    setConstitution(current); setVersions(history)
    setFields(Object.fromEntries(Object.entries(current.sections).map(([key, value]) => [key, value.join('\n')])) as Record<keyof ConstitutionSections, string>)
  }
  useEffect(() => { void Promise.resolve().then(loadConstitution).catch((e) => setError((e as Error).message)) }, [])
  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy('save'); setError('')
    try {
      await request('/editorial-constitution', {
        method: 'POST',
        body: JSON.stringify({ sections: Object.fromEntries(constitutionSectionLabels.map(([key]) => [key, lines(fields[key])])), change_note: changeNote, confirm: confirmed }),
      })
      setEditing(false); setChangeNote(''); setConfirmed(false); await loadConstitution()
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  async function rollback(version: number) {
    if (!window.confirm(`确认恢复到编辑宪法 V${version}？系统会创建新版本，不会删除历史。`)) return
    setBusy(`rollback-${version}`); setError('')
    try {
      await request(`/editorial-constitution/rollback/${version}`, { method: 'POST', body: JSON.stringify({ confirm: true }) })
      await loadConstitution()
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  if (!constitution && error) return <section className="constitution-panel" role="alert"><p>{error}</p><button className="ghost" onClick={() => loadConstitution().catch((e) => setError((e as Error).message))}>重新读取编辑宪法</button></section>
  if (!constitution) return <section className="constitution-panel"><div className="empty-note"><LoaderCircle className="spin" size={18} /><p>正在读取编辑宪法……</p></div></section>
  return <section className="constitution-panel">
    <div className="panel-title"><span>编辑宪法</span><small>最高优先级 · 当前 V{constitution.version}</small></div>
    <p className="constitution-note"><ShieldCheck size={16} />所有写作、审阅和风格学习都受它约束；只有勾选人工确认后才能创建新版本。</p>
    {error && <div className="error-banner">{error}</div>}
    {!editing ? <>
      <div className="constitution-grid">{constitutionSectionLabels.map(([key, label]) => <div key={key}><h3>{label}</h3>{constitution.sections[key].map((rule) => <p key={rule}>{rule}</p>)}</div>)}</div>
      <div className="profile-actions"><small>{constitution.change_note}</small><button className="ghost" onClick={() => { setConfirmed(false); setChangeNote(''); setFields(Object.fromEntries(Object.entries(constitution.sections).map(([key, value]) => [key, value.join('\n')])) as Record<keyof ConstitutionSections, string>); setEditing(true) }}>编辑宪法</button></div>
    </> : <form className="constitution-editor" onSubmit={save}>
      {constitutionSectionLabels.map(([key, label]) => <label key={key}>{label}（每行一条）<textarea required value={fields[key]} onChange={(e) => setFields({ ...fields, [key]: e.target.value })} /></label>)}
      <label>本次变更说明<input required minLength={2} maxLength={500} value={changeNote} onChange={(e) => setChangeNote(e.target.value)} placeholder="说明为什么要修改这条最高优先级边界" /></label>
      <label className="confirm-line"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />我确认这些修改将成为后续写作与审阅的最高优先级边界</label>
      <div className="proposal-actions"><button type="button" className="ghost" onClick={() => setEditing(false)}>取消</button><button className="primary" disabled={!confirmed || !changeNote.trim() || !!busy}>{busy === 'save' ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />}确认并保存新版本</button></div>
    </form>}
    <div className="constitution-history"><div className="panel-title"><span>版本历史</span><small>{versions.length} 个可恢复版本</small></div>{versions.map((item) => <div className="profile-version-row" key={`constitution-${item.version}`}><span>V{item.version}</span><strong>{item.version === 0 ? '文档初始版' : item.change_type === 'rollback' ? '恢复版本' : '人工修改'}</strong><small>{item.change_note}{item.created_at ? ` · ${new Date(item.created_at).toLocaleString('zh-CN')}` : ''}</small>{item.version !== constitution.version && <button className="ghost" disabled={!!busy} onClick={() => rollback(item.version)}>{busy === `rollback-${item.version}` ? <LoaderCircle className="spin" size={14} /> : <RotateCcw size={14} />}恢复到此版本</button>}{item.version !== constitution.version && <RuleDiff current={Object.fromEntries(constitutionSectionLabels.map(([key, label]) => [label, constitution.sections[key]]))} previous={Object.fromEntries(constitutionSectionLabels.map(([key, label]) => [label, item.sections[key]]))} />}</div>)}</div>
  </section>
}
