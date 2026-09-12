import type { Content, OcrRun } from '../types'

export function latest(content: Content | null, type: string) {
  return [...(content?.artifacts || [])].reverse().find((item) => item.artifact_type === type)
}

export function stepLabel(step: string) {
  const labels: Record<string, string> = { idea_intake: '主题已保存', plan_selection: '等待选择方案', detail_enrichment: '补充一个细节', draft_generation: '准备生成正文', human_edit: '人工编辑' }
  return labels[step] || step
}

export function suggestedCommentText(run: OcrRun) {
  const suggested = run.engine_metadata?.suggested_comments
  if (Array.isArray(suggested) && suggested.length) {
    return suggested.map((item) => item.author_label ? `${item.author_label}：${item.text}` : item.text).join('\n')
  }
  return run.corrected_text || run.recognized_text || ''
}
