import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { libraryRequest } from '../api'

export default function CloudStatus() {
  const location = useLocation()
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
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
    window.addEventListener('sync-status-changed', refresh)
    return () => { alive = false; clearInterval(timer); window.removeEventListener('sync-status-changed', refresh) }
  }, [])
  const problem = error || status?.error
  const syncing = status?.syncing
  const label = problem ? 'Drive 需检查' : status?.auth_pending ? '等待 Google 授权' : syncing ? 'Drive 同步中…' : status?.connected ? 'Drive 已连接' : status ? '本地保存' : '检查连接…'
  const detail = problem || (status?.connected
    ? `${status.pending} 条变更待${status.provider === 'drive_folder' ? '写入文件夹；实际上传请查看 Drive 桌面版' : '同步'}${status.last_synced_at ? ` · 上次 ${new Date(status.last_synced_at).toLocaleTimeString()}` : ''}`
    : '连接 Google Drive 后，两台电脑可同步词汇与学习记录')
  return <Link to="/sync-settings" className={`cloud-entry ${location.pathname === '/sync-settings' ? 'active' : ''} ${problem ? 'has-error' : status?.connected ? 'connected' : ''}`} title={detail} aria-label={`云端同步：${label}`}>
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M7 18a5 5 0 0 1-.7-9.95A6 6 0 0 1 18 7a5.5 5.5 0 0 1 .5 11H7Z" /><path d="m9 13 3-3 3 3m-3-3v11" /></svg>
    <span>云端同步</span><span className="cloud-entry-dot" aria-hidden="true" />
  </Link>
}
