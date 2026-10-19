import { useCallback, useEffect, useState } from 'react'
import { fetchReviewStats } from './api'

/** 导航栏待复习角标：首次加载、评分后、回到页面和每 60 秒刷新。 */
export function useDueCount() {
  const [dueCount, setDueCount] = useState(0)

  const refresh = useCallback(() => {
    fetchReviewStats()
      .then(stats => setDueCount(stats.due_today || 0))
      .catch(() => {})
  }, [])

  useEffect(() => {
    refresh()
    const timer = window.setInterval(refresh, 60_000)
    function handleVisibility() {
      if (document.visibilityState === 'visible') refresh()
    }
    window.addEventListener('review-stats-changed', refresh)
    document.addEventListener('visibilitychange', handleVisibility)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('review-stats-changed', refresh)
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }, [refresh])

  return dueCount
}
