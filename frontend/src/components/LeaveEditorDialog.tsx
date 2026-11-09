import { useEffect, useRef } from 'react'

export function LeaveEditorDialog({ onStay, onLeave }: { onStay: () => void; onLeave: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const stay = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    dialog.current?.showModal(); stay.current?.focus()
    return () => previous?.focus()
  }, [])
  return <dialog className="leave-dialog" ref={dialog} aria-labelledby="leave-title" aria-describedby="leave-description" onCancel={onStay}>
    <h2 id="leave-title">这篇文章还有未保存的修改</h2>
    <p id="leave-description">修改尚未保存为正式版本。你可以继续编辑，保存新版本后再离开。</p>
    <div className="settings-actions"><button ref={stay} className="primary" onClick={onStay}>继续编辑</button><button className="ghost" onClick={onLeave}>仍然离开</button></div>
  </dialog>
}
