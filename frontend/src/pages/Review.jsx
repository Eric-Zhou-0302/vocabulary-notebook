import { useCallback, useEffect, useState } from 'react'
import { fetchReviewDue, fetchReviewStats, fetchWords, rateWord } from '../api'
import AllWordsReview from '../components/AllWordsReview'
import SpacedReview from '../components/SpacedReview'

export default function Review() {
  const [mode, setMode] = useState('daily')
  const [cards, setCards] = useState([])
  const [stats, setStats] = useState(null)
  const [allWords, setAllWords] = useState([])
  const [allTotal, setAllTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')

  const loadQueue = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await fetchReviewDue(20)
      setCards(result.cards)
      setStats(result.stats)
      window.dispatchEvent(new Event('review-stats-changed'))
    } catch (requestError) {
      setError(requestError.message || '复习队列加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadAllWords = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await fetchWords({ size: 10000, sort: 'alpha_asc' })
      setAllTotal(result.total)
      setAllWords(result.words.filter(word => word.definition?.trim()))
    } catch (requestError) {
      setError(requestError.message || '全部单词加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (mode === 'daily') loadQueue()
    else loadAllWords()
  }, [loadAllWords, loadQueue, mode])

  const handleRate = useCallback(async (wordId, rating) => {
    try {
      const result = await rateWord(wordId, rating)
      fetchReviewStats().then(setStats).catch(() => {})
      return result
    } catch (requestError) {
      setToast(requestError.message || '评分保存失败，请重试')
      window.setTimeout(() => setToast(''), 4000)
      throw requestError
    }
  }, [])

  return (
    <div className="review-page">
      {toast && <div className="toast toast-error">{toast}</div>}

      <header className="review-header">
        <div>
          <p className="review-eyebrow">Spaced repetition</p>
          <h2>{mode === 'daily' ? '今日复习' : '全部单词'}</h2>
        </div>
        {mode === 'daily' && stats && (
          <dl className="review-stats" aria-label="复习统计">
            <div><dt>到期</dt><dd>{stats.review_due}</dd></div>
            <div><dt>新词</dt><dd>{stats.new_today}/{stats.daily_new_limit}</dd></div>
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
          <AllWordsReview words={allWords} />
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
        <SpacedReview cards={cards} onRate={handleRate} onReload={loadQueue} />
      )}
    </div>
  )
}
