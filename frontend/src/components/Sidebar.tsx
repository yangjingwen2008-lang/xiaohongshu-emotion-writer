import type { CSSProperties } from 'react'
import { BarChart3, BookOpen, Compass, FileText, Settings, ShieldCheck } from 'lucide-react'
import { RainMark } from './RainMark'

export function Sidebar({ page, setPage }: { page: string; setPage: (page: string) => void }) {
  const items = [
    ['home', Compass, '工作台'],
    ['drafts', FileText, '内容库'],
    ['style', BookOpen, '风格训练'],
    ['analytics', BarChart3, '复盘'],
    ['settings', Settings, '设置'],
  ] as const
  return (
    <aside className="sidebar">
      <button className="brand" onClick={() => setPage('home')}>
        <span className="brand-mark"><RainMark /></span>
        <span><strong>潮湿雨季</strong><small>情感随笔工作台</small></span>
      </button>
      <nav aria-label="主导航" style={{ '--nav-index': Math.max(0, items.findIndex(([key]) => key === page)), '--nav-visible': page === 'composer' ? 0 : 1 } as CSSProperties}>
        {items.map(([key, Icon, label]) => (
          <button key={key} aria-current={page === key ? 'page' : undefined} className={page === key ? 'active' : ''} onClick={() => setPage(key)}>
            <Icon size={18} /><span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-foot">
        <ShieldCheck size={17} />
        <span>本地保存<br /><small>不会自动发布</small></span>
      </div>
    </aside>
  )
}
