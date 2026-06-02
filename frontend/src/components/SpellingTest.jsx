import { useState, useEffect } from 'react'

export default function SpellingTest({ words }) {
  const [questions, setQuestions] = useState([])
  const [index, setIndex] = useState(0)
  const [input, setInput] = useState('')
  const [feedback, setFeedback] = useState(null)
  const [correct, setCorrect] = useState([])
  const [wrong, setWrong] = useState([])
  const [done, setDone] = useState(false)

  useEffect(() => {
    const shuffled = [...words].sort(() => Math.random() - 0.5)
    setQuestions(shuffled)
    setIndex(0)
    setInput('')
    setFeedback(null)
    setCorrect([])
    setWrong([])
    setDone(false)
  }, [words])

  const current = questions[index]

  function handleSubmit(e) {
    e.preventDefault()
    if (!input.trim() || feedback) return
    const isCorrect = input.trim().toLowerCase() === current.word.toLowerCase()
    if (isCorrect) {
      setCorrect(c => [...c, current])
    } else {
      setWrong(c => [...c, current])
    }
    setFeedback({ correct: isCorrect, answer: current.word })
  }

  function handleNext() {
    if (index + 1 >= questions.length) {
      setDone(true)
    } else {
      setIndex(i => i + 1)
      setInput('')
      setFeedback(null)
    }
  }

  function restart(retryWrong = false) {
    const pool = retryWrong ? wrong : [...words].sort(() => Math.random() - 0.5)
    setQuestions(pool)
    setIndex(0)
    setInput('')
    setFeedback(null)
    setCorrect([])
    setWrong([])
    setDone(false)
  }

  if (done) {
    return (
      <div className="spelling-results">
        <h2>测试完成</h2>
        <p className="stats">
          正确 <span>{correct.length}</span> · 错误 <span className="wrong-count">{wrong.length}</span>
        </p>
        {wrong.length > 0 && (
          <div className="wrong-list">
            <h3>错题列表</h3>
            <ul>
              {wrong.map(w => (
                <li key={w.id}><b>{w.word}</b> — {w.definition}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="btn-group" style={{ justifyContent: 'center' }}>
          <button className="btn btn-primary" onClick={() => restart(false)}>重新测试</button>
          {wrong.length > 0 && (
            <button className="btn btn-secondary" onClick={() => restart(true)}>只测错题</button>
          )}
        </div>
      </div>
    )
  }

  if (questions.length === 0) return <div className="loading">没有单词可测试</div>

  return (
    <div className="spelling-container">
      <div className="flashcard-progress">第 {index + 1} / {questions.length} 个</div>

      <div className="spelling-card">
        <div className="spelling-definition">{current.definition}</div>
        <form onSubmit={handleSubmit}>
          <input
            type="text"
            className="spelling-input"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="输入英文拼写"
            autoFocus
            disabled={!!feedback}
          />
          {!feedback && (
            <button type="submit" className="btn btn-primary" style={{ marginTop: 16 }}>
              提交
            </button>
          )}
        </form>
        {feedback && (
          <div className={`spelling-feedback ${feedback.correct ? 'correct' : 'wrong'}`}>
            {feedback.correct ? '正确！' : `正确拼写：${feedback.answer}`}
          </div>
        )}
        {feedback && (
          <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={handleNext}>
            {index + 1 >= questions.length ? '查看结果' : '下一题'}
          </button>
        )}
      </div>
    </div>
  )
}
