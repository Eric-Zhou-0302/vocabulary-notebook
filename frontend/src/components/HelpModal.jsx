import { useEffect } from 'react'

const SHORTCUTS = [
  { keys: ['/'], desc: '聚焦搜索框' },
  { keys: ['?'], desc: '显示 / 隐藏此帮助' },
  { keys: ['Esc'], desc: '关闭此帮助' },
]

/**
 * 全局键盘帮助浮层。点击遮罩或按 Esc / ? 关闭。
 */
export default function HelpModal({ open, onClose }) {
  useEffect(() => {
    if (!open) return
    function onKey(e) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="help-modal-overlay" onClick={onClose}>
      <div className="help-modal-content" onClick={e => e.stopPropagation()}>
        <button className="help-modal-close" onClick={onClose} aria-label="关闭">×</button>
        <h2 className="help-modal-title">键盘快捷键</h2>
        <ul className="shortcut-list">
          {SHORTCUTS.map((s, i) => (
            <li key={i}>
              <span className="shortcut-keys">
                {s.keys.map((k, j) => (
                  <kbd key={j}>{k}</kbd>
                ))}
              </span>
              <span className="shortcut-desc">{s.desc}</span>
            </li>
          ))}
        </ul>
        <p className="help-modal-hint">复习模式的空格 / 1-4 见间隔复习 tab</p>
      </div>
    </div>
  )
}
