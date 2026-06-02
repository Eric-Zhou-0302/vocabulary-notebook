import { useState, useEffect } from 'react'
import { fetchWords, fetchDates } from '../api'
import Flashcard from '../components/Flashcard'
import SpellingTest from '../components/SpellingTest'

const TABS = [
  { key: 'browse', label: '浏览' },
  { key: 'flashcard', label: '闪卡' },
  { key: 'spelling', label: '拼写测试' },
]

export default function Review() {
  const [tab, setTab] = useState('browse')
  const [words, setWords] = useState([])
  const [dates, setDates] = useState([])
  const [date, setDate] = useState('')
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => { fetchDates().then(d => setDates(d.dates)).catch(() => {}) }, [])

  useEffect(() => {
    setLoading(true)
    fetchWords({ q, date, size: 999 }).then(data => {
      setWords(data.words)
    }).finally(() => setLoading(false))
  }, [q, date])

  return (
    <div>
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

      {tab !== 'browse' && (
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

      {loading ? (
        <div className="loading">加载中…</div>
      ) : words.length === 0 ? (
        <div className="empty-state"><p>没有单词可供复习</p></div>
      ) : tab === 'browse' ? (
        words.map(w => (
          <div key={w.id} className="word-card">
            <div className="head">
              <span className="word">{w.word}</span>
              {w.phonetic && <span className="phonetic">{w.phonetic}</span>}
            </div>
            <div className="definition">{w.definition}</div>
            {w.example && <div className="example-display" style={{ marginTop: 8, color: '#888' }}>"{w.example}"</div>}
          </div>
        ))
      ) : tab === 'flashcard' ? (
        <Flashcard words={words} />
      ) : (
        <SpellingTest words={words} />
      )}
    </div>
  )
}
