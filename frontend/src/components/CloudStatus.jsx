import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { libraryRequest } from '../api'

export default function CloudStatus() {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)
  const pulled = useRef(undefined)
  useEffect(() => {
    let alive = true
    async function refresh() {
      try {
        const next = await libraryRequest('/sync/status')
        if (!alive) return
        setStatus(next)
        setError('')
        if (pulled.current !== undefined && pulled.current !== next.last_pulled_at) {
          window.dispatchEvent(new Event('cloud-data-changed'))
          window.dispatchEvent(new Event('library-changed'))
        }
        pulled.current = next.last_pulled_at
      } catch (err) { if (alive) setError(err.message) }
    }
    refresh()
    const timer = setInterval(refresh, 3000)
    return () => { alive = false; clearInterval(timer) }
  }, [])
  async function sync() {
    setRunning(true)
    try {
      await libraryRequest('/sync/run', 'POST')
      setStatus(await libraryRequest('/sync/status'))
      setError('')
    } catch (err) { setError(err.message) }
    finally { setRunning(false) }
  }
  return <aside className="cloud-status" aria-label="云端同步状态">
    <div aria-live="polite">
      <strong>{status?.syncing || running ? '正在同步…' : status?.connected ? status.provider === 'drive_folder' ? 'Drive 同步文件夹已连接' : 'Google Drive 已连接' : '本地保存'}</strong>
      <span>{error || status?.error || (status?.connected
        ? `${status.pending} 条变更待${status.provider === 'drive_folder' ? '写入文件夹' : '同步'}${status.last_synced_at ? ` · 上次 ${new Date(status.last_synced_at).toLocaleTimeString()}` : ''}`
        : '连接 Google Drive 后，两台电脑可同步词汇与学习记录')}</span>
    </div>
    <div className="btn-group">
      {status?.connected && <button className="btn btn-secondary" disabled={running || status.syncing} onClick={sync}>立即同步</button>}
      <Link className="btn btn-ghost" to="/settings">同步与备份</Link>
    </div>
  </aside>
}
