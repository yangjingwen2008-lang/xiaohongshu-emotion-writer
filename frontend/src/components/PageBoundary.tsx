import { Component } from 'react'
import type { ReactNode } from 'react'

export class PageBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() { return { failed: true } }

  render() {
    if (this.state.failed) return <main className="page" role="alert">
      <h1>这个页面暂时无法打开</h1>
      <p>你可以切换到其他页面，或重新加载工作台。重新加载会丢失尚未保存的输入。</p>
      <button className="primary" onClick={() => window.location.reload()}>重新加载</button>
    </main>
    return this.props.children
  }
}
