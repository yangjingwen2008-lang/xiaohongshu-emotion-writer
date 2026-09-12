import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

describe('App', () => {
  afterEach(() => cleanup())

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      let data: any = []
      if (url.includes('/setup/status')) data = { deepseek_configured: true, tavily_configured: false, deepseek_model: 'deepseek-v4-flash' }
      else if (url.includes('/plugins/manifests')) data = [{ registry_version: 0, change_type: 'builtin', activation_mode: 'builtin_adapter', manifest: { plugin_id: 'local-export', name: 'Local Export Provider', version: '1.0.0', provider_type: 'ExportProvider', source_repo: 'builtin://export', pinned_ref: 'workspace', license: 'project-internal', maintenance_status: 'maintained', permissions: ['write:exports/packages'], allowed_domains: [], read_dirs: ['data/content'], write_dirs: ['exports/packages'], secret_names: [], needs_secret: false, retention: 'local', timeout_seconds: 30, health_check: 'export smoke test', rollback_version: 'builtin', enabled: true, built_in: true, tools: [] } }]
      else if (url.includes('/plugins/assessments')) data = []
      else if (url.includes('/trends/schedule/status')) data = { supported: true, installed: false, times: ['09:00', '20:00'], missed_run_policy: '电脑关机或错过时不补跑，等待下一次计划时间。' }
      else if (url.includes('/trends/')) data = []
      else if (url.includes('/ocr/status')) data = { available: true, provider: 'windows-media-ocr', local_only: true, languages: ['zh-Hans-CN'], retention: '确认后删除' }
      else if (url.includes('/ocr/runs')) data = []
      else if (url.includes('/editorial-constitution/versions')) data = [{ version: 0, change_type: 'initial', change_note: '文档内置初始编辑宪法', sections: { core_principles: ['用具体场景承载抽象情绪'], title_structure_rules: ['正文默认 600 至 900 字'], ai_tone_prohibitions: ['避免强行治愈'], evaluation_dimensions: ['具体性'] } }]
      else if (url.includes('/editorial-constitution')) data = { version: 0, change_type: 'initial', change_note: '文档内置初始编辑宪法', sections: { core_principles: ['用具体场景承载抽象情绪'], title_structure_rules: ['正文默认 600 至 900 字'], ai_tone_prohibitions: ['避免强行治愈'], evaluation_dimensions: ['具体性'] } }
      else if (url.includes('/style-training/profile/versions')) data = []
      else if (url.includes('/style-training/profile')) data = { version: 0, change_type: 'initial', rules: { core_rules: [], confirmed_training: [] } }
      return { ok: true, json: async () => data } as Response
    }))
  })

  it('renders the local writing dashboard', async () => {
    render(<App />)
    await waitFor(() => expect(screen.getByText('今天想写什么？')).toBeInTheDocument())
    expect(screen.getByText('不会自动发布')).toBeInTheDocument()
  })

  it('shows sourced trend candidates, honest limits and manual fallback', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      let data: any = []
      if (url.includes('/setup/status')) data = { deepseek_configured: true, tavily_configured: true, deepseek_model: 'deepseek-v4-flash' }
      else if (url.includes('/trends/candidates')) data = [{ id: 'trend-1', title: '把迟到的情绪放回下班路上', emotion: '延迟性痛感', source_platforms: ['豆瓣', '知乎'], source_links: [{ title: '公开讨论', url: 'https://example.org/topic', platform: '豆瓣' }], trend_signal: '正在讨论', trend_basis: '公开页面摘要出现了可核查的城市与关系讨论。', female_emotional_angle: '从年轻女性下班后的身体疲惫进入私人经验。', account_fit: '高', homogeneity_risk: '中', cultural_association: '轻度联想到城市电影', confidence: '中', data_limitations: '只覆盖搜索服务可访问的公开网页，不代表平台完整热度。', rewrite_logic: '只保留情绪内核，重写场景和结构。', created_at: '2026-07-16T10:00:00Z' }]
      else if (url.includes('/trends/runs')) data = [{ id: 'run-1', status: 'completed', provider: 'tavily', query_count: 3, usage_credits: 3, source_count: 6, candidate_count: 1, data_status: 'data_insufficient', started_at: '2026-07-16T10:00:00Z' }]
      else if (url.includes('/trends/manual-sources')) data = []
      else if (url.includes('/trends/schedule/status')) data = { supported: true, installed: false, times: ['09:00', '20:00'], missed_run_policy: '电脑关机或错过时不补跑，等待下一次计划时间。' }
      else if (url.includes('/ocr/status')) data = { available: true, provider: 'windows-media-ocr', local_only: true, languages: ['zh-Hans-CN'], retention: '确认后删除' }
      else if (url.includes('/ocr/runs')) data = [{ id: 'ocr-1', status: 'pending_confirmation', provider: 'windows-media-ocr', original_filename: '讨论.png', media_type: 'image/png', recognized_text: '下班以后，我才开始想念。', corrected_text: '下班以后，我才开始想念。', retention_policy: 'delete_after_confirmation', created_at: '2026-07-16T10:00:00Z' }]
      return { ok: true, json: async () => data } as Response
    }))

    render(<App />)
    expect(await screen.findByText('把迟到的情绪放回下班路上')).toBeInTheDocument()
    expect(screen.getByText(/不代表平台完整热度/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /豆瓣来源/ })).toHaveAttribute('href', 'https://example.org/topic')
    expect(screen.getByText(/09:00 \/ 20:00/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '补充话题或链接' }))
    expect(screen.getByPlaceholderText('例如：最近反复看到的讨论')).toBeInTheDocument()
    expect(screen.getByText('截图本地识别')).toBeInTheDocument()
    expect(screen.getByText(/不发送到云端/)).toBeInTheDocument()
    const ocrText = screen.getByDisplayValue('下班以后，我才开始想念。')
    fireEvent.change(ocrText, { target: { value: '下班以后，我才真正开始想念。' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /我已核对文字/ }))
    expect(screen.getByRole('button', { name: '确认并保存' })).toBeEnabled()
  })

  it('shows a failed trend refresh message only once', async () => {
    const message = '热点模型返回格式不正确，请稍后重新手动刷新。'
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/setup/status')) return { ok: true, json: async () => ({ deepseek_configured: true, tavily_configured: true, deepseek_model: 'deepseek-v4-flash' }) } as Response
      if (url.includes('/trends/refresh')) return { ok: false, json: async () => ({ detail: message }) } as Response
      if (url.includes('/trends/runs')) return { ok: true, json: async () => ([{ id: 'failed-run', status: 'failed', provider: 'tavily', query_count: 3, source_count: 15, candidate_count: 0, data_status: 'data_insufficient', error_summary: message, started_at: '2026-07-16T12:48:10Z' }]) } as Response
      if (url.includes('/trends/schedule/status')) return { ok: true, json: async () => ({ supported: true, installed: false, times: ['09:00', '20:00'] }) } as Response
      if (url.includes('/ocr/status')) return { ok: true, json: async () => ({ available: true, provider: 'windows-media-ocr', local_only: true, languages: ['zh-Hans-CN'], retention: '确认后删除' }) } as Response
      return { ok: true, json: async () => [] } as Response
    }))

    render(<App />)
    const refresh = await screen.findByRole('button', { name: '手动刷新' })
    fireEvent.click(refresh)
    await waitFor(() => expect(screen.getAllByText(message)).toHaveLength(1))
  })

  it('opens the content library from the sidebar', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '内容库' }))
    expect(await screen.findByRole('heading', { name: '内容库' })).toBeInTheDocument()
    expect(screen.getByPlaceholderText('搜索标题、主题或情绪')).toBeInTheDocument()
  })

  it('opens the style training page from the sidebar', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '风格训练' }))
    expect(await screen.findByRole('heading', { name: '喂文章 / 风格训练' })).toBeInTheDocument()
    expect(screen.getByPlaceholderText('在这里粘贴一篇你认可的文章，至少 200 字……')).toBeInTheDocument()
    expect(screen.getByText(/反馈固定使用简体中文/)).toBeInTheDocument()
  })

  it('opens the versioned editorial constitution from settings', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '设置' }))
    expect(await screen.findByRole('button', { name: '编辑宪法' })).toBeInTheDocument()
    expect(screen.getByText('用具体场景承载抽象情绪')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '测试 DeepSeek' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '测试 Tavily' })).toBeDisabled()
  })

  it('shows revision evidence and occurrence counts before diff memory confirmation', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      let data: any = []
      if (url.includes('/setup/status')) data = { deepseek_configured: true, tavily_configured: false, deepseek_model: 'deepseek-v4-flash' }
      else if (url.includes('/style-training/profile/versions')) data = []
      else if (url.includes('/style-training/profile')) data = { version: 0, change_type: 'initial', rules: { core_rules: [], confirmed_training: [] } }
      else if (url.includes('/style-training/diff-candidates')) data = [{ id: 'diff-1', pattern_type: 'deleted_phrase', rule_text: '减少使用“原来”，优先保留具体经验', status: 'pending', occurrence_count: 1, last_observed_at: '2026-07-16T00:00:00Z', evidence: [{ content_id: 'c1', content_title: '我还是绕开那条街', before_excerpt: '原来我终于明白', after_excerpt: '我没有明白什么', metrics: {}, observed_at: '2026-07-16T00:00:00Z' }] }]
      return { ok: true, json: async () => data } as Response
    }))
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '风格训练' }))
    expect(await screen.findByText('人工修改差异记忆')).toBeInTheDocument()
    expect(screen.getByText('减少使用“原来”，优先保留具体经验')).toBeInTheDocument()
    expect(screen.getByText('篇出现')).toBeInTheDocument()
    expect(screen.getByText('原来我终于明白')).toBeInTheDocument()
    expect(screen.getByText('我没有明白什么')).toBeInTheDocument()
  })

  it('opens the publication analytics page from the sidebar', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '复盘' }))
    expect(await screen.findByRole('heading', { name: '发布记录与数据快照' })).toBeInTheDocument()
    expect(screen.getByText('还没有发布记录。文章通过审核并由你手动发布后，可以在文章页粘贴笔记链接。')).toBeInTheDocument()
  })

  it('shows local analytics OCR correction and confirmation before saving metrics', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      let data: any = []
      if (url.includes('/setup/status')) data = { deepseek_configured: true, tavily_configured: false, deepseek_model: 'deepseek-v4-flash' }
      else if (url.endsWith('/api/contents')) data = []
      else if (url.endsWith('/api/publications')) data = [{ id: 'pub-1', content_id: 'c1', note_url: 'https://www.xiaohongshu.com/explore/1', published_at: '2026-07-15T12:00:00Z', final_title: '下班以后才开始想念', final_tags: [], snapshots: [] }]
      else if (url.includes('/publications/due')) data = []
      else if (url.includes('/ocr/runs?purpose=analytics')) data = [{ id: 'ocr-a1', purpose: 'analytics', status: 'pending_confirmation', provider: 'windows-media-ocr', original_filename: '后台.png', media_type: 'image/png', recognized_text: '浏览量 8600\n点赞 320', corrected_text: '浏览量 8600\n点赞 320', retention_policy: 'retain_until_manual_delete', engine_metadata: { publication_id: 'pub-1', day_offset: 1, parsed_metrics: { views: 8600, likes: 320 } }, created_at: '2026-07-16T10:00:00Z' }]
      return { ok: true, json: async () => data } as Response
    }))
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '复盘' }))
    fireEvent.click(await screen.findByRole('button', { name: '录入或更新数据' }))
    expect(await screen.findByText('数据后台截图本地 OCR')).toBeInTheDocument()
    expect(screen.getByLabelText('OCR 文字（请核对并修正）')).toHaveValue('浏览量 8600\n点赞 320')
    expect(screen.getByDisplayValue('8600')).toBeInTheDocument()
    expect(screen.getByText(/长期保留/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /我已逐项核对/ }))
    expect(screen.getByRole('button', { name: '确认 OCR 并保存独立快照' })).toBeEnabled()
  })

  it('requires selecting and confirming AI retrospective experiments before they enter memory', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      let data: any = []
      if (url.includes('/setup/status')) data = { deepseek_configured: true, tavily_configured: false, deepseek_model: 'deepseek-v4-flash' }
      else if (url.endsWith('/api/contents')) data = []
      else if (url.endsWith('/api/publications')) data = [{ id: 'pub-1', content_id: 'c1', note_url: 'https://www.xiaohongshu.com/explore/1', published_at: '2026-07-12T12:00:00Z', final_title: '下班以后才开始想念', final_tags: ['城市'], snapshots: [{ id: 'snap-1', day_offset: 1, captured_at: '2026-07-13T12:00:00Z', metrics: { views: 1000, favorites: 80 }, calculated_rates: { favorite_rate: 0.08 } }] }]
      else if (url.includes('/publications/due')) data = []
      else if (url.includes('/ocr/runs?purpose=analytics')) data = []
      else if (url.endsWith('/api/analytics/reports')) data = [{ id: 'report-1', report_type: 'single', publication_id: 'pub-1', period_start: '2026-07-12T12:00:00Z', period_end: '2026-07-13T12:00:00Z', status: 'generated', input_snapshot_ids: ['snap-1'], model_name: 'deepseek-v4-flash', prompt_version: '2.1.0', confirmed_suggestion_ids: [], created_at: '2026-07-16T12:00:00Z', payload: { sample_size: 1, period_summary: '只分析已确认快照，样本仍然有限。', observations: [{ label: '收藏线索', finding: '收藏率相对稳定。', confidence: '中', caveat: '不能判断因果。', snapshot_ids: ['snap-1'] }], suggestions: [{ suggestion_id: 'scene_opening_test', applies_to: '开头', experiment: '只测试一次更快进入场景', rationale: '现有数据只支持可逆实验', confidence: '中', evidence_snapshot_ids: ['snap-1'] }], preserve_identity: ['保留具体生活触感'], limitations: ['只有一篇样本'], conclusion: '不能形成固定模板。' } }]
      else if (url.includes('/api/analytics/reports/report-1/confirm')) data = { id: 'report-1', status: 'confirmed' }
      return { ok: true, json: async () => data } as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '复盘' }))
    expect(await screen.findByText('AI 单篇 / 周度 / 月度复盘')).toBeInTheDocument()
    expect(screen.getByText(/默认不会改风格档案/)).toBeInTheDocument()
    expect(screen.getByText('必须保留')).toBeInTheDocument()
    const confirmButton = screen.getByRole('button', { name: '确认选中建议' })
    expect(confirmButton).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /只测试一次更快进入场景/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /我确认只把选中建议作为可选实验/ }))
    expect(confirmButton).toBeEnabled()
    fireEvent.click(confirmButton)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/analytics/reports/report-1/confirm'), expect.objectContaining({ method: 'POST' })))
  })

  it('keeps comment OCR local and requires separate consent before reply generation', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      let data: any = []
      if (url.includes('/setup/status')) data = { deepseek_configured: true, tavily_configured: false, deepseek_model: 'deepseek-v4-flash' }
      else if (url.endsWith('/api/contents')) data = []
      else if (url.endsWith('/api/publications')) data = [{ id: 'pub-1', content_id: 'c1', note_url: 'https://www.xiaohongshu.com/explore/1', published_at: '2026-07-12T12:00:00Z', final_title: '下班以后才开始想念', final_tags: [], snapshots: [] }]
      else if (url.includes('/publications/due')) data = []
      else if (url.includes('/ocr/runs?purpose=analytics')) data = []
      else if (url.includes('/ocr/runs?purpose=comments')) data = [{ id: 'comment-ocr-1', purpose: 'comments', status: 'pending_confirmation', provider: 'windows-media-ocr', original_filename: '评论.png', media_type: 'image/png', recognized_text: '小雨：看到这里很想哭\n谢谢你写出来', corrected_text: '小雨：看到这里很想哭\n谢谢你写出来', retention_policy: 'delete_after_confirmation', engine_metadata: { publication_id: 'pub-1', suggested_comments: [{ author_label: '小雨', text: '看到这里很想哭' }, { text: '谢谢你写出来' }] }, created_at: '2026-07-16T12:00:00Z' }]
      else if (url.endsWith('/api/analytics/reports')) data = []
      else if (url.endsWith('/api/publications/pub-1/comments')) data = [{ id: 'comment-1', publication_id: 'pub-1', source_type: 'paste', author_label: '晚风', comment_text: '我也经历过这样的夜晚', created_at: '2026-07-16T12:00:00Z', reply_suggestions: [] }]
      return { ok: true, json: async () => data } as Response
    }))

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '复盘' }))
    expect(await screen.findByText('评论回复助手')).toBeInTheDocument()
    expect(screen.getByText(/截图确认\/放弃后永久删除/)).toBeInTheDocument()
    expect(await screen.findByAltText('待确认的评论截图')).toBeInTheDocument()
    expect(screen.getByLabelText('评论文字')).toHaveValue('小雨：看到这里很想哭\n谢谢你写出来')
    const saveComments = screen.getByRole('button', { name: '确认评论并删除截图' })
    expect(saveComments).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /我已逐条核对评论文字和昵称/ }))
    expect(saveComments).toBeEnabled()

    const generateReply = await screen.findByRole('button', { name: '生成一条回复建议' })
    expect(generateReply).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /只把这一条评论发送给 DeepSeek/ }))
    expect(generateReply).toBeEnabled()
    expect(screen.getByText(/应用没有登录、评论或发送接口/)).toBeInTheDocument()
  })

  it('discloses retrieved style memory and originality coverage without historical body text', async () => {
    const content = {
      id: 'article-1', theme: '旧街', emotion: '迟来的想念', title: '绕开那条街', status: 'draft',
      current_step: 'human_edit', updated_at: '2026-07-15T12:00:00Z', artifacts: [
        {
          id: 'draft-1', artifact_type: 'EssayDraft', step_id: 'draft_generation', version: 1,
          confirmed: false, created_at: '2026-07-15T11:59:00Z', payload: {
            title: '绕开那条街', body: '她从便利店门口经过。', alternate_titles: ['旧街', '慢一点忘记'],
            cover_copy: '城市比我更晚忘记', pinned_comment: '慢一点也没有关系。', recommended_publish_time: '21:30', recommendation_confidence: '低',
          },
        },
        {
          id: 'memory-1', artifact_type: 'GenerationMemoryReport', step_id: 'draft_generation', version: 1,
          confirmed: false, created_at: '2026-07-15T12:00:00Z', payload: {
            retrieval_engine: 'sqlite-fts5-char-ngram-v1',
            retrieval_scope: '仅检索本地历史版本的中文字符 n-gram、主题标签和结构指纹；未注入历史正文',
            style_rules_used: ['保留具体动作与身体感'],
            avoid_history: [{ version_id: 'v1', historical_title: '旧街仍然记得', scenes: ['便利店'], structure_tags: ['回忆折返'], imagery: ['夜'], ending_type: '动作或场景停顿' }],
          },
        },
        {
          id: 'originality-1', artifact_type: 'OriginalityReport', step_id: 'quality_review', version: 1,
          confirmed: false, created_at: '2026-07-15T12:01:00Z', payload: {
            passes_gate: true, title_risk: '低', opening_risk: '低', structure_risk: '低', scene_risk: '低', ending_risk: '低', metaphor_risk: '低',
            external_check_status: 'completed',
            coverage_details: [{ source: '本地历史版本', status: '已完成' }, { source: '公开可访问的小红书网页', status: '已完成 site:xiaohongshu.com 检索' }],
            uncovered_sources: ['需要登录、验证码或非公开的小红书内容'], matches: [], web_matches: [], manual_matches: [],
          },
        },
        {
          id: 'citation-1', artifact_type: 'CitationVerificationReport', step_id: 'citation_verification', version: 1,
          confirmed: false, created_at: '2026-07-15T12:01:00Z', payload: {
            check_status: 'completed', provider: 'tavily', query_count: 1, coverage_note: '已核验 1 条文化引用；结果仅覆盖搜索服务可访问的公开网页。',
            items: [{ reference: { work: '活着', author: '余华' }, status: 'verified', recommendation: '发布前仍建议人工复核。', evidence: [{ title: '《活着》作品介绍', url: 'https://example.org' }] }],
          },
        },
      ],
    }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      let data: any = []
      if (url.includes('/setup/status')) data = { deepseek_configured: true, tavily_configured: false, deepseek_model: 'deepseek-v4-flash' }
      else if (url.endsWith('/api/contents')) data = [content]
      else if (url.includes('/contents/article-1/versions')) data = []
      else if (url.endsWith('/contents/article-1/cover')) data = { upload: null, rendered: null, defaults: { width: 900, height: 1200, ratio: '3:4', format: 'PNG' }, auto_image_generation: false }
      else if (url.includes('/contents/article-1')) data = content
      return { ok: true, json: async () => data } as Response
    }))

    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '内容库' }))
    fireEvent.click(await screen.findByRole('button', { name: /绕开那条街/ }))
    expect(await screen.findByText('本次风格记忆与历史避重')).toBeInTheDocument()
    expect(screen.getByText('保留具体动作与身体感')).toBeInTheDocument()
    expect(screen.getByText('旧街仍然记得')).toBeInTheDocument()
    expect(screen.getByText('原创度检测范围')).toBeInTheDocument()
    expect(screen.getByText(/本系统不宣称“全网原创”/)).toBeInTheDocument()
    expect(screen.getByText(/公开可访问的小红书网页：已完成/)).toBeInTheDocument()
    expect(screen.getByText('文化引用核验')).toBeInTheDocument()
    expect(screen.getByText('手工补充比对来源')).toBeInTheDocument()
    expect(screen.getByText('封面与效果预览')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '纯文字留白型' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '生成真实 PNG 预览' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '生成图片' })).toBeDisabled()
    expect(screen.getByText(/裁剪、排版和 PNG 预览均在本地完成/)).toBeInTheDocument()
    expect(screen.queryByText('HISTORICAL_FULL_BODY_MUST_NOT_ENTER_GENERATION_CONTEXT')).not.toBeInTheDocument()
  })

  it('shows machine-readable provider security boundaries in settings', async () => {
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '设置' }))
    expect(await screen.findByText('Provider 与插件安全中心')).toBeInTheDocument()
    expect(screen.getByText('Local Export Provider')).toBeInTheDocument()
    expect(screen.getByText(/不运行下载代码/)).toBeInTheDocument()
  })
})
