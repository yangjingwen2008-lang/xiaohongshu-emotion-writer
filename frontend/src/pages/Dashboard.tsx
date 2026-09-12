import { useEffect, useState } from 'react'
import { BarChart3, ChevronRight, FileText } from 'lucide-react'
import type { Content, SetupStatus, Publication, DueSnapshot } from '../types'
import { request } from '../lib/api'
import { stepLabel } from '../lib/content'
import { CreateCard } from '../components/CreateCard'
import { TrendPanel } from '../components/TrendPanel'

export function Dashboard({ contents, status, onCreated, onOpen, onAnalytics }: { contents: Content[]; status: SetupStatus | null; onCreated: (c: Content) => void; onOpen: (id: string) => void; onAnalytics: () => void }) {
  const drafts = contents.filter((item) => item.status === 'draft' || item.status === 'pending_review')
  const [recentPublications, setRecentPublications] = useState<Publication[]>([])
  const [dueItems, setDueItems] = useState<DueSnapshot[]>([])
  useEffect(() => {
    Promise.all([request<Publication[]>('/publications'), request<DueSnapshot[]>('/publications/due')])
      .then(([publications, due]) => { setRecentPublications(publications); setDueItems(due) })
      .catch(() => undefined)
  }, [contents])
  return (
    <main className="page dashboard">
      <header className="page-header"><div><div className="eyebrow">{new Date().getFullYear()} · 写作日常</div><h1>今天想写什么？</h1><p>先把情绪放在桌上，不急着让它变成答案。</p></div><div className="date-block"><strong>{new Date().getDate()}</strong><span>{new Date().toLocaleDateString('zh-CN', { month: 'long', weekday: 'short' })}</span></div></header>
      <CreateCard onCreated={onCreated} />
      <section className="dashboard-grid">
        <TrendPanel status={status} onCreated={onCreated} />
        <div className="panel"><div className="panel-title"><span>草稿与待审核</span><small>{drafts.length} 篇</small></div>{drafts.length ? <div className="content-list">{drafts.slice(0, 4).map((item) => <button key={item.id} onClick={() => onOpen(item.id)}><span><strong>{item.title || item.theme}</strong><small>{item.emotion} · {stepLabel(item.current_step)}</small></span><ChevronRight size={17} /></button>)}</div> : <div className="empty-note"><FileText size={22} /><p>第一篇文章会从这里长出来。</p></div>}</div>
        <div className="panel wide"><div className="panel-title"><span>最近发布和数据表现</span><small>{dueItems.length ? `${dueItems.length} 项待录入` : recentPublications.length ? `${recentPublications.length} 篇已发布` : '尚无数据'}</small></div>{dueItems.length ? <div className="content-list">{dueItems.slice(0, 4).map((item) => <button key={`${item.publication_id}-${item.day_offset}`} onClick={onAnalytics}><span><strong>{item.final_title}</strong><small>第 {item.day_offset} 天数据待录入{item.overdue_days ? ` · 已逾期 ${item.overdue_days} 天` : ''}</small></span><BarChart3 size={17} /></button>)}</div> : recentPublications.length ? <div className="metric-empty"><div>{recentPublications[0].snapshots.length.toString().padStart(2, '0')}</div><p><b>{recentPublications[0].final_title}</b><br />已保存 {recentPublications[0].snapshots.length} 个数据快照；后续到期项目会显示在这里。</p></div> : <div className="metric-empty"><div>01</div><p>手动发布后粘贴笔记链接，系统会在第 1、3、7 天保存独立数据快照。</p></div>}</div>
      </section>
    </main>
  )
}
