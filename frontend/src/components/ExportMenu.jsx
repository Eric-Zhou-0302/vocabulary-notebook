import { useState, useRef, useEffect } from 'react'
import { exportUrl } from '../api'

export default function ExportMenu({ q, date }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function doExport(format) {
    window.open(exportUrl(format, { q, date }), '_blank')
    setOpen(false)
  }

  return (
    <div className="export-wrapper" ref={ref}>
      <button className="btn btn-secondary" onClick={() => setOpen(!open)}>
        导出
      </button>
      {open && (
        <div className="export-menu">
          <button onClick={() => doExport('json')}>JSON</button>
          <button onClick={() => doExport('csv')}>CSV</button>
          <button onClick={() => doExport('pdf')}>PDF</button>
        </div>
      )}
    </div>
  )
}
