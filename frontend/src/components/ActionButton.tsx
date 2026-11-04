import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Check, LoaderCircle } from 'lucide-react'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  busy?: boolean
  busyLabel?: string
  success?: boolean
  successLabel?: string
  icon?: ReactNode
}

/** Shared feedback for actions that wait on a service or save an article. */
export function ActionButton({ busy = false, busyLabel = '处理中…', success = false, successLabel,
  icon, children, className = 'primary', disabled, ...props }: Props) {
  const state = busy ? 'busy' : success ? 'success' : 'idle'
  return <button {...props} className={`${className} action-button`} disabled={disabled || busy}
    aria-busy={busy} data-state={state}>
    <span className="action-icon" key={state} aria-hidden="true">
      {busy ? <LoaderCircle className="spin" size={16} /> : success ? <Check className="action-check" size={16} /> : icon}
    </span>
    <span className="action-label-grid">
      <span className="action-label-reserve" aria-hidden="true">{children}</span>
      <span className="action-label-reserve" aria-hidden="true">{busyLabel}</span>
      {successLabel && <span className="action-label-reserve" aria-hidden="true">{successLabel}</span>}
      <span aria-live="polite">{busy ? busyLabel : success && successLabel ? successLabel : children}</span>
    </span>
  </button>
}
