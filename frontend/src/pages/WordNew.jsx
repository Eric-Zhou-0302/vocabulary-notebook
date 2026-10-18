import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { createWord } from '../api'
import { useBooks } from '../Books'

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
  const { books, active } = useBooks()
  const [bookId, setBookId] = useState(active || 'default')
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState(null)
  const navigate = useNavigate()
  const providerLabel = useProviderLabel()

  async function handleSubmit(e) {
    e.preventDefault()
    if (!word.trim()) return
    setLoading(true)
    try {
      await createWord(word.trim(), '', bookId)
      setWord('')
      window.dispatchEvent(new Event('library-changed'))
      window.dispatchEvent(new Event('review-stats-changed'))
      setToast({ type: 'info', msg: `「${word.trim()}」已保存` })
      setTimeout(() => setToast(null), 2000)
    } catch (err) {
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
        <div className="form-group"><label htmlFor="new-word-book">保存到</label>
          <select id="new-word-book" value={bookId} onChange={e => setBookId(e.target.value)}>
            {books.map(book => <option key={book.id} value={book.id}>{book.name}</option>)}
          </select></div>
        <div className="form-group">
          <label htmlFor="new-word">单词</label>
          <input
            id="new-word"
            maxLength={200}
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
          Enter 保存 · Esc 返回 · 释义由 {providerLabel} 补充；离线也能保存
        </p>
      </form>
    </div>
  )
}
