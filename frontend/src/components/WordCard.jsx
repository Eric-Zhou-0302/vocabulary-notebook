import { Link } from 'react-router-dom'

// case-insensitive 高亮 q 在 text 中所有出现位置
// 转义正则元字符，防止 q 含 `.`、`(` 等特殊字符导致正则语法错误
function highlight(text, q) {
  if (!q || !text) return text
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(`(${escaped})`, 'gi')
  const parts = text.split(re)
  return parts.map((part, i) =>
    part.toLowerCase() === q.toLowerCase()
      ? <mark key={i}>{part}</mark>
      : part
  )
}

export default function WordCard({ word, q = '', index = 0 }) {
  return (
    <Link
      to={`/word/${word.id}`}
      className="word-card"
      style={{ '--card-index': index }}
    >
      <div className="head">
        <span className="word">{highlight(word.word, q)}</span>
        {word.phonetic && <span className="phonetic">{word.phonetic}</span>}
      </div>
      <div className="definition">{highlight(word.definition, q)}</div>
      {word.example && <div className="example-display">"{word.example}"</div>}
    </Link>
  )
}