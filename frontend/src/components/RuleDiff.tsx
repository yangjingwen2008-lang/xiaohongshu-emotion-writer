type Rules = Record<string, string[]>

export function RuleDiff({ current, previous }: { current: Rules; previous: Rules }) {
  const keys = [...new Set([...Object.keys(current), ...Object.keys(previous)])]
  const changes = keys.map((key) => ({
    key,
    added: (current[key] || []).filter((rule) => !(previous[key] || []).includes(rule)),
    removed: (previous[key] || []).filter((rule) => !(current[key] || []).includes(rule)),
  })).filter((group) => group.added.length || group.removed.length)

  return <details className="rule-diff">
    <summary>与当前规则比较</summary>
    <p className="form-note">对照此历史版本，以下为当前版本新增或移除的规则；恢复前请核对。</p>
    {changes.length ? changes.map((group) => <div key={group.key}>
      <strong>{group.key}</strong>
      {group.added.map((rule) => <p key={`add-${rule}`}><span className="diff-added">当前新增</span>{rule}</p>)}
      {group.removed.map((rule) => <p key={`remove-${rule}`}><span className="diff-removed">当前移除</span>{rule}</p>)}
    </div>) : <p>可编辑规则相同。</p>}
  </details>
}
