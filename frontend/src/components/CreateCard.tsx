import { useEffect, useState } from 'react'
import { ArrowUpRight, ChevronRight, Plus } from 'lucide-react'
import { ActionButton } from './ActionButton'
import type { Content } from '../types'
import { request } from '../lib/api'

const ideaKey = 'chaoshi-yuji.unfiled-idea.v1'

function readIdea(): { theme?: string; emotion?: string; extra?: string } {
  try { return JSON.parse(localStorage.getItem(ideaKey) ?? '{}') ?? {} }
  catch { return {} }
}

export function CreateCard({ onCreated }: { onCreated: (content: Content) => void }) {
  const [idea] = useState(readIdea)
  const [theme, setTheme] = useState(idea.theme ?? '')
  const [emotion, setEmotion] = useState(idea.emotion ?? '')
  const [extra, setExtra] = useState(idea.extra ?? '')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const hasIdea = !!(theme.trim() || emotion.trim() || extra.trim())

  useEffect(() => {
    if (!open) return
    try {
      if (hasIdea) localStorage.setItem(ideaKey, JSON.stringify({ theme, emotion, extra }))
      else localStorage.removeItem(ideaKey)
    } catch { /* Local storage is optional. */ }
  }, [open, hasIdea, theme, emotion, extra])

  function discard() {
    try { localStorage.removeItem(ideaKey) } catch { /* Local storage is optional. */ }
    setTheme(''); setEmotion(''); setExtra(''); setError(''); setOpen(false)
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (busy) return
    if (!theme.trim() || !emotion.trim()) { setError('请填写主题和主要情绪，不能只输入空格。'); return }
    setBusy(true); setError('')
    try {
      const content = await request<Content>('/contents', { method: 'POST', body: JSON.stringify({ theme: theme.trim(), emotion: emotion.trim(), extra_requirements: extra.trim() || null }) })
      discard()
      onCreated(content)
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  if (!open) return (
    <button className="create-hero" data-has-idea={hasIdea || undefined} onClick={() => setOpen(true)}>
      <span className="create-icon"><Plus size={23} /></span>
      <span><strong>{hasIdea ? '继续上次的念头' : '写下一个念头'}</strong><em>{hasIdea ? theme || emotion || '未建稿的内容已暂存在本浏览器' : '一段经历，一种情绪，一句没说完的话。'}</em></span>
      <ChevronRight />
    </button>
  )
  return (
    <form className="create-form" onSubmit={submit} aria-busy={busy}>
      {error && <p className="error-banner" role="alert">{error}</p>}
      <label>今日主题<input autoFocus required disabled={busy} maxLength={240} value={theme} onChange={(e) => setTheme(e.target.value)} placeholder="例如：分开以后，我开始绕开那条街" /></label>
      <label>主要情绪<input required disabled={busy} maxLength={120} value={emotion} onChange={(e) => setEmotion(e.target.value)} placeholder="例如：延迟性痛感、依恋、羞耻" /></label>
      <label>补充要求（可选）<textarea disabled={busy} maxLength={2000} value={extra} onChange={(e) => setExtra(e.target.value)} placeholder="不想出现的意象、希望保留的语气……" /></label>
      <p className="connection-note">建稿前的输入暂存在本浏览器，建稿后归入内容库。</p>
      <div className="row"><button type="button" className="ghost" disabled={busy || !hasIdea} onClick={discard}>清除暂存</button><button type="button" className="ghost" disabled={busy} onClick={() => setOpen(false)}>收起</button><ActionButton busy={busy} busyLabel="正在建立草稿…" icon={<ArrowUpRight size={16} />}>生成创作流程</ActionButton></div>
    </form>
  )
}
