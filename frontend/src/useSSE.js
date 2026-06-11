import { useEffect } from 'react'

/**
 * 订阅后端 SSE 事件流，enriched 事件触发时回调 onEnriched(wordId, data)
 * 返回 cleanup 函数在组件卸载时断开连接
 */
export function useSSE(onEnriched) {
  useEffect(() => {
    let aborted = false
    let reader = null

    async function connect() {
      try {
        const res = await fetch('/api/events', { headers: { Accept: 'text/event-stream' } })
        if (!res.ok || aborted) return
        reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (!aborted) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          // 解析 SSE 帧
          const parts = buffer.split('\n\n')
          buffer = parts.pop() || ''

          for (const part of parts) {
            const lines = part.split('\n')
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const event = JSON.parse(line.slice(6))
                  if (event.type === 'enriched') {
                    onEnriched(event.word_id, {
                      phonetic: event.phonetic,
                      definition: event.definition,
                      example: event.example,
                    })
                  }
                } catch {
                  // 忽略解析失败的行
                }
              }
            }
          }
        }
      } catch {
        // 连接失败静默处理，SSE 不是关键功能
      } finally {
        if (reader) {
          try { reader.cancel() } catch {}
        }
      }
    }

    connect()

    return () => {
      aborted = true
      if (reader) {
        try { reader.cancel() } catch {}
      }
    }
  }, [onEnriched])
}
