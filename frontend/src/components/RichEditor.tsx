import { useEffect, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import { LoaderCircle, Save } from 'lucide-react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'

export function RichEditor({ title, html, onSave }: { title: string; html: string; onSave: (title: string, bodyHtml: string, bodyText: string) => Promise<void> }) {
  const [titleEdit, setTitleEdit] = useState({ source: title, value: title })
  const draftTitle = titleEdit.source === title ? titleEdit.value : title
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState('')
  const editor = useEditor({ immediatelyRender: false, extensions: [StarterKit, Placeholder.configure({ placeholder: '从一个具体场景开始……' })], content: html })
  useEffect(() => { if (editor && !editor.isDestroyed && editor.schema && html && editor.getHTML() !== html) editor.commands.setContent(html) }, [html, editor])
  async function save() {
    if (!editor || saving) return
    setSaving(true); setFeedback('')
    try { await onSave(draftTitle, editor.getHTML(), editor.getText()); setFeedback('新版本已保存。') }
    catch (cause) { setFeedback((cause as Error).message) }
    finally { setSaving(false) }
  }
  return (
    <div className="editor-shell">
      <div className="editor-toolbar">
        <button aria-label="加粗" aria-pressed={editor?.isActive('bold') || false} onClick={() => editor?.chain().focus().toggleBold().run()} className={editor?.isActive('bold') ? 'active' : ''}>B</button>
        <button aria-label="引用段落" onClick={() => editor?.chain().focus().toggleBlockquote().run()}>“</button>
        <span />
        <button className="save" disabled={saving || !editor} onClick={save}>{saving ? <LoaderCircle className="spin" size={15} /> : <Save size={15} />}保存新版本</button>
      </div>
      {feedback && <p className="message editor-feedback" role="status">{feedback}</p>}
      <input aria-label="文章标题" className="editor-title" value={draftTitle} onChange={(e) => setTitleEdit({ source: title, value: e.target.value })} />
      <EditorContent editor={editor} className="editor-content" />
    </div>
  )
}
