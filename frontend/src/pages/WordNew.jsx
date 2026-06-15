import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { createWord } from '../api'

function useProviderLabel() {
  const [label, setLabel] = useState('模型')
  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(d => {
        const p = d.provider
        setLabel(p === 'ollama' ? 'Ollama' : p === 'deepseek' ? 'DeepSeek' : p || '模型')
      })
      .catch(() => {})
  }, [])
  return label
}

export default function WordNew() {
  const [word, setWord] = useState('')
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState(null)
  const navigate = useNavigate()
  const providerLabel = useProviderLabel()

  async function handleSubmit(e) {
    e.preventDefault()
    if (!word.trim()) return
    setLoading(true)
    try {
      await createWord(word.trim())
      setWord('')
      setToast({ type: 'info', msg: `「${word.trim()}」已保存` })
      setTimeout(() => setToast(null), 2000)
    } catch (err) {
      setWord('')
      if (err.status === 409) {
        setToast({ type: 'warn', msg: err.message })
      } else {
        setToast({ type: 'error', msg: err.message })
      }
      setTimeout(() => setToast(null), 3000)
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Escape') {
      e.preventDefault()
      navigate(-1)
    }
  }

  return (
    <div>
      {toast && <div className={`toast toast-${toast.type}`}>{toast.msg}</div>}
      <h2 style={{ marginBottom: 20 }}>添加单词</h2>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>单词</label>
          <input
            type="text"
            value={word}
            onChange={e => setWord(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入英文单词，回车保存"
            autoFocus
          />
        </div>
        <div className="btn-group">
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? '保存中…' : '保存'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>
            取消
          </button>
        </div>
        <p style={{ marginTop: 14, fontSize: 12, color: 'var(--text-muted)', letterSpacing: '0.04em' }}>
          Enter 保存 · Esc 返回 · 释义/音标/例句由 {providerLabel} 自动补充
        </p>
      </form>
    </div>
  )
}
