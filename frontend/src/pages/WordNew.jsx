import { useState, useEffect, useRef, useCallback } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { createWord, fetchWord } from '../api'
import { useSSE } from '../useSSE'
import WordCard from '../components/WordCard'
import { useNotebooks } from '../useNotebooks'

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
  const [searchParams, setSearchParams] = useSearchParams()
  const notebookId = searchParams.get('notebook_id') || 'default'
  const { notebooks, loading: booksLoading, error: booksError, refresh: refreshBooks } = useNotebooks()
  const selectedBook = notebooks.find(book => book.id === notebookId)
  const [word, setWord] = useState('')
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState(null)
  const [addedWords, setAddedWords] = useState([])
  const addedRef = useRef([])
  const inputRef = useRef(null)
  const navigate = useNavigate()
  const providerLabel = useProviderLabel()
  useEffect(() => { addedRef.current = addedWords }, [addedWords])

  const updateAdded = useCallback(result => {
    setAddedWords(previous => previous.map(entry => {
      if (entry.word.id !== result.word.id) return entry
      // A request started before an SSE success must not erase the displayed definition.
      if (['removed', 'deleted'].includes(entry.enrichment?.status)) return entry
      if (entry.word.definition && !result.word.definition) return entry
      return { ...entry, ...result }
    }))
  }, [])
  const handleEnriched = useCallback((id, fields) => {
    setAddedWords(previous => previous.map(entry => entry.word.id === id
      ? { ...entry, word: { ...entry.word, ...fields }, enrichment: { status: fields.definition ? 'ready' : 'idle' } } : entry))
    window.dispatchEvent(new Event('review-stats-changed'))
  }, [])
  const handleFailed = useCallback((id, _word, reason, detail) => {
    setAddedWords(previous => previous.map(entry => entry.word.id === id
      ? { ...entry, enrichment: { status: detail?.removed ? 'removed' : 'failed', error: reason } } : entry))
    if (detail?.removed) {
      window.dispatchEvent(new Event('notebooks-changed'))
      window.dispatchEvent(new Event('review-stats-changed'))
    }
  }, [])
  useSSE({ onEnriched: handleEnriched, onEnrichFailed: handleFailed })

  const hasPending = addedWords.some(entry => ['queued', 'processing'].includes(entry.enrichment?.status))
  useEffect(() => {
    if (!hasPending) return
    let alive = true
    let running = false
    async function refresh() {
      if (running) return
      running = true
      try {
        const pending = addedRef.current.filter(entry => ['queued', 'processing'].includes(entry.enrichment?.status))
        const results = await Promise.allSettled(pending.map(async entry => {
          try { return await fetchWord(entry.word.id) }
          catch (err) {
            if (err.status === 404) return { ...entry, enrichment: { status: 'deleted' } }
            throw err
          }
        }))
        if (alive) results.forEach(result => { if (result.status === 'fulfilled') updateAdded(result.value) })
      } finally { running = false }
    }
    // Recover persisted results after a disconnected or missed SSE notification.
    const timer = setInterval(refresh, 2000)
    return () => { alive = false; clearInterval(timer) }
  }, [hasPending, updateAdded])

  function showRecent(result) {
    setAddedWords(previous => [result, ...previous.filter(entry => entry.word.id !== result.word.id)].slice(0, 10))
  }

  function clearSubmitted(submitted) {
    setWord(current => current.trim() === submitted ? '' : current)
    inputRef.current?.focus()
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!word.trim() || loading || booksLoading || booksError || !selectedBook) return
    const submitted = word.trim()
    setLoading(true)
    try {
      const result = await createWord(submitted, '', notebookId)
      showRecent(result)
      clearSubmitted(submitted)
      setToast({ type: 'info', msg: `「${result.word.word}」已保存到「${selectedBook.name}」` })
      setTimeout(() => setToast(null), 2000)
    } catch (err) {
      if (err.status === 409 && err.details?.word?.id) {
        showRecent({ word: err.details.word, enrichment: err.details.enrichment, existing: true })
        clearSubmitted(submitted)
        setToast({ type: 'info', msg: err.message })
      } else if (err.status === 409) {
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
          <label htmlFor="new-word-notebook">保存到单词本</label>
          <select
            id="new-word-notebook"
            className="notebook-select"
            value={notebookId}
            disabled={loading || booksLoading || Boolean(booksError)}
            onKeyDown={event => event.stopPropagation()}
            onChange={event => setSearchParams(previous => {
              const next = new URLSearchParams(previous)
              next.set('notebook_id', event.target.value)
              return next
            })}
          >
            {!selectedBook && <option value={notebookId} disabled>{booksLoading ? '加载单词本…' : '此单词本已不可用，请重新选择'}</option>}
            {notebooks.map(book => <option key={book.id} value={book.id}>{book.name}</option>)}
          </select>
          <Link className="btn btn-ghost" to="/notebooks">管理单词本</Link>
          {booksError && <p role="alert">{booksError} <button type="button" className="btn btn-ghost" onClick={refreshBooks}>重试</button></p>}
        </div>
        <div className="form-group">
          <label htmlFor="new-word">单词</label>
          <input
            id="new-word"
            ref={inputRef}
            type="text"
            value={word}
            onChange={e => setWord(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入英文单词，回车保存"
            autoFocus
          />
        </div>
        <div className="btn-group">
          <button type="submit" className="btn btn-primary" disabled={loading || booksLoading || Boolean(booksError) || !selectedBook}>
            {loading ? '保存中…' : '保存'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>
            取消
          </button>
        </div>
        <p style={{ marginTop: 14, fontSize: 12, color: 'var(--text-muted)', letterSpacing: '0.04em' }}>
          Enter 保存 · Esc 返回 · 释义/音标/例句由 {providerLabel} 自动补充
          <br />新词首字母统一大写，其余字符保持输入的大小写；已有词条不改名。
        </p>
      </form>
      {addedWords.length > 0 && <section className="added-words" aria-labelledby="added-words-heading">
        <h3 id="added-words-heading">刚刚添加 · 即时记忆</h3>
        <p className="added-words-hint">本页展示最近添加或再次查看的 10 个单词，在同一本中重复输入会直接显示已有内容。</p>
        <div aria-live="polite" aria-relevant="additions text">
          {addedWords.map((entry, index) => <article key={entry.word.id}>
            <p className="added-words-hint">
              <Link to={`/?notebook_id=${encodeURIComponent(entry.word.notebook_id || 'default')}`}>{notebooks.find(book => book.id === entry.word.notebook_id)?.name || '所属单词本'}</Link>
              {entry.existing && ' · 本中已有，已展示原记录并保留复习进度'}
            </p>
            {['removed', 'deleted'].includes(entry.enrichment?.status) ? <h4>{entry.word.word}</h4> : <WordCard word={entry.word} index={index} />}
            {!entry.word.definition && <p className="added-words-hint">
              {['queued', 'processing'].includes(entry.enrichment?.status) ? '已保存，正在生成释义…'
                : entry.enrichment?.status === 'deleted' ? '这个单词已被删除。'
                  : entry.enrichment?.error || '单词已保存，释义尚未生成，可在列表补全缺失或手动编辑。'}
            </p>}
          </article>)}
        </div>
      </section>}
    </div>
  )
}
