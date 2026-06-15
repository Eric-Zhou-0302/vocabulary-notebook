import { useState, useEffect, useCallback } from 'react'

const RATING_LABELS = {
  1: '重来',
  2: '困难',
  3: '良好',
  4: '简单',
}

const RATING_CLASS = {
  1: 'rating-again',
  2: 'rating-hard',
  3: 'rating-good',
  4: 'rating-easy',
}

/**
 * FSRS 间隔复习组件
 * 接收从 /api/review/due 拉来的 cards 队列，按 4 档评分推进。
 * Again 在队列末尾重新插入一次（同 session 重学）。
 */
export default function SpacedReview({ cards, onRate, onSessionEnd }) {
  const [queue, setQueue] = useState([])
  const [index, setIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [done, setDone] = useState(false)
  const [reviewedCount, setReviewedCount] = useState(0)
  const [newCount, setNewCount] = useState(0)
  const [reviewCount, setReviewCount] = useState(0)
  const [newReviewed, setNewReviewed] = useState(0)
  const [reviewReviewed, setReviewReviewed] = useState(0)

  useEffect(() => {
    setQueue(cards)
    setIndex(0)
    setFlipped(false)
    setDone(false)
    setReviewedCount(0)
    setNewCount(cards.filter(c => !c.srs).length)
    setReviewCount(cards.filter(c => c.srs).length)
    setNewReviewed(0)
    setReviewReviewed(0)
  }, [cards])

  const current = queue[index]

  const handleRate = useCallback(async (rating) => {
    if (!current || !flipped) return
    const isNew = !current.srs
    setReviewedCount(c => c + 1)
    if (isNew) {
      setNewCount(c => c - 1)
      setNewReviewed(c => c + 1)
    } else {
      setReviewCount(c => c - 1)
      setReviewReviewed(c => c + 1)
    }

    try {
      await onRate(current.id, rating)
    } catch {
      // 失败不前进：弹 toast 由父组件处理
      return
    }

    if (rating === 1) {
      // Again：队尾再插一次（spec：所有 Again 都在同 session 重学）
      setQueue(prev => [...prev, current])
    }

    if (index + 1 >= queue.length) {
      setDone(true)
    } else {
      setIndex(i => i + 1)
      setFlipped(false)
    }
  }, [current, flipped, index, queue, onRate])

  const handleKey = useCallback((e) => {
    if (!current) return
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault()
      if (!flipped) setFlipped(true)
      return
    }
    if (flipped && ['1', '2', '3', '4'].includes(e.key)) {
      e.preventDefault()
      handleRate(parseInt(e.key, 10))
    }
  }, [current, flipped, handleRate])

  useEffect(() => {
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [handleKey])

  if (done) {
    return (
      <div className="srs-done">
        <h2>本轮完成</h2>
        <p>本轮复习 <b>{reviewedCount}</b> 个（新词 {newReviewed} · 复习 {reviewReviewed}）</p>
        <button className="btn btn-primary" onClick={onSessionEnd} style={{ marginTop: 16 }}>
          再来一批
        </button>
      </div>
    )
  }

  if (!current) {
    return <div className="empty-state"><p>没有待复习的单词</p></div>
  }

  return (
    <div className="srs-container">
      <div className="srs-progress">
        第 {index + 1} / {queue.length} 个 · 空格翻面 · 1-4 评分
      </div>

      <div className="flashcard" onClick={() => !flipped && setFlipped(true)}>
        <div className={`flashcard-inner ${flipped ? 'flipped' : ''}`}>
          <div className="flashcard-front">
            <span className="word-display">{current.word}</span>
            {current.phonetic && <span className="phonetic-display">{current.phonetic}</span>}
          </div>
          <div className="flashcard-back">
            <span className="word-display">{current.word}</span>
            {current.phonetic && <span className="phonetic-display">{current.phonetic}</span>}
            <span className="definition-display">{current.definition}</span>
            {current.example && <span className="example-display">"{current.example}"</span>}
          </div>
        </div>
      </div>

      {flipped && (
        <div className="srs-rating-grid">
          {[1, 2, 3, 4].map(r => (
            <button
              key={r}
              type="button"
              className={`srs-rating-btn ${RATING_CLASS[r]}`}
              onClick={() => handleRate(r)}
            >
              <span className="rating-label">{r} · {RATING_LABELS[r]}</span>
              <span className="rating-interval">{current.predicted_intervals?.[String(r)] || '?'}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}