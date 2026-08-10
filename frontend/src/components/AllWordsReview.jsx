import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

function shuffle(items) {
  const result = [...items]
  for (let index = result.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1))
    const current = result[index]
    result[index] = result[swapIndex]
    result[swapIndex] = current
  }
  return result
}

export default function AllWordsReview({ words }) {
  const [order, setOrder] = useState('alpha')
  const [randomSeed, setRandomSeed] = useState(0)
  const [index, setIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [done, setDone] = useState(false)
  const actionsRef = useRef(null)

  const deck = useMemo(() => {
    const alphabetic = [...words].sort((a, b) => a.word.localeCompare(b.word, 'en'))
    return order === 'random' ? shuffle(alphabetic) : alphabetic
  }, [order, randomSeed, words])

  useEffect(() => {
    setIndex(0)
    setFlipped(false)
    setDone(false)
  }, [deck])

  const current = deck[index]

  useEffect(() => {
    if (flipped) {
      actionsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [flipped])

  const goPrevious = useCallback(() => {
    if (index <= 0) return
    setIndex(previous => previous - 1)
    setFlipped(false)
  }, [index])

  const goNext = useCallback(() => {
    if (!flipped || !current) return
    if (index + 1 >= deck.length) {
      setDone(true)
      return
    }
    setIndex(previous => previous + 1)
    setFlipped(false)
  }, [current, deck.length, flipped, index])

  const restart = useCallback(() => {
    if (order === 'random') setRandomSeed(seed => seed + 1)
    setIndex(0)
    setFlipped(false)
    setDone(false)
  }, [order])

  useEffect(() => {
    function handleKey(event) {
      const tagName = event.target?.tagName
      if (tagName === 'INPUT' || tagName === 'TEXTAREA' || event.target?.isContentEditable) return
      if (event.ctrlKey || event.metaKey || event.altKey) return

      if ((event.key === ' ' || event.key === 'Enter') && current && !flipped) {
        if (tagName === 'BUTTON') return
        event.preventDefault()
        setFlipped(true)
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault()
        goPrevious()
      } else if (event.key === 'ArrowRight' && flipped) {
        event.preventDefault()
        goNext()
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [current, flipped, goNext, goPrevious])

  if (done) {
    return (
      <section className="srs-done" aria-live="polite">
        <div className="srs-done-mark">✓</div>
        <h2>全部浏览完成</h2>
        <p>本轮共翻阅 {deck.length} 个单词，不影响每日复习计划。</p>
        <button type="button" className="btn btn-primary" onClick={restart}>
          重新开始
        </button>
      </section>
    )
  }

  if (!current) return null

  function changeOrder(nextOrder) {
    // 排序变化与翻面状态必须在同一帧重置，避免新单词沿用旧卡背面。
    setIndex(0)
    setFlipped(false)
    setDone(false)
    if (nextOrder === order) {
      if (nextOrder === 'random') setRandomSeed(seed => seed + 1)
      return
    }
    setOrder(nextOrder)
  }

  return (
    <div className="srs-container all-review-container">
      <div className="all-review-toolbar">
        <div className="order-switch" role="group" aria-label="单词顺序">
          <button
            type="button"
            className={order === 'alpha' ? 'active' : ''}
            onClick={() => changeOrder('alpha')}
          >
            A–Z 顺序
          </button>
          <button
            type="button"
            className={order === 'random' ? 'active' : ''}
            onClick={() => changeOrder('random')}
          >
            {order === 'random' ? '重新随机' : '随机顺序'}
          </button>
        </div>
        <div className="srs-progress">
          第 {index + 1} / {deck.length} 个 · 空格翻面 · ← → 切换
        </div>
      </div>

      <button
        type="button"
        className="flashcard"
        onClick={() => !flipped && setFlipped(true)}
        aria-label={flipped ? `${current.word} 的释义` : `单词 ${current.word}，点击查看释义`}
        aria-pressed={flipped}
      >
        <span
          key={`${order}-${randomSeed}-${index}-${current.id}`}
          className={`flashcard-inner ${flipped ? 'flipped' : ''}`}
        >
          <span className="flashcard-front">
            <span className="word-display">{current.word}</span>
            {current.phonetic && <span className="phonetic-display">{current.phonetic}</span>}
            <span className="flip-hint">点击或按空格查看答案</span>
          </span>
          <span className="flashcard-back">
            <span className="word-display">{current.word}</span>
            {current.phonetic && <span className="phonetic-display">{current.phonetic}</span>}
            <span className="definition-display">{current.definition}</span>
            {current.example && <span className="example-display">“{current.example}”</span>}
          </span>
        </span>
      </button>

      <div ref={actionsRef} className="all-review-actions">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={goPrevious}
          disabled={index === 0}
        >
          ← 上一个
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={goNext}
          disabled={!flipped}
        >
          {index + 1 >= deck.length ? '完成本轮' : '下一个 →'}
        </button>
      </div>
    </div>
  )
}
