import { useEffect, useRef, useState, type CSSProperties, type RefObject } from 'react'
import { ArrowRight, RotateCcw } from 'lucide-react'

export const welcomeHoldMs = 2200
export const welcomeExitMs = 360

/** A finite rain → lettering → controls sequence, shared by first-run and repeat launches. */
export function WelcomeScene({ onEnter, automatic = false, brandOnly = false, titleRef }: {
  onEnter: () => void
  automatic?: boolean
  brandOnly?: boolean
  titleRef?: RefObject<HTMLHeadingElement | null>
}) {
  const [replay, setReplay] = useState(0)
  const [leaving, setLeaving] = useState(false)
  const entered = useRef(false)
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  const heading = brandOnly ? '潮湿雨季' : '欢迎'

  useEffect(() => {
    if (!automatic) return
    const timer = window.setTimeout(() => setLeaving(true), brandOnly ? 1600 : welcomeHoldMs)
    return () => window.clearTimeout(timer)
  }, [automatic, brandOnly, replay])

  useEffect(() => {
    if (!leaving) return
    const timer = window.setTimeout(() => {
      if (entered.current) return
      entered.current = true
      onEnter()
    }, reduceMotion ? 0 : welcomeExitMs)
    return () => window.clearTimeout(timer)
  }, [leaving, onEnter, reduceMotion])

  function enter() {
    if (entered.current || leaving) return
    if (reduceMotion) { entered.current = true; onEnter() }
    else setLeaving(true)
  }

  return <div className="welcome-scene" data-leaving={leaving || undefined} data-brand-only={brandOnly || undefined}>
    <div className="welcome-stage" key={replay}>
      <svg className="welcome-water" viewBox="0 0 600 230" fill="none" aria-hidden="true">
        <path className="welcome-drop" d="M300 22v25" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <circle className="welcome-impact" cx="300" cy="145" r="3" fill="currentColor" />
        {[0, 1, 2, 3, 4].map(index => <ellipse key={index} className="welcome-wave" cx="300" cy="145" rx={42 + index * 47} ry={12 + index * 13}
          stroke="currentColor" strokeWidth="1.2" style={{ '--wave-delay': `${330 + index * 105}ms`, '--wave-opacity': 0.65 - index * .08 } as CSSProperties} />)}
      </svg>
      <h1 className="welcome-title" id="opening-title" ref={titleRef} tabIndex={-1} aria-label={heading}>
        {Array.from(heading).map((character, index) => <span className="welcome-letter-window" key={index} aria-hidden="true">
          <span className="welcome-letter" style={{ '--letter-delay': `${400 + index * 150}ms` } as CSSProperties}>{character}</span>
        </span>)}
      </h1>
      <p className="welcome-caption">{brandOnly ? '情感随笔工作台' : '把今天留在纸上'}</p>
      {!brandOnly && <div className="welcome-actions">
        <button className="primary welcome-enter" disabled={leaving} onClick={enter}>进入工作台<ArrowRight size={16} /></button>
        <button className="welcome-replay" disabled={leaving} onClick={() => setReplay(value => value + 1)}><RotateCcw size={14} />重播动画</button>
      </div>}
    </div>
    {automatic && <button className="welcome-skip" disabled={leaving} onClick={enter}>跳过动画<ArrowRight size={14} /></button>}
  </div>
}
