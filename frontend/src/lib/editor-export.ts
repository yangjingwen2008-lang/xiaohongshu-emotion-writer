type Node = { type?: string; text?: string; attrs?: Record<string, unknown>; marks?: { type: string; attrs?: Record<string, unknown> }[]; content?: Node[] }
const escape = (value: string) => value.replace(/([\\`*_{}[\]<>#!|])/g, '\\$1')
function serialize(node: Node): string {
  if (node.type === 'text') {
    if (node.marks?.some((m) => m.type === 'code')) {
      const raw = node.text || ''
      const fence = '`'.repeat(Math.max(0, ...(raw.match(/`+/g) || []).map((s) => s.length)) + 1)
      return `${fence} ${raw} ${fence}`
    }
    let text = escape(node.text || '')
    for (const mark of node.marks || []) {
      if (mark.type === 'bold') text = `**${text}**`
      if (mark.type === 'italic') text = `*${text}*`
      if (mark.type === 'strike') text = `~~${text}~~`
      if (mark.type === 'link' && typeof mark.attrs?.href === 'string' && /^(https?:|mailto:)/i.test(mark.attrs.href)) text = `[${text}](<${mark.attrs.href.replace(/[<>\r\n]/g, '')}>)`
    }
    return text
  }
  const children = (node.content || []).map(serialize).join('')
  switch (node.type) {
    case 'heading': return `${'#'.repeat(Math.max(1, Math.min(6, Number(node.attrs?.level) || 2)))} ${children}\n\n`
    case 'paragraph': return `${children}\n\n`
    case 'hardBreak': return '  \n'
    case 'horizontalRule': return '\n---\n\n'
    case 'blockquote': return `${children.trimEnd().split('\n').map((line) => `> ${line}`).join('\n')}\n\n`
    case 'bulletList': case 'orderedList': return (node.content || []).map((child, i) => {
      const prefix = node.type === 'orderedList' ? `${(Number(node.attrs?.start) || 1) + i}. ` : '- '
      return serialize(child).trimEnd().split('\n').map((line, n) => (n ? ' '.repeat(prefix.length) : prefix) + line).join('\n')
    }).join('\n') + '\n\n'
    case 'codeBlock': {
      const raw = (node.content || []).map((n) => n.text || '').join('')
      const fence = '`'.repeat(Math.max(2, ...(raw.match(/`+/g) || []).map((s) => s.length)) + 1)
      return `${fence}\n${raw}\n${fence}\n\n`
    }
    default: return children
  }
}
export function markdownDocument(title: string, document: Node) { return `# ${escape(title.replace(/[\r\n]+/g, ' '))}\n\n${serialize(document).trimEnd()}\n` }
