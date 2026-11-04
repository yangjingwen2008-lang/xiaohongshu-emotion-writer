import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight } from 'lucide-react'
import type { SetupStatus } from '../types'
import { WritingConnection } from './WritingConnection'
import { RainPrint } from './RainPrint'
import { RainMark } from './RainMark'
import { WelcomeScene } from './WelcomeScene'

const slides = [
  { label: '起笔', title: '把说不清的，\n先写下来。', body: '潮湿雨季是一张写情感随笔的桌子。从一段经历、一个片段，或一种还没起名字的情绪开始。', mark: '雨' },
  { label: '成篇', title: '一篇文章，\n可以慢慢长出来。', body: '从选题到初稿，从改句子到做封面。每一步都可以自己判断，文章由你编辑，也由你决定何时发布。', mark: '稿' },
  { label: '连接', title: '选一个写作服务。', body: '填入所选供应商的 API Key 即可。也可以先进入工作台，之后在设置里连接。', mark: '笔' },
]

export function Opening({ status, onDone }: { status: SetupStatus; onDone: () => void }) {
  const [step, setStep] = useState(0)
  const [direction, setDirection] = useState('forward')
  const title = useRef<HTMLHeadingElement>(null)
  const touchStart = useRef<{ x: number; y: number } | null>(null)
  const slide = slides[step]

  useEffect(() => { title.current?.focus() }, [step])

  function move(next: number) {
    setDirection(next < step ? 'backward' : 'forward')
    setStep(next)
  }

  return <main className="opening" aria-labelledby="opening-title">
    <header className="opening-head"><span><RainMark />潮湿雨季</span>
      {slide && <button className="opening-skip" onClick={() => move(3)}>跳过引导</button>}
    </header>
    {slide ? <>
      <div className="opening-spread" key={step} data-direction={direction}
        onTouchStart={(event) => {
          const touch = event.touches[0]
          touchStart.current = { x: touch.clientX, y: touch.clientY }
        }}
        onTouchCancel={() => { touchStart.current = null }}
        onTouchEnd={(event) => {
          if (touchStart.current === null) return
          const touch = event.changedTouches[0]
          const delta = touch.clientX - touchStart.current.x
          const vertical = touch.clientY - touchStart.current.y
          touchStart.current = null
          if (Math.abs(vertical) > Math.abs(delta)) return
          if (delta < -65 && step < 2) move(step + 1)
          if (delta > 65 && step > 0) move(step - 1)
        }}>
        <div className="opening-copy">
          <h1 id="opening-title" ref={title} tabIndex={-1}>{slide.title}</h1>
          <p className="opening-body">{slide.body}</p>
          {step === 2 && <WritingConnection status={status} onSaved={() => move(3)} onboarding />}
        </div>
        <div className="opening-plate" data-plate={step} aria-hidden="true"><RainPrint /><span className="plate-character">{slide.mark}</span><small>潮湿雨季 · {slide.label}</small></div>
      </div>
      <footer className="opening-foot">
        <div className="opening-progress" aria-label={`第 ${step + 1} 步，共 3 步`}>
          {slides.map((item, index) => <button key={item.label} aria-label={item.label} aria-current={index === step ? 'step' : undefined} onClick={() => move(index)} />)}
        </div>
        <div className="opening-controls">
          {step > 0 && <button className="ghost" onClick={() => move(step - 1)}><ArrowLeft size={16} />上一步</button>}
          {step < 2 ? <button className="primary" onClick={() => move(step + 1)}>继续<ArrowRight size={16} /></button>
            : <button className="ghost" onClick={() => move(3)}>稍后配置<ArrowRight size={16} /></button>}
        </div>
      </footer>
    </> : <WelcomeScene onEnter={onDone} titleRef={title} />}
  </main>
}

export function LaunchMark({ onDone, returning }: { onDone: () => void; returning: boolean }) {
  return <main className="launch-mark" aria-label="启动欢迎页">
    <WelcomeScene automatic brandOnly={!returning} onEnter={onDone} />
  </main>
}
