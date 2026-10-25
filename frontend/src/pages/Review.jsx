import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { fetchReviewDue, fetchReviewStats, fetchWords, rateWord } from '../api'
import AllWordsReview from '../components/AllWordsReview'
import SpacedReview from '../components/SpacedReview'
import { useNotebooks } from '../useNotebooks'

export default function Review() {
  const [searchParams, setSearchParams] = useSearchParams()
  const notebookId = searchParams.get('notebook_id') || ''
  const { notebooks, loading: booksLoading, error: booksError, refresh: refreshBooks } = useNotebooks()
  const [mode, setMode] = useState('daily')
  const bookUnavailable = notebookId && !booksLoading && !booksError && !notebooks.some(book => book.id === notebookId)

  return (
    <div className="review-page">
      <div className="notebook-scope">
        <label htmlFor="review-notebook">复习范围</label>
        <select
          id="review-notebook"
          className="notebook-select"
          value={notebookId}
          disabled={booksLoading || Boolean(booksError)}
          onKeyDown={event => event.stopPropagation()}
          onChange={event => setSearchParams(previous => {
            const next = new URLSearchParams(previous)
            if (event.target.value) next.set('notebook_id', event.target.value)
            else next.delete('notebook_id')
            return next
          })}
        >
          <option value="">全部单词本</option>
          {notebookId && !notebooks.some(book => book.id === notebookId) && <option value={notebookId} disabled>{booksLoading ? '加载单词本…' : '此单词本已不可用'}</option>}
          {notebooks.map(book => <option key={book.id} value={book.id}>{book.name} · {book.word_count} 词</option>)}
        </select>
        <Link className="btn btn-ghost" to="/notebooks">管理单词本</Link>
      </div>
      {booksError && <p role="alert">{booksError} <button type="button" className="btn btn-ghost" onClick={refreshBooks}>重试</button></p>}
      <p className="added-words-hint">同一单词在各本中独立记录复习进度；每日新词额度由所有单词本共用。</p>
      {bookUnavailable ? <div className="empty-state"><p>此单词本已不存在，请选择其他单词本。</p></div> : (
        <ReviewSession key={`${notebookId}:${mode}`} notebookId={notebookId} notebooks={notebooks} mode={mode} setMode={setMode} />
      )}
    </div>
  )
}

function ReviewSession({ notebookId, notebooks, mode, setMode }) {
  const [cards, setCards] = useState([])
  const [stats, setStats] = useState(null)
  const [allWords, setAllWords] = useState([])
  const [allTotal, setAllTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const requestId = useRef(0)
  const notebookNames = notebookId ? undefined : Object.fromEntries(notebooks.map(book => [book.id, book.name]))

  const loadQueue = useCallback(async () => {
    const current = ++requestId.current
    setLoading(true)
    setError('')
    try {
      const result = await fetchReviewDue(20, notebookId)
      if (current !== requestId.current) return
      setCards(result.cards)
      setStats(result.stats)
      window.dispatchEvent(new Event('review-stats-changed'))
    } catch (requestError) {
      if (current === requestId.current) setError(requestError.message || '复习队列加载失败')
    } finally {
      if (current === requestId.current) setLoading(false)
    }
  }, [notebookId])

  const loadAllWords = useCallback(async () => {
    const current = ++requestId.current
    setLoading(true)
    setError('')
    try {
      const result = await fetchWords({ size: 10000, sort: 'alpha_asc', notebook_id: notebookId })
      if (current !== requestId.current) return
      setAllTotal(result.total)
      setAllWords(result.words.filter(word => word.definition?.trim()))
    } catch (requestError) {
      if (current === requestId.current) setError(requestError.message || '全部单词加载失败')
    } finally {
      if (current === requestId.current) setLoading(false)
    }
  }, [notebookId])

  useEffect(() => {
    if (mode === 'daily') loadQueue()
    else loadAllWords()
    return () => { requestId.current += 1 }
  }, [loadAllWords, loadQueue, mode])

  const handleRate = useCallback(async (wordId, rating) => {
    const current = requestId.current
    try {
      const result = await rateWord(wordId, rating)
      if (current === requestId.current) {
        fetchReviewStats(notebookId).then(nextStats => {
          if (current === requestId.current) setStats(nextStats)
        }).catch(() => {})
      }
      return result
    } catch (requestError) {
      if (current === requestId.current) {
        setToast(requestError.message || '评分保存失败，请重试')
        window.setTimeout(() => { if (current === requestId.current) setToast('') }, 4000)
      }
      throw requestError
    }
  }, [notebookId])

  return (
    <div>
      {toast && <div className="toast toast-error">{toast}</div>}

      <header className="review-header">
        <div>
          <p className="review-eyebrow">Spaced repetition</p>
          <h2>{mode === 'daily' ? '今日复习' : '全部单词'}</h2>
        </div>
        {mode === 'daily' && stats && (
          <dl className="review-stats" aria-label="复习统计">
            <div><dt>到期</dt><dd>{stats.review_due}</dd></div>
            <div><dt>今日已学 · 全部本</dt><dd>{stats.new_today}/{stats.daily_new_limit}</dd></div>
            <div><dt>词库</dt><dd>{stats.total}</dd></div>
          </dl>
        )}
        {mode === 'all' && !loading && (
          <dl className="review-stats" aria-label="全部单词统计">
            <div><dt>可复习</dt><dd>{allWords.length}</dd></div>
            <div><dt>全部记录</dt><dd>{allTotal}</dd></div>
          </dl>
        )}
      </header>

      <div className="review-mode-tabs" role="tablist" aria-label="复习模式">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'daily'}
          className={mode === 'daily' ? 'active' : ''}
          onClick={() => setMode('daily')}
        >
          今日复习
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'all'}
          className={mode === 'all' ? 'active' : ''}
          onClick={() => setMode('all')}
        >
          全部单词
        </button>
      </div>

      {error ? (
        <div className="empty-state">
          <p>{error}</p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={mode === 'daily' ? loadQueue : loadAllWords}
          >
            重新加载
          </button>
        </div>
      ) : loading ? (
        <div className="loading">
          {mode === 'daily' ? '加载复习队列…' : '加载全部单词…'}
        </div>
      ) : mode === 'all' ? (
        allWords.length > 0 ? (
          <AllWordsReview words={allWords} notebookNames={notebookNames} />
        ) : (
          <section className="review-empty">
            <h2>没有可复习的单词</h2>
            <p>补全单词释义后，它们会出现在这里。</p>
          </section>
        )
      ) : cards.length === 0 ? (
        <section className="review-empty">
          <div className="srs-done-mark">✓</div>
          <h2>{stats?.total ? '今天已经复习完了' : '还没有可复习的单词'}</h2>
          <p>
            {stats?.total
              ? '到期卡片已经清空。新卡片会按每日上限逐步加入。'
              : '添加并补全单词释义后，它们会自动进入复习队列。'}
          </p>
        </section>
      ) : (
        <SpacedReview cards={cards} notebookNames={notebookNames} onRate={handleRate} onReload={loadQueue} />
      )}
    </div>
  )
}
