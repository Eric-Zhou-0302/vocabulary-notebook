import { useState, useEffect, useCallback } from 'react'

export default function Flashcard({ words }) {
  const [queue, setQueue] = useState([])
  const [index, setIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    const shuffled = [...words].sort(() => Math.random() - 0.5)
    setQueue(shuffled)
    setIndex(0)
    setFlipped(false)
    setDone(false)
  }, [words])

  const current = queue[index]

  const handleKey = useCallback((e) => {
    if (!current) return
    if (e.key === ' ') { e.preventDefault(); setFlipped(f => !f) }
    if (!flipped) return
    if (e.key === 'ArrowLeft') handleForgot()
    if (e.key === 'ArrowRight') handleRemember()
  }, [current, flipped])

  useEffect(() => {
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [handleKey])

  function handleForgot() {
    setQueue(prev => [...prev, prev[index]])
    goNext()
  }

  function handleRemember() {
    goNext()
  }

  function goNext() {
    if (index + 1 >= queue.length) {
      setDone(true)
    } else {
      setIndex(i => i + 1)
      setFlipped(false)
    }
  }

  function restart() {
    const shuffled = [...words].sort(() => Math.random() - 0.5)
    setQueue(shuffled)
    setIndex(0)
    setFlipped(false)
    setDone(false)
  }

  if (done) {
    return (
      <div className="flashcard-done">
        <h2>本轮完成</h2>
        <p>已复习 {queue.length} 个单词</p>
        <button className="btn btn-primary" onClick={restart} style={{ marginTop: 16 }}>
          再来一轮
        </button>
      </div>
    )
  }

  if (!current) return <div className="loading">没有单词可复习</div>

  return (
    <div className="flashcard-container">
      <div className="flashcard-progress">
        第 {index + 1} / {queue.length} 个 · 空格翻转 · ← 忘了 · → 记得
      </div>

      <div className="flashcard" onClick={() => setFlipped(f => !f)}>
        <div className={`flashcard-inner ${flipped ? 'flipped' : ''}`}>
          <div className="flashcard-front">
            <span className="word-display">{current.word}</span>
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
        <div className="flashcard-actions">
          <button className="btn btn-danger" onClick={handleForgot}>忘了</button>
          <button className="btn btn-primary" onClick={handleRemember}>记得</button>
        </div>
      )}
    </div>
  )
}
