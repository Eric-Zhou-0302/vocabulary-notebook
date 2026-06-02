import { Routes, Route, Link, useLocation } from 'react-router-dom'
import WordList from './pages/WordList'
import WordNew from './pages/WordNew'
import WordDetail from './pages/WordDetail'
import Review from './pages/Review'

export default function App() {
  const location = useLocation()

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">
          <Link to="/">词汇笔记本</Link>
        </h1>
        <nav className="app-nav">
          <Link to="/" className={location.pathname === '/' ? 'active' : ''}>
            单词列表
          </Link>
          <Link to="/word/new" className={location.pathname === '/word/new' ? 'active' : ''}>
            添加单词
          </Link>
          <Link to="/review" className={location.pathname === '/review' ? 'active' : ''}>
            复习
          </Link>
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<WordList />} />
          <Route path="/word/new" element={<WordNew />} />
          <Route path="/word/:id" element={<WordDetail />} />
          <Route path="/review" element={<Review />} />
        </Routes>
      </main>
    </div>
  )
}
