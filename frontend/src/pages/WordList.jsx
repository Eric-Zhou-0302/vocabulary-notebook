import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { fetchWords, fetchDates, enrichMissing } from '../api'
import { useSSE } from '../useSSE'
import WordCard from '../components/WordCard'
import ExportMenu from '../components/ExportMenu'

export default function WordList() {
  const [words, setWords] = useState([])
  const [dates, setDates] = useState([])
  const [q, setQ] = useState('')
  const [date, setDate] = useState('')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [enriching, setEnriching] = useState(false)
  const [toast, setToast] = useState('')

  useEffect(() => { fetchDates().then(d => setDates(d.dates)).catch(() => {}) }, [])

  useEffect(() => {
    setLoading(true)
    setError('')
    fetchWords({ q, date, page })
      .then(data => {
        setWords(data.words)
        setTotalPages(data.pages)
      })
      .catch(() => setError('加载失败，请确认后端服务是否运行'))
      .finally(() => setLoading(false))
  }, [q, date, page])

  // SSE 实时更新 — Ollama 补充数据后无需刷新
  const handleEnriched = useCallback((wordId, data) => {
    setWords(prev => prev.map(w =>
      w.id === wordId ? { ...w, ...data } : w
    ))
  }, [])

  useSSE(handleEnriched)

  const hasMissing = !loading && words.some(w => !w.definition)

  async function handleEnrichMissing() {
    if (!hasMissing) {
      setToast('当前列表没有需要补全的单词')
      setTimeout(() => setToast(''), 3000)
      return
    }
    setEnriching(true)
    setToast('')
    try {
      const result = await enrichMissing()
      setToast(result.message)
      setTimeout(() => setToast(''), 4000)
    } catch {
      setToast('补全请求失败，请确认后端运行中')
      setTimeout(() => setToast(''), 4000)
    } finally {
      setEnriching(false)
    }
  }

  return (
    <div>
      {toast && <div className="toast toast-info">{toast}</div>}
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
        <button
          className="btn btn-secondary"
          onClick={handleEnrichMissing}
          disabled={enriching || !hasMissing}
          title={!hasMissing ? '当前列表所有单词已补全' : undefined}
        >
          {enriching ? '补全中…' : '补全缺失'}
        </button>
        <ExportMenu q={q} date={date} />
        <Link to="/word/new" className="btn btn-primary">+ 添加</Link>
      </div>

      {error && <div className="empty-state"><p>{error}</p></div>}
      {!error && loading ? (
        <div className="loading">加载中…</div>
      ) : !error && words.length === 0 ? (
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
