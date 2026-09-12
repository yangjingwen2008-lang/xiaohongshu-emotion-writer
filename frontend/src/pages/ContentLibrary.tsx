import { useState } from 'react'
import { ChevronRight, FileText, Search } from 'lucide-react'
import type { Content } from '../types'
import { stepLabel } from '../lib/content'

export function ContentLibrary({ contents, onOpen, goHome }: { contents: Content[]; onOpen: (id: string) => void; goHome: () => void }) {
  const [status, setStatus] = useState('all')
  const [query, setQuery] = useState('')
  const filtered = contents.filter((item) => {
    const statusMatch = status === 'all' || item.status === status
    const queryMatch = !query || `${item.title || ''}${item.theme}${item.emotion}`.toLowerCase().includes(query.toLowerCase())
    return statusMatch && queryMatch
  })
  const tabs = [['all', '全部'], ['draft', '草稿'], ['pending_review', '待审核'], ['published', '已发布']]
  const label: Record<string, string> = { draft: '草稿', pending_review: '待审核', published: '已发布' }
  return (
    <main className="page library-page">
      <header className="library-head"><div><div className="eyebrow">内容资产</div><h1>内容库</h1><p>所有正式进入创作流程的文章，都可以从这里继续、查看和管理。</p></div><strong>{contents.length}<small>篇内容</small></strong></header>
      <div className="library-tools">
        <div className="library-tabs">{tabs.map(([key, text]) => <button key={key} aria-pressed={status === key} className={status === key ? 'active' : ''} onClick={() => setStatus(key)}>{text}</button>)}</div>
        <label className="library-search"><Search size={15} /><input aria-label="搜索内容" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索标题、主题或情绪" /></label>
      </div>
      {filtered.length ? <div className="library-list">{filtered.map((item) => <button key={item.id} onClick={() => onOpen(item.id)}><span className={`status-dot ${item.status}`} /><span className="library-main"><small>{label[item.status] || item.status} · {stepLabel(item.current_step)}</small><strong>{item.title || item.theme}</strong><em>{item.emotion}{item.title ? ` · ${item.theme}` : ''}</em></span><time>{new Date(item.updated_at).toLocaleDateString('zh-CN')}</time><ChevronRight size={18} /></button>)}</div> : <div className="library-empty"><FileText size={30} /><h2>{contents.length ? '没有符合条件的内容' : '内容库还是空的'}</h2><p>{contents.length ? '换一个状态或搜索词试试。' : '从一个主题和一种情绪开始，第一篇文章会出现在这里。'}</p>{!contents.length && <button className="primary" onClick={goHome}>返回工作台开始创作</button>}</div>}
    </main>
  )
}
