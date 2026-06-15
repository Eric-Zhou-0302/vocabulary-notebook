import { useState, useEffect } from 'react'

/**
 * 轮询 /api/review/stats，返回今日 due 总数。
 * 用于 App nav 角标。
 */
export function useDueCount(intervalMs = 60000) {
  const [dueToday, setDueToday] = useState(0)

  useEffect(() => {
    let timer = null
    let aborted = false

    async function fetch() {
      try {
        const res = await fetch('/api/review/stats')
        if (res.ok && !aborted) {
          const data = await res.json()
          setDueToday(data.due_today || 0)
        }
      } catch {
        // 忽略网络错误
      }
    }

    fetch()
    timer = setInterval(fetch, intervalMs)
    return () => {
      aborted = true
      if (timer) clearInterval(timer)
    }
  }, [intervalMs])

  return dueToday
}
