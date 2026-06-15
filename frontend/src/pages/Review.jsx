import { useState, useEffect, useCallback } from 'react'
import { fetchWords, fetchDates } from '../api'
import { useSSE } from '../useSSE'
import SpacedReview from '../components/SpacedReview'
import SpellingTest from '../components/SpellingTest'

const TABS = [
  { key: 'browse', label: '浏览' },
  { key: 'srs', label: '间隔复习' },
  { key: 'spelling', label: '拼写测试' },
]

export default function Review() {
  const [tab, setTab] = useState('browse')
  const [words, setWords] = useState([])
  const [dates, setDates] = useState([])
  const [date, setDate] = useState('')
  const [q, setQ] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  // SRS 状态
  const [srsCards, setSrsCards] = useState([])
  const [srsStats, setSrsStats] = useState(null)
  const [srsLoading, setSrsLoading] = useState(false)
  const [toast, setToast] = useState('')

  useEffect(() => { fetchDates().then(d => setDates(d.dates)).catch(() => {}) }, [])

  useEffect(() => {
    setLoading(true)
    setError('')
    fetchWords({ q, date, size: 10000 })
      .then(data => setWords(data.words))
      .catch(() => setError('加载失败，请确认后端服务是否运行'))
      .finally(() => setLoading(false))
  }, [q, date])

  const handleEnriched = useCallback((wordId, data) => {
    setWords(prev => prev.map(w =>
      w.id === wordId ? { ...w, ...data } : w
    ))
  }, [])

  useSSE(handleEnriched)

  // SRS：拉取 due 队列
  const fetchSrsQueue = useCallback(async () => {
    setSrsLoading(true)
    try {
      const res = await fetch('/api/review/due?new_limit=20&limit=20')
      if (res.ok) {
        const data = await res.json()
        setSrsCards(data.cards)
        setSrsStats(data.stats)
      }
    } catch {
      setError('复习队列加载失败')
    } finally {
      setSrsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (tab === 'srs') fetchSrsQueue()
  }, [tab, fetchSrsQueue])

  // 评分
  const handleRate = useCallback(async (wordId, rating) => {
    const res = await fetch(`/api/words/${wordId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || '评分失败')
    }
    return res.json()
  }, [])

  function showToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(''), 3000)
  }

  const handleSessionEnd = useCallback(() => {
    fetchSrsQueue()
  }, [fetchSrsQueue])

  return (
    <div>
      {toast && <div className="toast toast-info">{toast}</div>}
      <div className="tabs">
        {TABS.map(t => (
          <button
            key={t.key}
            className={`tab ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'srs' && srsStats && (
        <div className="srs-header">
          {srsStats.due_today > 0
            ? <>今日待复习 <b>{srsStats.due_today}</b> · 全部 {srsStats.total}</>
            : <span className="srs-done-hint">今日已完成 ✓</span>}
        </div>
      )}

      {tab !== 'browse' && tab !== 'srs' && (
        <div className="toolbar">
          <input
            type="text" placeholder="筛选单词…" value={q}
            onChange={e => setQ(e.target.value)}
          />
          <select value={date} onChange={e => setDate(e.target.value)}>
            <option value="">全部日期</option>
            {dates.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
      )}

      {error && <div className="empty-state"><p>{error}</p></div>}
      {!error && loading ? (
        <div className="loading">加载中…</div>
      ) : !error && words.length === 0 ? (
        <div className="empty-state"><p>没有单词可供复习</p></div>
      ) : tab === 'browse' ? (
        words.map(w => (
          <div key={w.id} className="word-card">
            <div className="head">
              <span className="word">{w.word}</span>
              {w.phonetic && <span className="phonetic">{w.phonetic}</span>}
            </div>
            <div className="definition">{w.definition}</div>
            {w.example && <div className="example-display">"{w.example}"</div>}
          </div>
        ))
      ) : tab === 'srs' ? (
        srsLoading ? (
          <div className="loading">加载复习队列…</div>
        ) : (
          <SpacedReview
            cards={srsCards}
            onRate={handleRate}
            onSessionEnd={handleSessionEnd}
          />
        )
      ) : (
        <SpellingTest words={words} />
      )}
    </div>
  )
}
