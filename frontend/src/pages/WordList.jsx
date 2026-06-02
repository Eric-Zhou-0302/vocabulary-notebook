import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { fetchWords, fetchDates } from '../api'
import WordCard from '../components/WordCard'
import ExportMenu from '../components/ExportMenu'

export default function WordList() {
  const [words, setWords] = useState([])
  const [dates, setDates] = useState([])
  const [q, setQ] = useState('')
  const [date, setDate] = useState('')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => { fetchDates().then(d => setDates(d.dates)).catch(() => {}) }, [])

  useEffect(() => {
    setLoading(true)
    fetchWords({ q, date, page }).then(data => {
      setWords(data.words)
      setTotalPages(data.pages)
    }).finally(() => setLoading(false))
  }, [q, date, page])

  return (
    <div>
      <div className="toolbar">
        <input
          type="text"
          placeholder="搜索单词或释义…"
          value={q}
          onChange={e => { setQ(e.target.value); setPage(1) }}
        />
        <select value={date} onChange={e => { setDate(e.target.value); setPage(1) }}>
          <option value="">全部日期</option>
          {dates.map(d => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
        <ExportMenu q={q} date={date} />
        <Link to="/word/new" className="btn btn-primary">+ 添加</Link>
      </div>

      {loading ? (
        <div className="loading">加载中…</div>
      ) : words.length === 0 ? (
        <div className="empty-state">
          <p>{q || date ? '无匹配单词' : '还没有单词'}</p>
          {q || date ? (
            <button className="btn btn-ghost" onClick={() => { setQ(''); setDate('') }}>
              清除筛选
            </button>
          ) : (
            <Link to="/word/new">去添加第一个单词</Link>
          )}
        </div>
      ) : (
        <>
          {words.map(w => <WordCard key={w.id} word={w} />)}
          {totalPages > 1 && (
            <div className="pagination">
              <button
                className="btn btn-secondary"
                disabled={page <= 1}
                onClick={() => setPage(p => p - 1)}
              >
                上一页
              </button>
              <span>{page} / {totalPages}</span>
              <button
                className="btn btn-secondary"
                disabled={page >= totalPages}
                onClick={() => setPage(p => p + 1)}
              >
                下一页
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
