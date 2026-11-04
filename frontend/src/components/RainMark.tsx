export function RainMark({ className = '' }: { className?: string }) {
  return <svg className={`rain-mark ${className}`} viewBox="0 0 48 48" width="36" height="36" fill="none" aria-hidden="true">
    <path className="rain-drop" d="M24 6v12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <ellipse className="rain-ring outer" cx="24" cy="31" rx="20" ry="9" stroke="currentColor" strokeWidth="1.3" />
    <ellipse className="rain-ring inner" cx="24" cy="31" rx="12" ry="5.5" stroke="currentColor" strokeWidth="1.3" />
    <circle className="rain-center" cx="24" cy="31" r="2" fill="currentColor" />
  </svg>
}
