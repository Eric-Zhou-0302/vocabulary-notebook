import { useState, useEffect } from 'react'

export default function ModelStatus() {
  const [health, setHealth] = useState(null) // null = checking

  useEffect(() => {
    let aborted = false

    async function check() {
      try {
        const res = await fetch('/api/health')
        const data = await res.json()
        if (!aborted) setHealth(data)
      } catch {
        if (!aborted) setHealth({ provider: 'unknown', status: 'disconnected' })
      }
    }

    check()
    const timer = setInterval(check, 5 * 60 * 1000) // 每 5min 检测一次
    return () => {
      aborted = true
      clearInterval(timer)
    }
  }, [])

  if (health === null) return null // 首次加载不显示

  const { provider, status } = health
  const connected = status === 'connected'
  const providerLabel = provider === 'ollama' ? 'Ollama' : provider === 'deepseek' ? 'DeepSeek' : provider

  return (
    <span
      className={`model-status ${connected ? 'on' : 'off'}`}
      title={connected ? `${providerLabel} 已连接` : `${providerLabel} 离线 — 音标和释义将无法自动补充`}
    >
      <span className="model-dot" />
      {connected ? `${providerLabel} 已连接` : `${providerLabel} 离线`}
    </span>
  )
}
