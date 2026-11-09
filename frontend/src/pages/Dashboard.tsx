import { useEffect, useState } from 'react'
import { ArrowRight, BarChart3, ChevronRight, FileText, PenLine, Plug } from 'lucide-react'
import type { Content, SetupStatus, Publication, DueSnapshot } from '../types'
import { request } from '../lib/api'
import { stringValue, useStoredState } from '../lib/preferences'
import { stepLabel } from '../lib/content'
import { CreateCard } from '../components/CreateCard'
import { TrendPanel } from '../components/TrendPanel'

export function Dashboard({ contents, status, onCreated, onOpen, onAnalytics, onSettings }: { contents: Content[]; status: SetupStatus | null; onCreated: (c: Content) => void; onOpen: (id: string) => void; onAnalytics: () => void; onSettings: () => void }) {
  const drafts = contents.filter((item) => item.status === 'draft' || item.status === 'pending_review').sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
  const [lastId] = useStoredState('chaoshi-yuji.last-content.v1', '', stringValue)
  const resume = contents.find((item) => item.id === lastId)
  const today = new Date()
  const [recentPublications, setRecentPublications] = useState<Publication[]>([])
  const [dueItems, setDueItems] = useState<DueSnapshot[]>([])
  useEffect(() => {
    Promise.all([request<Publication[]>('/publications'), request<DueSnapshot[]>('/publications/due')])
      .then(([publications, due]) => { setRecentPublications(publications); setDueItems(due) })
      .catch(() => undefined)
  }, [contents])
  return (
    <main className="page dashboard">
      <header className="desk-heading">
        <div><h1 id="desk-title">今天想写什么？</h1><p>从一段经历或一句还没写完的话开始。</p></div>
        <time className="desk-date" dateTime={`${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`}>
          <span>{today.getMonth() + 1} 月 {today.getDate()} 日</span><small>{today.toLocaleDateString('zh-CN', { weekday: 'long' })}</small>
        </time>
      </header>
      {resume && <div className="resume-strip"><FileText size={18} /><div><small>继续上次的文章 · {stepLabel(resume.current_step)}</small><strong>{resume.title || resume.theme}</strong></div><button className="ghost" onClick={() => onOpen(resume.id)}>继续查看<ChevronRight size={16} /></button></div>}
      <div className="desk-layout">
        <section className="writing-sheet" aria-label="开始创作">
          <header className="sheet-head"><span><PenLine size={17} />一篇新的随笔</span><small>文字从这里开始</small></header>
          <CreateCard onCreated={onCreated} />
          <footer className="sheet-foot"><span>主题与情绪</span><ArrowRight size={13} /><span>创作方案</span><ArrowRight size={13} /><span>编辑成篇</span></footer>
        </section>
        <section className="draft-shelf">
          <div className="panel-title"><h2>草稿与待审核</h2><small>{drafts.length} 篇</small></div>
          {drafts.length ? <div className="content-list">{drafts.slice(0, 3).map((item, index) => <button key={item.id} onClick={() => onOpen(item.id)}>
            <span><strong>{item.title || item.theme}</strong><small>{index === 0 ? '接着写 · ' : ''}{item.emotion} · {stepLabel(item.current_step)}</small></span><ChevronRight size={17} />
          </button>)}</div> : <div className="draft-empty"><FileText size={25} strokeWidth={1.3} /><p>这里还没有草稿</p><small>写下第一个念头，<br />下次回来可以接着写。</small></div>}
        </section>
      </div>
      {!(status?.writing_configured ?? status?.deepseek_configured) && <div className="desk-connection">
        <Plug size={17} /><p>连接写作服务后，就可以生成第一篇随笔。</p><button className="ghost" onClick={onSettings}>配置 API Key <ChevronRight size={15} /></button>
      </div>}
      <section className="dashboard-grid">
        <TrendPanel status={status} onCreated={onCreated} />
        <div className="publication-strip"><div className="panel-title"><h2>发布后的回声</h2><button className="text-button" onClick={onAnalytics}>查看复盘<ArrowRight size={15} /></button></div>
          {dueItems.length ? <div className="content-list">{dueItems.slice(0, 3).map((item) => <button key={`${item.publication_id}-${item.day_offset}`} onClick={onAnalytics}><span><strong>{item.final_title}</strong><small>第 {item.day_offset} 天数据待录入{item.overdue_days ? ` · 已逾期 ${item.overdue_days} 天` : ''}</small></span><BarChart3 size={17} /></button>)}</div>
            : <div className="publication-note"><BarChart3 size={22} strokeWidth={1.4} /><p>{recentPublications.length ? <><b>{recentPublications[0].final_title}</b><br />已保存 {recentPublications[0].snapshots.length} 个数据快照。</> : '发布后，在这里记录第 1、3、7 天的数据，回看文字引起的共鸣。'}</p><small>{recentPublications.length ? `${recentPublications.length} 篇已发布` : '还没有发布记录'}</small></div>}
        </div>
      </section>
    </main>
  )
}
