import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createWord } from '../api'

export default function WordNew() {
  const [word, setWord] = useState('')
  const [definition, setDefinition] = useState('')
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState(null)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    if (!word.trim() || !definition.trim()) return
    setLoading(true)
    try {
      const result = await createWord(word, definition)
      if (!result.enriched && result.word.phonetic === '') {
        setToast({ type: 'warn', msg: '音标例句补充失败，可稍后重试' })
        setTimeout(() => {
          setToast(null)
          navigate('/')
        }, 1500)
      } else {
        navigate('/')
      }
    } catch (err) {
      setToast({ type: 'error', msg: err.message })
      setTimeout(() => setToast(null), 3000)
    } finally {
      setLoading(false)
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
            placeholder="输入英文单词"
            autoFocus
          />
        </div>
        <div className="form-group">
          <label>释义</label>
          <input
            type="text"
            value={definition}
            onChange={e => setDefinition(e.target.value)}
            placeholder="输入中文释义"
          />
        </div>
        <div className="btn-group">
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? '保存中…' : '保存'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => navigate('/')}>
            取消
          </button>
        </div>
      </form>
    </div>
  )
}
