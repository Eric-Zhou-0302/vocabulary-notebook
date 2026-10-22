import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { fetchWord, updateWord, deleteWord } from '../api'

export default function WordDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [word, setWord] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const [editWord, setEditWord] = useState('')
  const [editDef, setEditDef] = useState('')
  const [syncNotice, setSyncNotice] = useState('')

  useEffect(() => {
    let active = true
    let request = 0
    async function refresh(fromCloud = false) {
      const current = ++request
      try {
        const data = await fetchWord(id)
        if (!active || current !== request) return
        setWord(data.word)
        if (fromCloud) setSyncNotice('云端内容已更新，当前未保存的编辑已保留。保存会提交编辑框中的内容。')
      } catch {
        if (!active || current !== request) return
        if (fromCloud) setSyncNotice('无法刷新此单词，它可能已在另一台电脑删除。当前编辑仍已保留，请先复制需要的内容。')
        else setError('单词不存在')
      } finally {
        if (active && current === request) setLoading(false)
      }
    }
    const onCloudChange = () => refresh(true)
    window.addEventListener('cloud-data-changed', onCloudChange)
    refresh()
    return () => { active = false; window.removeEventListener('cloud-data-changed', onCloudChange) }
  }, [id])

  function startEdit() {
    setEditWord(word.word)
    setEditDef(word.definition)
    setEditing(true)
  }

  async function handleEdit(e) {
    e.preventDefault()
    const result = await updateWord(id, { word: editWord, definition: editDef })
    setWord(result.word)
    setEditing(false)
  }

  async function handleDelete() {
    if (!window.confirm('确认删除这个单词？')) return
    await deleteWord(id)
    navigate(-1)
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

      {syncNotice && <p role="status">{syncNotice}</p>}
      <div className="detail-card">
        <div className="detail-word">{word.word}</div>
        {word.phonetic && <div className="detail-phonetic">{word.phonetic}</div>}
        <div className="detail-definition">{word.definition}</div>
        {word.example && <div className="detail-example">"{word.example}"</div>}
        <div className="detail-date">添加于 {word.created_at.slice(0, 10)}</div>

        <div className="btn-group">
          <button className="btn btn-primary" onClick={startEdit}>编辑</button>
          <button className="btn btn-danger" onClick={handleDelete}>删除</button>
        </div>
      </div>

      {editing && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setEditing(false) }}>
          <div className="modal">
            <h2>编辑单词</h2>
            <form onSubmit={handleEdit}>
              <div className="form-group">
                <label>单词</label>
                <input type="text" value={editWord} onChange={e => setEditWord(e.target.value)} />
              </div>
              <div className="form-group">
                <label>释义</label>
                <input type="text" value={editDef} onChange={e => setEditDef(e.target.value)} />
              </div>
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
