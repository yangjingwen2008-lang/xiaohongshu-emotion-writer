import { useEffect, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import { Bold, Quote, Save } from 'lucide-react'
import { ActionButton } from './ActionButton'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'

export function RichEditor({ title, html, onSave }: { title: string; html: string; onSave: (title: string, bodyHtml: string, bodyText: string) => Promise<void> }) {
  const [titleEdit, setTitleEdit] = useState({ source: title, value: title })
  const draftTitle = titleEdit.source === title ? titleEdit.value : title
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [saved, setSaved] = useState(false)
  const editor = useEditor({ immediatelyRender: false, extensions: [StarterKit, Placeholder.configure({ placeholder: '从一个具体场景开始……' })], content: html, onUpdate: () => { setSaved(false); setFeedback('') } })
  useEffect(() => { editor?.setEditable(!saving, false) }, [editor, saving])
  useEffect(() => { if (editor && !editor.isDestroyed && editor.schema && html && editor.getHTML() !== html) editor.commands.setContent(html, { emitUpdate: false }) }, [html, editor])
  async function save() {
    if (!editor || saving) return
    setSaving(true); setFeedback(''); setSaved(false)
    try { await onSave(draftTitle, editor.getHTML(), editor.getText()); setFeedback('新版本已保存。'); setSaved(true) }
    catch (cause) { setFeedback((cause as Error).message) }
    finally { setSaving(false) }
  }
  return (
    <div className="editor-shell">
      <div className="editor-toolbar">
        <button disabled={saving} aria-label="加粗" aria-pressed={editor?.isActive('bold') || false} onClick={() => editor?.chain().focus().toggleBold().run()} className={editor?.isActive('bold') ? 'active' : ''}><Bold size={16} /></button>
        <button disabled={saving} aria-label="引用段落" aria-pressed={editor?.isActive('blockquote') || false} onClick={() => editor?.chain().focus().toggleBlockquote().run()} className={editor?.isActive('blockquote') ? 'active' : ''}><Quote size={16} /></button>
        <span />
        <ActionButton className="save" busy={saving} busyLabel="保存中…" success={saved} successLabel="已保存" disabled={!editor} onClick={save} icon={<Save size={15} />}>保存新版本</ActionButton>
      </div>
      {feedback && <p className="message editor-feedback" role="status">{feedback}</p>}
      <input aria-label="文章标题" disabled={saving} className="editor-title" value={draftTitle} onChange={(e) => { setTitleEdit({ source: title, value: e.target.value }); setSaved(false); setFeedback('') }} />
      <EditorContent editor={editor} className="editor-content" />
    </div>
  )
}
