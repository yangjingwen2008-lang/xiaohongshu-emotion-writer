import { useEffect, useRef, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import { Bold, Quote, Save, Heading2, Undo2, Redo2, Copy, Download, Maximize2, Minimize2, SlidersHorizontal, List } from 'lucide-react'
import { ActionButton } from './ActionButton'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import { ReadingPreferences } from './ReadingPreferences'
import { usePreferences, paperStyle } from '../lib/preferences'
import { markdownDocument } from '../lib/editor-export'

type Recovery = { title: string; html: string; savedAt: string }
export function RichEditor({ title, html, onSave, contentId, onDirtyChange }: { title: string; html: string; onSave: (title: string, bodyHtml: string, bodyText: string) => Promise<void>; contentId?: string; onDirtyChange?: (dirty: boolean) => void }) {
  const [draftTitle, setDraftTitle] = useState(title)
  const titleRef = useRef(title)
  const baseline = useRef({ title, html })
  const dirtyRef = useRef(false)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)
  const [feedback, setFeedback] = useState('')
  const [saved, setSaved] = useState(false)
  const [focused, setFocused] = useState(false)
  const [showAppearance, setShowAppearance] = useState(false)
  const [count, setCount] = useState(0)
  const [, updateToolbar] = useState(0)
  const [prefs] = usePreferences()
  const recoveryKey = contentId ? `chaoshi-yuji.recovery.${contentId}` : ''
  const [recovery, setRecovery] = useState<Recovery | null>(() => {
    try {
      const value = JSON.parse(localStorage.getItem(recoveryKey) || 'null')
      return value && typeof value.title === 'string' && typeof value.html === 'string' && (value.title !== title || value.html !== html) ? value : null
    } catch { return null }
  })
  const [recoveryState, setRecoveryState] = useState('')
  function removeRecovery() { try { if (recoveryKey) localStorage.removeItem(recoveryKey) } catch { /* Optional recovery storage. */ } }
  function track(body: string, text: string) {
    const changed = titleRef.current !== baseline.current.title || body !== baseline.current.html
    dirtyRef.current = changed; setDirty(changed); onDirtyChange?.(changed)
    setSaved(false); setFeedback('')
    setCount(Array.from(text.replace(/\s/g, '')).length)
    if (!changed) { if (!recovery) removeRecovery(); return }
    if (recoveryKey && !recovery) {
      try {
        localStorage.setItem(recoveryKey, JSON.stringify({ title: titleRef.current, html: body, savedAt: new Date().toISOString() }))
        setRecoveryState('临时修改已备份到当前浏览器')
      } catch { setRecoveryState('浏览器无法暂存，请及时保存新版本') }
    }
  }
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [StarterKit, Placeholder.configure({ placeholder: '从一个具体场景开始……' })], content: html,
    editorProps: { attributes: { role: 'textbox', 'aria-label': '文章正文', 'aria-multiline': 'true' } },
    onCreate: ({ editor: instance }) => {
      baseline.current.html = instance.getHTML()
      setCount(Array.from(instance.getText().replace(/\s/g, '')).length)
    },
    onUpdate: ({ editor: instance }) => track(instance.getHTML(), instance.getText()),
    onSelectionUpdate: () => updateToolbar((v) => v + 1),
  })
  useEffect(() => { editor?.setEditable(!saving && !recovery, false) }, [editor, saving, recovery])
  useEffect(() => {
    if (!editor || editor.isDestroyed || dirtyRef.current || savingRef.current) return
    if (editor.getHTML() !== html) editor.commands.setContent(html, { emitUpdate: false })
    baseline.current = { title, html: editor.getHTML() }
    titleRef.current = title; setDraftTitle(title)
    setCount(Array.from(editor.getText().replace(/\s/g, '')).length)
  }, [title, html, editor])
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => { if (dirtyRef.current || savingRef.current) { event.preventDefault(); event.returnValue = '' } }
    window.addEventListener('beforeunload', beforeUnload)
    return () => { window.removeEventListener('beforeunload', beforeUnload); onDirtyChange?.(false) }
  }, [onDirtyChange])
  async function save() {
    if (!editor || recovery || savingRef.current || !dirtyRef.current) return
    savingRef.current = true; setSaving(true); setFeedback(''); setSaved(false)
    const body = editor.getHTML()
    try {
      await onSave(titleRef.current, body, editor.getText())
      baseline.current = { title: titleRef.current, html: body }
      dirtyRef.current = false; setDirty(false); onDirtyChange?.(false)
      removeRecovery(); setRecovery(null); setRecoveryState(''); setFeedback('新版本已保存。'); setSaved(true)
    } catch (cause) { setFeedback((cause as Error).message) }
    finally { savingRef.current = false; setSaving(false) }
  }
  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      if (event.isComposing) return
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); void save() }
      if (event.key === 'Escape' && focused) { setFocused(false); document.getElementById('editor-focus-toggle')?.focus() }
    }
    window.addEventListener('keydown', keydown)
    return () => window.removeEventListener('keydown', keydown)
  })
  useEffect(() => {
    if (!focused) return
    const y = window.scrollY
    document.getElementById('editor-focus-toggle')?.scrollIntoView?.({ block: 'start' })
    return () => window.scrollTo?.({ top: y })
  }, [focused])
  async function copyText() {
    if (!editor) return
    try { await navigator.clipboard.writeText(`${titleRef.current}\n\n${editor.getText({ blockSeparator: '\n\n' })}`); setFeedback('标题与正文已复制。') }
    catch { setFeedback('复制失败，请选中正文手动复制。') }
  }
  function download() {
    if (!editor) return
    const url = URL.createObjectURL(new Blob([markdownDocument(titleRef.current, editor.getJSON())], { type: 'text/markdown;charset=utf-8' }))
    const a = document.createElement('a'); a.href = url; a.download = `${Array.from(titleRef.current || '随笔').map((char) => char.charCodeAt(0) < 32 || '<>:"/\\|?*'.includes(char) ? '_' : char).join('').slice(0, 80)}.md`
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    setFeedback('已导出当前文稿 Markdown，未自动提交审核。')
  }
  function restore() {
    if (!editor || !recovery) return
    titleRef.current = recovery.title; setDraftTitle(recovery.title)
    editor.commands.setContent(recovery.html, { emitUpdate: false }); setRecovery(null)
    dirtyRef.current = true; setDirty(true); onDirtyChange?.(true)
    setCount(Array.from(editor.getText().replace(/\s/g, '')).length)
    setFeedback('已恢复临时修改，请核对后保存新版本。')
  }
  return <div className={`editor-shell paper-surface${focused ? ' is-focused' : ''}`} data-paper={prefs.paper} style={paperStyle(prefs)}>
    <div className="editor-toolbar">
      <div className="format-tools" role="group" aria-label="正文格式">
        <button disabled={saving || !!recovery} aria-label="加粗" aria-pressed={editor?.isActive('bold') || false} onClick={() => editor?.chain().focus().toggleBold().run()}><Bold size={16} /></button>
        <button disabled={saving || !!recovery} aria-label="二级标题" aria-pressed={editor?.isActive('heading', { level: 2 }) || false} onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()}><Heading2 size={16} /></button>
        <button disabled={saving || !!recovery} aria-label="引用段落" aria-pressed={editor?.isActive('blockquote') || false} onClick={() => editor?.chain().focus().toggleBlockquote().run()}><Quote size={16} /></button>
        <button disabled={saving || !!recovery} aria-label="项目列表" aria-pressed={editor?.isActive('bulletList') || false} onClick={() => editor?.chain().focus().toggleBulletList().run()}><List size={16} /></button>
        <button disabled={saving || !!recovery || !editor?.can().undo()} aria-label="撤销" onClick={() => editor?.chain().focus().undo().run()}><Undo2 size={16} /></button>
        <button disabled={saving || !!recovery || !editor?.can().redo()} aria-label="重做" onClick={() => editor?.chain().focus().redo().run()}><Redo2 size={16} /></button>
      </div>
      <div className="editor-view-tools">
        <button aria-label="调整阅读排版" aria-expanded={showAppearance} onClick={() => setShowAppearance(!showAppearance)}><SlidersHorizontal size={16} /></button>
        <button id="editor-focus-toggle" aria-label={focused ? '退出专注模式' : '进入专注模式'} aria-pressed={focused} onClick={() => setFocused(!focused)}>{focused ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</button>
        <ActionButton className="save" busy={saving} busyLabel="保存中…" success={saved} successLabel="已保存" disabled={!editor || !dirty} onClick={save} icon={<Save size={15} />}>保存新版本</ActionButton>
      </div>
    </div>
    {showAppearance && <div className="editor-appearance"><ReadingPreferences preview={false} /></div>}
    {recovery && <div className="recovery-notice" role="status"><p>发现这篇文章未保存的临时修改。恢复后可以核对，再另存为新版本。</p><button className="ghost" onClick={restore}>恢复临时修改</button><button className="text-button" onClick={() => { removeRecovery(); setRecovery(null); setFeedback('已保留服务器上的版本。') }}>使用已保存版本</button></div>}
    {feedback && <p className="message editor-feedback" role="status">{feedback}</p>}
    <input aria-label="文章标题" disabled={saving || !!recovery} className="editor-title" value={draftTitle} onChange={(e) => { titleRef.current = e.target.value; setDraftTitle(e.target.value); if (editor) track(editor.getHTML(), editor.getText()) }} />
    <EditorContent editor={editor} className="editor-content" />
    <footer className="editor-status"><span>{count} 字 · 约 {Math.max(1, Math.ceil(count / 400))} 分钟阅读</span><span>{saving ? '正在保存…' : dirty ? '有未保存的修改' : '已与保存版本同步'}</span><div><button className="text-button" disabled={!editor} onClick={() => void copyText()}><Copy size={14} />复制全文</button><button className="text-button" disabled={!editor} onClick={download}><Download size={14} />导出 Markdown</button></div></footer>
    {dirty && recoveryState && <p className="editor-recovery-status">{recoveryState}</p>}
  </div>
}
