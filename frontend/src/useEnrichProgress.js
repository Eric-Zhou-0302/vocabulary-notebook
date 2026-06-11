import { useState, useEffect } from 'react'

export function useEnrichProgress(enabled = false) {
  const [progress, setProgress] = useState({
    queue_size: 0,
    current_word: null,
    batch_total: 0,
    batch_done: 0,
    total_missing: 0,
    is_processing: false,
  })

  useEffect(() => {
    if (!enabled) return

    let timer = null

    async function poll() {
      try {
        const res = await fetch('/api/enrich/progress')
        if (res.ok) {
          const data = await res.json()
          setProgress(data)
          if (!data.is_processing && data.queue_size === 0) {
            clearInterval(timer)
          }
        }
      } catch {
        // 忽略
      }
    }

    poll()
    timer = setInterval(poll, 2000)
    return () => clearInterval(timer)
  }, [enabled])

  return progress
}