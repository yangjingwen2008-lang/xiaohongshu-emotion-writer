import { useEffect, useRef, useState } from 'react'
import { Search, X, FileText, ArrowUpRight } from 'lucide-react'
import type { Content } from '../types'

export function QuickOpen({ contents, onClose, onOpen, navigate }: { contents: Content[]; onClose: () => void; onOpen: (id: string) => void; navigate: (page: string) => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [index, setIndex] = useState(0)
  const needle = query.trim().toLocaleLowerCase()
  const pages = [['home', '工作台'], ['drafts', '内容库'], ['style', '风格训练'], ['analytics', '复盘'], ['settings', '设置']]
  const results = [
    ...pages.filter(([, name]) => !needle || name.includes(needle)).map(([id, title]) => ({ id: `page-${id}`, title, detail: '页面', run: () => navigate(id) })),
    ...contents.filter((c) => !needle || `${c.title ?? ''} ${c.theme} ${c.emotion}`.toLocaleLowerCase().includes(needle)).slice(0, 30).map((c) => ({ id: c.id, title: c.title || c.theme, detail: c.emotion, run: () => onOpen(c.id) })),
  ]
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    dialog.current?.showModal()
    input.current?.focus()
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = overflow; previous?.focus() }
  }, [])
  useEffect(() => { document.getElementById(`quick-result-${index}`)?.scrollIntoView?.({ block: 'nearest' }) }, [index])
  function choose(position: number) { if (results[position]) { onClose(); results[position].run() } }
  return <dialog ref={dialog} className="quick-dialog" aria-labelledby="quick-title" onCancel={onClose} onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
    <header><h2 id="quick-title">快速跳转</h2><button className="icon-button" aria-label="关闭快速跳转" onClick={onClose}><X size={18} /></button></header>
    <label className="quick-search"><Search size={18} /><input ref={input} autoFocus aria-label="搜索页面与文章" placeholder="搜索页面、标题、主题或情绪" value={query} onChange={(e) => { setQuery(e.target.value); setIndex(0) }} onKeyDown={(e) => {
      if (e.nativeEvent.isComposing) return
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); setIndex((old) => Math.max(0, Math.min(results.length - 1, old + (e.key === 'ArrowDown' ? 1 : -1)))) }
      if (e.key === 'Enter') { e.preventDefault(); choose(index) }
    }} role="combobox" aria-autocomplete="list" aria-controls="quick-results" aria-expanded="true" aria-activedescendant={results[index] ? `quick-result-${index}` : undefined} /></label>
    <div id="quick-results" role="listbox" aria-label="跳转结果" className="quick-results">{results.map((result, i) => <button role="option" aria-selected={i === index} id={`quick-result-${i}`} className={i === index ? 'selected' : ''} key={result.id} onClick={() => choose(i)}><FileText size={16} /><span><strong>{result.title}</strong><small>{result.detail}</small></span><ArrowUpRight size={16} /></button>)}</div>
    {!results.length && <p className="quick-empty">没有找到相关页面或文章，试试更短的关键词。</p>}
    <footer>↑ ↓ 选择 · Enter 打开 · Esc 关闭</footer>
  </dialog>
}
