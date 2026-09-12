

export type Artifact = {
  id: string
  artifact_type: string
  step_id: string
  version: number
  payload: Record<string, any>
  confirmed: boolean
  created_at: string
}

export type Content = {
  id: string
  theme: string
  emotion: string
  extra_requirements?: string
  title?: string
  status: string
  current_step: string
  selected_plan_id?: string
  selected_detail?: string
  updated_at: string
  artifacts?: Artifact[]
}

export type SetupStatus = {
  deepseek_configured: boolean
  tavily_configured: boolean
  deepseek_model: string
  price?: Record<string, number> | null
  price_source?: string | null
}

export type TrendCandidate = {
  id: string
  title: string
  emotion: string
  source_platforms: string[]
  source_links: Array<{ title: string; url: string; platform: string }>
  trend_signal: string
  trend_basis: string
  female_emotional_angle: string
  account_fit: string
  homogeneity_risk: string
  cultural_association?: string | null
  confidence: string
  data_limitations: string
  rewrite_logic: string
  used_content_id?: string | null
  created_at: string
}

export type TrendRun = {
  id: string
  status: string
  provider: string
  query_count: number
  usage_credits?: number | null
  source_count: number
  candidate_count: number
  data_status: string
  error_summary?: string | null
  started_at: string
}

export type ManualTrendSource = { id: string; source_type: string; label: string; source_value: string; created_at: string }

export type TrendSchedule = { supported: boolean; installed: boolean; times: string[]; missed_run_policy?: string }

export type OcrStatus = { available: boolean; provider: string; local_only: boolean; languages: string[]; reason?: string; retention: string }

export type OcrRun = {
  id: string; purpose: string; status: string; provider: string; original_filename: string; media_type: string
  recognized_text?: string | null; corrected_text?: string | null; retention_policy: string
  linked_manual_trend_source_id?: string | null; error_summary?: string | null; created_at: string; deleted_at?: string | null
  linked_analytics_snapshot_id?: string | null; engine_metadata: Record<string, any>
}

export type CoverAsset = {
  id: string; preview_url: string; original_name?: string; template?: 'whitespace' | 'magazine' | 'subtitle'
  copy?: string; width: number; height: number; size_bytes?: number; sharpness_score?: number
  quality_status?: 'ready' | 'warning'; quality_note?: string; focus_x?: number; focus_y?: number; zoom?: number
}

export type ImageSetup = { enabled: boolean; base_url: string; model: string; timeout_seconds: number; key_configured: boolean; available: boolean; configuration_error?: string | null }
export type CoverCandidate = { id: string; preview_url: string; download_url: string; prompt: string; model: string; width: number; height: number; size_bytes: number; created_at: string }
export type CoverState = { upload: CoverAsset | null; rendered: CoverAsset | null; defaults: { width: number; height: number; ratio: string; format: string }; auto_image_generation: boolean; image_generation_busy?: boolean; candidates?: CoverCandidate[] }

export type PluginManifest = {
  plugin_id: string; name: string; version: string; provider_type: string; source_repo: string
  pinned_ref: string; license: string; maintenance_status: string; permissions: string[]
  allowed_domains: string[]; read_dirs: string[]; write_dirs: string[]; secret_names: string[]
  needs_secret: boolean; retention: string; timeout_seconds: number; health_check: string
  rollback_version: string; enabled: boolean; built_in: boolean; tools: Array<{ tool_id: string; description: string }>
}

export type PluginRegistryItem = { manifest: PluginManifest; registry_version: number; change_type: string; activation_mode: string }

export type PluginAssessment = {
  id: string; plugin_id: string; candidate_version: string; source_repo: string; pinned_ref: string
  status: string; isolation_status: string; findings: Array<{ level: string; code: string; message: string }>
  regression_summary: Record<string, any>; error_summary?: string | null; created_at: string
}

export type PluginHistory = { registry_version: number; plugin_version: string; status: string; change_type: string; activated_at: string }

export type ConstitutionSections = {
  core_principles: string[]
  title_structure_rules: string[]
  ai_tone_prohibitions: string[]
  evaluation_dimensions: string[]
}

export type EditorialConstitution = {
  id?: string
  version: number
  sections: ConstitutionSections
  change_type: string
  source_version?: number
  change_note: string
  created_at?: string
}

export type StyleProposal = {
  id: string
  status: string
  source_type: string
  source_char_count: number
  editorial_constitution_version: number
  analysis: {
    features: Array<{ dimension: string; observation: string; preference: string; imitation_risk: string }>
    preferred_patterns: string[]
    avoid_patterns: string[]
    imagery_tendencies: string[]
    rhythm_summary: string
    ending_summary: string
    ai_tone_risks: string[]
    test_text: string
    privacy_note: string
  }
  created_at: string
}

export type StyleProfile = {
  id?: string
  version: number
  rules: {
    core_rules?: string[]
    manual_preferences?: string[]
    manual_avoid_patterns?: string[]
    confirmed_training?: Array<Record<string, any>>
    confirmed_diff_memory?: Array<Record<string, any>>
  }
  change_type: string
  source_version?: number
  created_at?: string
}

export type DiffMemoryCandidate = {
  id: string
  pattern_type: string
  rule_text: string
  status: string
  occurrence_count: number
  evidence: Array<{ content_id: string; content_title: string; before_excerpt: string; after_excerpt: string; metrics: Record<string, any>; observed_at: string }>
  profile_version_id?: string
  last_observed_at: string
}

export type AnalyticsSnapshot = {
  id: string
  day_offset: 1 | 3 | 7
  captured_at: string
  metrics: Record<string, number>
  calculated_rates: Record<string, number | string>
  note?: string
}

export type Publication = {
  id: string
  content_id: string
  note_url: string
  published_at: string
  final_title: string
  final_tags: string[]
  recommended_publish_time?: string
  snapshots: AnalyticsSnapshot[]
}

export type DueSnapshot = {
  publication_id: string
  content_id: string
  final_title: string
  day_offset: 1 | 3 | 7
  due_at: string
  overdue_days: number
}

export type AnalyticsReport = {
  id: string
  report_type: 'single' | 'weekly' | 'monthly'
  publication_id?: string | null
  period_start: string
  period_end: string
  status: 'running' | 'generated' | 'confirmed' | 'dismissed' | 'failed'
  input_snapshot_ids: string[]
  model_name?: string | null
  prompt_version: string
  payload: {
    sample_size?: number
    period_summary?: string
    observations?: Array<{ label: string; finding: string; confidence: string; caveat: string; snapshot_ids: string[] }>
    suggestions?: Array<{ suggestion_id: string; applies_to: string; experiment: string; rationale: string; confidence: string; evidence_snapshot_ids: string[] }>
    preserve_identity?: string[]
    limitations?: string[]
    conclusion?: string
  }
  confirmed_suggestion_ids: string[]
  decision_note?: string | null
  error_summary?: string | null
  created_at: string
}

export type CommentReplySuggestion = {
  id: string
  status: 'running' | 'generated' | 'failed'
  payload: { reply_text?: string; tone?: string; safety_note?: string }
  error_summary?: string | null
  created_at: string
}

export type CommentRecord = {
  id: string
  publication_id: string
  source_type: 'paste' | 'screenshot'
  author_label?: string | null
  comment_text: string
  created_at: string
  reply_suggestions: CommentReplySuggestion[]
}
