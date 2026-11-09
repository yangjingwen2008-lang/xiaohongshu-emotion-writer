import { defaults, usePreferences, paperStyle, type Preferences } from '../lib/preferences'

export function ReadingPreferences({ preview = true }: { preview?: boolean }) {
  const [prefs, setPrefs] = usePreferences()
  function change<K extends keyof Preferences>(key: K, value: Preferences[K]) { setPrefs((p) => ({ ...p, [key]: value })) }
  return <div className="reading-preferences">
    <div className="preference-fields">
      <label>正文字体<select value={prefs.font} onChange={(e) => change('font', e.target.value as Preferences['font'])}><option value="serif">宋体 · 随笔</option><option value="sans">黑体 · 清晰</option></select></label>
      <label>正文字号 · {prefs.fontSize}px<input type="range" min="14" max="24" step="1" value={prefs.fontSize} onChange={(e) => change('fontSize', Number(e.target.value))} /></label>
      <label>正文行距<select value={prefs.lineHeight} onChange={(e) => change('lineHeight', Number(e.target.value))}>{[1.7, 1.9, 2.1, 2.3].map((v) => <option key={v} value={v}>{v} 倍</option>)}</select></label>
      <label>文章宽度<select value={prefs.width} onChange={(e) => change('width', e.target.value as Preferences['width'])}><option value="standard">标准</option><option value="wide">宽幅</option></select></label>
      <label>编辑纸色<select value={prefs.paper} onChange={(e) => change('paper', e.target.value as Preferences['paper'])}><option value="white">素白</option><option value="warm">暖纸</option><option value="night">夜读</option></select></label>
    </div>
    {preview && <div className="prose-preview paper-surface" data-paper={prefs.paper} style={paperStyle(prefs)}><small>排版预览 · 仅影响显示</small><p>雨停以后，我把窗户推开了一点。街上的声音慢慢进来，刚才没有写完的话，也终于有了下一句。</p></div>}
    <button type="button" className="text-button" onClick={() => setPrefs((p) => ({ ...p, font: defaults.font, fontSize: defaults.fontSize, lineHeight: defaults.lineHeight, width: defaults.width, paper: defaults.paper }))}>恢复默认排版</button>
    <p className="form-note">偏好保存在当前浏览器；文章正文与导出内容保持原样。</p>
  </div>
}
