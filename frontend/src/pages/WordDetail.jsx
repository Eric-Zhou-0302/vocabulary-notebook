import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { fetchWord, updateWord, deleteWord } from '../api'
import { useBooks } from '../Books'

export default function WordDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [word, setWord] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const [editWord, setEditWord] = useState('')
  const [editDef, setEditDef] = useState('')
  const [editBook, setEditBook] = useState('default')
  const [editPhonetic, setEditPhonetic] = useState('')
  const [editExample, setEditExample] = useState('')
  const [saveError, setSaveError] = useState('')
  const { books } = useBooks()

  useEffect(() => {
    fetchWord(id)
      .then(data => setWord(data.word))
      .catch(() => setError('单词不存在'))
      .finally(() => setLoading(false))
  }, [id])

  function startEdit() {
    setEditWord(word.word)
    setEditDef(word.definition)
    setEditBook(word.notebook_id || 'default')
    setEditPhonetic(word.phonetic || '')
    setEditExample(word.example || '')
    setSaveError('')
    setEditing(true)
  }

  async function handleEdit(e) {
    e.preventDefault()
    try {
      const result = await updateWord(id, { word: editWord, definition: editDef, notebook_id: editBook, phonetic: editPhonetic, example: editExample })
      setWord(result.word)
      setEditing(false)
      window.dispatchEvent(new Event('library-changed'))
      window.dispatchEvent(new Event('review-stats-changed'))
    } catch (err) { setSaveError(err.message) }
  }

  async function handleDelete() {
    if (!window.confirm('确认删除这个单词？')) return
    try {
      await deleteWord(id)
      window.dispatchEvent(new Event('library-changed'))
      window.dispatchEvent(new Event('review-stats-changed'))
      navigate('/')
    } catch (err) { setSaveError(err.message) }
  }

  if (loading) return <div className="loading">加载中…</div>
  if (error) return (
    <div className="empty-state">
      <p>{error}</p>
      <button onClick={() => navigate(-1)}>返回列表</button>
    </div>
  )

  return (
    <div>
      <button onClick={() => navigate(-1)} className="btn btn-ghost" style={{ marginBottom: 16 }}>← 返回</button>

      <div className="detail-card">
        <p className="book-description">{books.find(book => book.id === word.notebook_id)?.name}</p>
        <div className="detail-word">{word.word}</div>
        {word.phonetic && <div className="detail-phonetic">{word.phonetic}</div>}
        <div className="detail-definition">{word.definition}</div>
        {word.example && <div className="detail-example">"{word.example}"</div>}
        <div className="detail-date">添加于 {word.created_at.slice(0, 10)}</div>
        {word.srs && <p className="book-description">已复习 {word.srs.reps} 次 · 下次 {new Date(word.srs.due_at).toLocaleString()}</p>}
        {saveError && !editing && <p role="alert">{saveError}</p>}

        <div className="btn-group">
          <button className="btn btn-primary" onClick={startEdit}>编辑</button>
          <button className="btn btn-danger" onClick={handleDelete}>删除</button>
        </div>
      </div>

      {editing && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setEditing(false) }}>
          <div className="modal" role="dialog" aria-modal="true" aria-label="编辑单词">
            <h2>编辑单词</h2>
            <form onSubmit={handleEdit}>
              <div className="form-group"><label htmlFor="edit-book">单词本</label>
                <select id="edit-book" value={editBook} onChange={e => setEditBook(e.target.value)}>
                  {books.map(book => <option key={book.id} value={book.id}>{book.name}</option>)}
                </select></div>
              <div className="form-group">
                <label htmlFor="edit-word">单词</label>
                <input id="edit-word" maxLength={200} required type="text" value={editWord} onChange={e => setEditWord(e.target.value)} />
              </div>
              <div className="form-group">
                <label htmlFor="edit-definition">释义</label>
                <textarea id="edit-definition" rows={3} value={editDef} onChange={e => setEditDef(e.target.value)} />
              </div>
              <div className="form-group"><label htmlFor="edit-phonetic">音标</label><input id="edit-phonetic" value={editPhonetic} onChange={e => setEditPhonetic(e.target.value)} /></div>
              <div className="form-group"><label htmlFor="edit-example">课程例句</label><textarea id="edit-example" rows={3} value={editExample} onChange={e => setEditExample(e.target.value)} /></div>
              {saveError && <p role="alert">{saveError}</p>}
              <div className="btn-group">
                <button type="submit" className="btn btn-primary">保存</button>
                <button type="button" className="btn btn-secondary" onClick={() => setEditing(false)}>取消</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
