import { useState } from 'react'
import { ChevronRight, LoaderCircle, Plus } from 'lucide-react'
import type { Content } from '../types'
import { request } from '../lib/api'

export function CreateCard({ onCreated }: { onCreated: (content: Content) => void }) {
  const [theme, setTheme] = useState('')
  const [emotion, setEmotion] = useState('')
  const [extra, setExtra] = useState('')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (busy) return
    if (!theme.trim() || !emotion.trim()) { setError('请填写主题和主要情绪，不能只输入空格。'); return }
    setBusy(true); setError('')
    try {
      const content = await request<Content>('/contents', { method: 'POST', body: JSON.stringify({ theme: theme.trim(), emotion: emotion.trim(), extra_requirements: extra.trim() || null }) })
      onCreated(content)
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  if (!open) return (
    <button className="create-hero" onClick={() => setOpen(true)}>
      <span className="create-icon"><Plus size={23} /></span>
      <span><small>今日创作</small><strong>写下一个念头</strong><em>从主题与情绪开始</em></span>
      <ChevronRight />
    </button>
  )
  return (
    <form className="create-form" onSubmit={submit}>
      <div className="eyebrow">今日创作</div>
      {error && <p className="error-banner" role="alert">{error}</p>}
      <label>今日主题<input autoFocus required maxLength={240} value={theme} onChange={(e) => setTheme(e.target.value)} placeholder="例如：分开以后，我开始绕开那条街" /></label>
      <label>主要情绪<input required maxLength={120} value={emotion} onChange={(e) => setEmotion(e.target.value)} placeholder="例如：延迟性痛感、依恋、羞耻" /></label>
      <label>补充要求（可选）<textarea maxLength={2000} value={extra} onChange={(e) => setExtra(e.target.value)} placeholder="不想出现的意象、希望保留的语气……" /></label>
      <div className="row"><button type="button" className="ghost" onClick={() => setOpen(false)}>取消</button><button className="primary" disabled={busy}>{busy && <LoaderCircle className="spin" size={16} />}生成创作流程</button></div>
    </form>
  )
}
