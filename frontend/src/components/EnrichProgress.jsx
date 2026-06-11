import { useEnrichProgress } from '../useEnrichProgress'

export default function EnrichProgress({ active }) {
  const progress = useEnrichProgress(active)

  if (!active && !progress.is_processing && progress.queue_size === 0) return null
  if (!progress.is_processing && progress.queue_size === 0 && progress.batch_total === 0) return null

  const percent = progress.batch_total > 0
    ? Math.round((progress.batch_done / progress.batch_total) * 100)
    : 0

  return (
    <div className="enrich-progress">
      <div className="enrich-progress-info">
        <span>
          {progress.is_processing && progress.current_word
            ? `正在补全：${progress.current_word}`
            : progress.queue_size > 0
            ? `队列中 ${progress.queue_size} 个单词…`
            : progress.batch_total > 0
            ? `已完成 ${progress.batch_done}/${progress.batch_total}`
            : '准备中…'}
        </span>
        {progress.batch_total > 0 && (
          <span className="enrich-progress-pct">{percent}%</span>
        )}
      </div>
      {progress.batch_total > 0 && (
        <div className="enrich-progress-bar">
          <div
            className="enrich-progress-fill"
            style={{ width: `${percent}%` }}
          />
        </div>
      )}
    </div>
  )
}