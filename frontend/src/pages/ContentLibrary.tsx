import { useState } from 'react'
import { ChevronRight, FileText, Search, Star, List, LayoutGrid, X, Plus } from 'lucide-react'
import type { Content } from '../types'
import { stepLabel } from '../lib/content'
import { stringIds, stringValue, useStoredState } from '../lib/preferences'

const tabs = [['all', '全部'], ['draft', '草稿'], ['pending_review', '待审核'], ['published', '已发布']]
const labels: Record<string, string> = { draft: '草稿', pending_review: '待审核', published: '已发布' }
export function ContentLibrary({ contents, onOpen, goHome }: { contents: Content[]; onOpen: (id: string) => void; goHome: () => void }) {
  const [status, setStatus] = useState('all')
  const [query, setQuery] = useState('')
  const [emotion, setEmotion] = useState('')
  const [onlyStarred, setOnlyStarred] = useState(false)
  const [stars, setStars] = useStoredState('chaoshi-yuji.starred.v1', [], stringIds)
  const [view, setView] = useStoredState<string>('chaoshi-yuji.library-view.v1', 'list', (v) => v === 'grid' ? 'grid' : 'list')
  const [sort, setSort] = useStoredState<string>('chaoshi-yuji.library-sort.v1', 'recent', (v) => v === 'oldest' || v === 'title' ? v : 'recent')
  const [lastOpened] = useStoredState('chaoshi-yuji.last-content.v1', '', stringValue)
  const resume = contents.find((c) => c.id === lastOpened)
  const needle = query.trim().toLocaleLowerCase()
  const filtered = contents.filter((item) => (status === 'all' || item.status === status)
    && (!emotion || item.emotion === emotion) && (!onlyStarred || stars.includes(item.id))
    && (!needle || `${item.title || ''} ${item.theme} ${item.emotion}`.toLocaleLowerCase().includes(needle)))
    .sort((a, b) => sort === 'title' ? (a.title || a.theme).localeCompare(b.title || b.theme, 'zh-CN') : (sort === 'oldest' ? 1 : -1) * (Date.parse(a.updated_at) - Date.parse(b.updated_at)))
  const emotions = [...new Set(contents.map((c) => c.emotion).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN'))
  function reset() { setStatus('all'); setQuery(''); setEmotion(''); setOnlyStarred(false) }
  const hasFilters = status !== 'all' || !!query || !!emotion || onlyStarred
  return <main className="page library-page">
    <header className="library-head"><div><h1>内容库</h1><p>整理每一次起笔，接着上次的思路写下去。</p></div><button className="primary" onClick={goHome}><Plus size={16} />开始新稿</button></header>
    {resume && <div className="resume-strip"><FileText size={18} /><div><small>上次打开</small><strong>{resume.title || resume.theme}</strong></div><button className="ghost" onClick={() => onOpen(resume.id)}>继续查看<ChevronRight size={16} /></button></div>}
    <div className="library-tools">
      <div className="library-tabs" aria-label="内容状态">{tabs.map(([key, label]) => <button key={key} aria-pressed={status === key} className={status === key ? 'active' : ''} onClick={() => setStatus(key)}>{label}<span className="tab-count">{key === 'all' ? contents.length : contents.filter((c) => c.status === key).length}</span></button>)}</div>
      <label className="library-search"><Search size={16} /><input aria-label="搜索内容" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索标题、主题或情绪" />{query && <button aria-label="清空搜索" className="icon-button" onClick={() => setQuery('')}><X size={15} /></button>}</label>
    </div>
    <div className="library-filters">
      <button className={`ghost favorite-filter ${onlyStarred ? 'active' : ''}`} aria-pressed={onlyStarred} onClick={() => setOnlyStarred(!onlyStarred)}><Star size={15} />收藏</button>
      <label>情绪<select value={emotion} onChange={(e) => setEmotion(e.target.value)}><option value="">全部情绪</option>{emotions.map((item) => <option key={item}>{item}</option>)}</select></label>
      <label>排序<select value={sort} onChange={(e) => setSort(e.target.value)}><option value="recent">最近更新</option><option value="oldest">最早更新</option><option value="title">标题顺序</option></select></label>
      <div className="view-switch" role="group" aria-label="内容视图"><button className="icon-button" aria-label="列表视图" aria-pressed={view === 'list'} onClick={() => setView('list')}><List size={18} /></button><button className="icon-button" aria-label="卡片视图" aria-pressed={view === 'grid'} onClick={() => setView('grid')}><LayoutGrid size={18} /></button></div>
    </div>
    <div className="library-result-summary"><span role="status">显示 {filtered.length} / {contents.length} 篇</span>{hasFilters && <button className="text-button" onClick={reset}>清除筛选</button>}<small>收藏与视图偏好保存在当前浏览器</small></div>
    {filtered.length ? <div className={`content-catalog ${view}`}>{filtered.map((item) => <article key={item.id}>
      <button className="catalog-open" aria-label={`打开文章：${item.title || item.theme}`} onClick={() => onOpen(item.id)}><span className="catalog-meta"><span className={`status-dot ${item.status}`} />{labels[item.status] || item.status} · {stepLabel(item.current_step)}</span><strong>{item.title || item.theme}</strong><span className="catalog-description">{item.emotion}{item.title ? ` · ${item.theme}` : ''}</span><time dateTime={item.updated_at}>{new Date(item.updated_at).toLocaleDateString('zh-CN')} 更新</time></button>
      <button className="icon-button catalog-star" aria-label={`${stars.includes(item.id) ? '取消收藏' : '收藏'}：${item.title || item.theme}`} aria-pressed={stars.includes(item.id)} onClick={() => setStars((old) => old.includes(item.id) ? old.filter((id) => id !== item.id) : [...old, item.id])}><Star size={17} fill={stars.includes(item.id) ? 'currentColor' : 'none'} /></button>
    </article>)}</div> : <div className="library-empty"><FileText size={30} /><h2>{contents.length ? '没有符合条件的内容' : '内容库还是空的'}</h2><p>{contents.length ? '调整筛选条件，或清除筛选查看全部文章。' : '从一个主题和一种情绪开始，第一篇文章会出现在这里。'}</p><button className="primary" onClick={contents.length ? reset : goHome}>{contents.length ? '查看全部内容' : '返回工作台开始创作'}</button></div>}
  </main>
}
