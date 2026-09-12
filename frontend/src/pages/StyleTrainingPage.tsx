import { useEffect, useState } from 'react'
import { BookOpen, Check, LoaderCircle, RotateCcw, Save, ShieldCheck, Sparkles } from 'lucide-react'
import type { StyleProposal, StyleProfile, DiffMemoryCandidate } from '../types'
import { request } from '../lib/api'
import { EditorialConstitutionPanel } from '../components/EditorialConstitutionPanel'
import { RuleDiff } from '../components/RuleDiff'

export function StyleTrainingPage() {
  const [constitutionOpen, setConstitutionOpen] = useState(false)
  const [article, setArticle] = useState('')
  const [sourceType, setSourceType] = useState('我认可的参考文章')
  const [proposals, setProposals] = useState<StyleProposal[]>([])
  const [profile, setProfile] = useState<StyleProfile | null>(null)
  const [profileVersions, setProfileVersions] = useState<StyleProfile[]>([])
  const [diffCandidates, setDiffCandidates] = useState<DiffMemoryCandidate[]>([])
  const [editingProfile, setEditingProfile] = useState(false)
  const [coreRules, setCoreRules] = useState('')
  const [manualPreferences, setManualPreferences] = useState('')
  const [manualAvoid, setManualAvoid] = useState('')
  const [profileConfirmed, setProfileConfirmed] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  async function loadStyle() {
    setError('')
    const [nextProposals, nextProfile, nextVersions, nextDiffCandidates] = await Promise.all([
      request<StyleProposal[]>('/style-training/proposals'),
      request<StyleProfile>('/style-training/profile'),
      request<StyleProfile[]>('/style-training/profile/versions'),
      request<DiffMemoryCandidate[]>('/style-training/diff-candidates'),
    ])
    setProposals(nextProposals); setProfile(nextProfile); setProfileVersions(nextVersions); setDiffCandidates(nextDiffCandidates)
    setCoreRules((nextProfile.rules.core_rules || []).join('\n'))
    setManualPreferences((nextProfile.rules.manual_preferences || []).join('\n'))
    setManualAvoid((nextProfile.rules.manual_avoid_patterns || []).join('\n'))
  }
  useEffect(() => { void Promise.resolve().then(loadStyle).catch((e) => setError((e as Error).message)) }, [])

  async function analyze(event: React.FormEvent) {
    event.preventDefault(); setBusy('analyze'); setError('')
    try {
      await request('/style-training/analyze', { method: 'POST', body: JSON.stringify({ article, source_type: sourceType }) })
      setArticle('')
      await loadStyle()
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  async function decide(id: string, choice: 'confirm' | 'reject') {
    setBusy(choice); setError('')
    try { await request(`/style-training/proposals/${id}/${choice}`, { method: 'POST' }); await loadStyle() }
    catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  const lines = (value: string) => value.split('\n').map((item) => item.trim()).filter(Boolean)
  async function saveProfile(event: React.FormEvent) {
    event.preventDefault(); setBusy('profile'); setError('')
    try {
      await request('/style-training/profile', {
        method: 'POST',
        body: JSON.stringify({
          core_rules: lines(coreRules),
          manual_preferences: lines(manualPreferences),
          manual_avoid_patterns: lines(manualAvoid),
          confirm: profileConfirmed,
        }),
      })
      setEditingProfile(false); setProfileConfirmed(false); await loadStyle()
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  async function rollback(version: number) {
    if (!window.confirm(`确认把风格档案回滚到 V${version}？系统会创建一个新的回滚版本，不会删除历史。`)) return
    setBusy(`rollback-${version}`); setError('')
    try {
      await request(`/style-training/profile/rollback/${version}`, { method: 'POST', body: JSON.stringify({ confirm: true }) })
      await loadStyle()
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  async function decideDiff(id: string, choice: 'confirm' | 'reject') {
    setBusy(`diff-${choice}-${id}`); setError('')
    try {
      await request(`/style-training/diff-candidates/${id}/${choice}`, { method: 'POST', body: JSON.stringify({ confirm: true }) })
      await loadStyle()
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  const pending = proposals.find((item) => item.status === 'pending')
  const pendingDiff = diffCandidates.filter((item) => item.status === 'pending')
  return (
    <main className="page style-page">
      <header className="style-head"><div><div className="eyebrow">可解释风格记忆</div><h1>喂文章 / 风格训练</h1><p>学习抽象特征，不复制原句、结构或核心比喻。</p></div><div className="profile-version"><span>V{profile?.version || 0}</span><small>当前风格档案</small></div></header>
      {error && <div className="error-banner" role="alert">{error}{!profile && <button className="ghost" onClick={() => loadStyle().catch((e) => setError((e as Error).message))}>重新读取风格档案</button>}</div>}
      <nav className="section-nav" aria-label="风格管理分组"><a href="#style-profile">当前规则</a><a href="#style-learning">文章训练</a><a href="#style-candidates">修改规律</a><a href="#style-history">版本历史</a></nav>
      <details className="style-constitution" onToggle={(event) => setConstitutionOpen(event.currentTarget.open)}><summary>查看或调整最高优先级的编辑宪法</summary>{constitutionOpen && <EditorialConstitutionPanel />}</details>
      <section id="style-profile" className="profile-manager">
        <div className="panel-title"><span>当前风格档案</span><small>确认后才会影响后续写作</small></div>
        {!editingProfile ? <>
          <div className="profile-columns">
            <div><h3>核心规则</h3>{(profile?.rules.core_rules || []).map((rule) => <p key={rule}>{rule}</p>)}</div>
            <div><h3>手动偏好</h3>{(profile?.rules.manual_preferences || []).length ? profile?.rules.manual_preferences?.map((rule) => <p key={rule}>{rule}</p>) : <p className="muted">尚未添加</p>}</div>
            <div><h3>明确避开</h3>{(profile?.rules.manual_avoid_patterns || []).length ? profile?.rules.manual_avoid_patterns?.map((rule) => <p key={rule}>{rule}</p>) : <p className="muted">尚未添加</p>}</div>
          </div>
          <div className="profile-actions"><small>已确认训练 {profile?.rules.confirmed_training?.length || 0} 次</small><button className="ghost" disabled={!profile} onClick={() => { setCoreRules((profile?.rules.core_rules || []).join('\n')); setManualPreferences((profile?.rules.manual_preferences || []).join('\n')); setManualAvoid((profile?.rules.manual_avoid_patterns || []).join('\n')); setProfileConfirmed(false); setEditingProfile(true) }}>编辑风格档案</button></div>
        </> : <form className="profile-editor" onSubmit={saveProfile}>
          <label>核心规则（每行一条）<textarea required value={coreRules} onChange={(e) => setCoreRules(e.target.value)} /></label>
          <label>偏好表达（每行一条）<textarea value={manualPreferences} onChange={(e) => setManualPreferences(e.target.value)} /></label>
          <label>明确避开（每行一条）<textarea value={manualAvoid} onChange={(e) => setManualAvoid(e.target.value)} /></label>
          <label className="confirm-line"><input type="checkbox" checked={profileConfirmed} onChange={(e) => setProfileConfirmed(e.target.checked)} />我确认这些修改将进入新的风格档案版本</label>
          <div className="proposal-actions"><button type="button" className="ghost" onClick={() => setEditingProfile(false)}>取消</button><button className="primary" disabled={!profileConfirmed || !lines(coreRules).length || !!busy}>{busy === 'profile' ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />}确认并保存新版本</button></div>
        </form>}
      </section>
      {!pending && <form id="style-learning" className="training-form" onSubmit={analyze}>
        <label>来源类型<input value={sourceType} onChange={(e) => setSourceType(e.target.value)} /></label>
        <label>粘贴参考文章<textarea required minLength={200} maxLength={20000} value={article} onChange={(e) => setArticle(e.target.value)} placeholder="在这里粘贴一篇你认可的文章，至少 200 字……" /></label>
        <div className="privacy-box"><ShieldCheck size={17} /><span><b>原文不会长期保存 · 反馈固定使用简体中文</b>分析时内容会发送给你配置的 DeepSeek；完成后数据库只保留不可逆哈希、字符数和中文抽象提案，不保存原文或可识别长片段。</span></div>
        <div className="training-actions"><small>{article.length} / 20000 字</small><button className="primary" disabled={article.length < 200 || !!busy}>{busy === 'analyze' ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}提取风格特征</button></div>
      </form>}
      {pending && <section className="proposal-card"><div className="proposal-top"><div><div className="section-kicker">待你确认的提案</div><h2>只保存抽象规则，不保存参考原文</h2></div><small>{pending.source_char_count} 字 · {pending.source_type}</small></div><div className="features-grid">{pending.analysis.features.map((feature) => <article key={feature.dimension}><span>{feature.dimension}</span><p>{feature.observation}</p><strong>{feature.preference}</strong><small>模仿风险：{feature.imitation_risk}</small></article>)}</div><div className="test-text"><div className="section-kicker">原创测试短文</div><p>{pending.analysis.test_text}</p></div><div className="proposal-actions"><button className="ghost" disabled={!!busy} onClick={() => decide(pending.id, 'reject')}>拒绝并丢弃</button><button className="primary" disabled={!!busy} onClick={() => decide(pending.id, 'confirm')}>{busy === 'confirm' ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}确认并加入风格档案</button></div></section>}
      <section id="style-candidates" className="diff-memory-panel">
        <div className="panel-title"><span>人工修改差异记忆</span><small>{pendingDiff.length} 条待确认</small></div>
        <p className="diff-memory-note">人工稿通过质量门禁并提交待审核后，系统比较 AI 初稿与最终人工稿，只生成候选规律。每条都显示证据和跨文章出现次数；未经你确认不会进入风格档案。</p>
        {pendingDiff.length ? pendingDiff.map((item) => <article className="diff-candidate" key={item.id}><header><div><small>{item.pattern_type}</small><h3>{item.rule_text}</h3></div><strong>{item.occurrence_count}<small>篇出现</small></strong></header><div className="diff-evidence">{item.evidence.slice(0, 3).map((evidence) => <div key={evidence.content_id}><b>{evidence.content_title}</b><p><span>AI 稿</span>{evidence.before_excerpt}</p><p><span>人工稿</span>{evidence.after_excerpt}</p></div>)}</div><div className="proposal-actions"><button className="ghost" disabled={!!busy} onClick={() => decideDiff(item.id, 'reject')}>拒绝这条规律</button><button className="primary" disabled={!!busy} onClick={() => decideDiff(item.id, 'confirm')}>{busy === `diff-confirm-${item.id}` ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}确认并写入风格档案</button></div></article>) : <div className="empty-note"><BookOpen size={22} /><p>还没有待确认的修改规律。提交一篇通过质量门禁的人工稿后，系统会在这里展示候选证据。</p></div>}
        {diffCandidates.some((item) => item.status !== 'pending') && <div className="diff-history"><h3>已处理候选</h3>{diffCandidates.filter((item) => item.status !== 'pending').map((item) => <p key={item.id}><span className={`history-status ${item.status}`}>{item.status === 'confirmed' ? '已确认' : '已拒绝'}</span><strong>{item.rule_text}</strong><small>{item.occurrence_count} 篇证据</small></p>)}</div>}
      </section>
      <section className="training-history"><div className="panel-title"><span>训练记录</span><small>{proposals.length} 次</small></div>{proposals.length ? proposals.map((item) => <div className="history-row" key={item.id}><span className={`history-status ${item.status}`}>{item.status === 'confirmed' ? '已确认' : item.status === 'rejected' ? '已拒绝' : '待确认'}</span><strong>{item.source_type}</strong><small>{item.source_char_count} 字 · {new Date(item.created_at).toLocaleDateString('zh-CN')}</small></div>) : <div className="empty-note"><BookOpen size={22} /><p>还没有训练记录。你可以从一篇真正认可的文章开始。</p></div>}</section>
      <section id="style-history" className="profile-history">
        <div className="panel-title"><span>风格档案版本</span><small>{profileVersions.length} 个可回滚版本</small></div>
        {profileVersions.length ? profileVersions.map((item) => <div className="profile-version-row" key={item.id}><span>V{item.version}</span><strong>{item.change_type === 'training' ? '文章训练确认' : item.change_type === 'manual_edit' ? '人工编辑' : item.change_type === 'diff_memory' ? '修改差异确认' : item.change_type === 'language_repair' ? '中文反馈修复' : '回滚恢复'}</strong><small>{item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : ''}{item.source_version !== undefined && item.source_version !== null ? ` · 来源 V${item.source_version}` : ''}</small>{item.version !== profile?.version && <button className="ghost" disabled={!!busy} onClick={() => rollback(item.version)}>{busy === `rollback-${item.version}` ? <LoaderCircle className="spin" size={14} /> : <RotateCcw size={14} />}回滚到此版本</button>}{item.version !== profile?.version && <RuleDiff current={{ '核心规则': profile?.rules.core_rules || [], '手动偏好': profile?.rules.manual_preferences || [], '明确避开': profile?.rules.manual_avoid_patterns || [] }} previous={{ '核心规则': item.rules.core_rules || [], '手动偏好': item.rules.manual_preferences || [], '明确避开': item.rules.manual_avoid_patterns || [] }} />}</div>) : <div className="empty-note"><BookOpen size={22} /><p>确认一次训练或人工修改后，这里会出现可回滚版本。</p></div>}
      </section>
    </main>
  )
}
