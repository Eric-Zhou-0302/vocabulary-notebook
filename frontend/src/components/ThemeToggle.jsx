import { useState, useEffect } from 'react'

export default function ThemeToggle() {
  const [dark, setDark] = useState(true)

  useEffect(() => {
    const saved = localStorage.getItem('theme')
    const isDark = saved ? saved === 'dark' : true
    setDark(isDark)
    document.documentElement.dataset.theme = isDark ? 'dark' : 'light'
  }, [])

  function toggle() {
    const next = !dark
    setDark(next)
    const theme = next ? 'dark' : 'light'
    document.documentElement.dataset.theme = theme
    localStorage.setItem('theme', theme)
  }

  return (
    <button
      className="theme-toggle"
      onClick={toggle}
      title={dark ? '切换浅色' : '切换深色'}
      aria-label={dark ? '切换浅色模式' : '切换深色模式'}
    >
      {dark ? '☀' : '☾'}
    </button>
  )
}
