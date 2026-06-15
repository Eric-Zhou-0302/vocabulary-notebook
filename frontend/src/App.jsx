import { useState, useRef, useCallback } from 'react'
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import WordList from './pages/WordList'
import WordNew from './pages/WordNew'
import WordDetail from './pages/WordDetail'
import Review from './pages/Review'
import ThemeToggle from './components/ThemeToggle'
import ModelStatus from './components/ModelStatus'
import { useDueCount } from './useDueCount'
import { useGlobalShortcuts } from './useGlobalShortcuts'
import HelpModal from './components/HelpModal'

export default function App() {
  const location = useLocation()
  const dueToday = useDueCount()
  const searchInputRef = useRef(null)
  const [helpOpen, setHelpOpen] = useState(false)
  const toggleHelp = useCallback(() => setHelpOpen(o => !o), [])

  useGlobalShortcuts({ searchInputRef, toggleHelp })

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1 className="app-title">
            <Link to="/">词汇笔记本</Link>
          </h1>
          <ModelStatus />
        </div>
        <nav className="app-nav">
          <Link to="/" className={location.pathname === '/' ? 'active' : ''}>
            单词列表
          </Link>
          <Link to="/review" className={location.pathname === '/review' ? 'active' : ''}>
            复习 {dueToday > 0 && <span className="nav-badge">{dueToday}</span>}
          </Link>
          <Link to="/word/new" className={location.pathname === '/word/new' ? 'active' : ''}>
            添加单词
          </Link>
          <ThemeToggle />
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<WordList searchInputRef={searchInputRef} />} />
          <Route path="/word/new" element={<WordNew />} />
          <Route path="/word/:id" element={<WordDetail />} />
          <Route path="/review" element={<Review />} />
        </Routes>
      </main>
      <HelpModal open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  )
}
