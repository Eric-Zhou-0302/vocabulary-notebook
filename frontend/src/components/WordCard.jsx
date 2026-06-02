import { Link } from 'react-router-dom'

export default function WordCard({ word }) {
  return (
    <Link to={`/word/${word.id}`} className="word-card">
      <div className="head">
        <span className="word">{word.word}</span>
        {word.phonetic && <span className="phonetic">{word.phonetic}</span>}
      </div>
      <div className="definition">{word.definition}</div>
    </Link>
  )
}
