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
      <div className="enrich-line-wrap">
        <div className="enrich-line">
          {progress.is_processing && (
            <div
              className="enrich-line-dot"
              style={{ left: `${percent}%` }}
            />
          )}
          <div
            className="enrich-line-fill"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>
      <div className="enrich-meta">
        <span className="enrich-status">
          {progress.is_processing && progress.current_word
            ? progress.current_word
            : progress.queue_size > 0
            ? `${progress.queue_size} 个在队列中`
            : progress.batch_total > 0
            ? `${progress.batch_done}/${progress.batch_total} 已完成`
            : '准备中…'}
        </span>
        {progress.batch_total > 0 && (
          <span className="enrich-pct">{percent}%</span>
        )}
      </div>
    </div>
  )
}