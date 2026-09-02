import { useCallback, useEffect, useState } from 'react'
import './Recommendations.css'
import './Quarantine.css'

const API_BASE = 'http://127.0.0.1:8756'

function formatQuarantinedAt(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso

  const diffSec = Math.round((Date.now() - date.getTime()) / 1000)

  if (diffSec < 60) return 'just now'
  const diffMin = Math.round(diffSec / 60)
  if (diffMin < 60) return `${diffMin} minute${diffMin === 1 ? '' : 's'} ago`
  const diffHour = Math.round(diffMin / 60)
  if (diffHour < 24) return `${diffHour} hour${diffHour === 1 ? '' : 's'} ago`
  const diffDay = Math.round(diffHour / 24)
  if (diffDay < 7) return `${diffDay} day${diffDay === 1 ? '' : 's'} ago`

  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function QuarantineCard({ item, actionState, onRestore }) {
  const phase = actionState?.phase

  return (
    <div className="q-card">
      <div className="q-card-header">
        <span className="q-path mono">{item.original_path}</span>
      </div>

      <p className="q-reason">{item.reason}</p>
      <p className="q-meta text-dim">
        Quarantined {formatQuarantinedAt(item.quarantined_at)}
      </p>

      <div className="q-actions">
        {phase !== 'restoring' && (
          <button type="button" className="btn btn-primary" onClick={() => onRestore(item)}>
            {phase === 'error' ? 'Retry restore' : 'Restore'}
          </button>
        )}

        {phase === 'restoring' && <span className="text-dim">Restoring…</span>}

        {phase === 'error' && (
          <span className="confirm confirm-blocked">{actionState.message}</span>
        )}
      </div>
    </div>
  )
}

function Quarantine() {
  const [status, setStatus] = useState('loading') // loading | loaded | error
  const [items, setItems] = useState([])
  const [errorMessage, setErrorMessage] = useState('')
  const [actions, setActions] = useState({})
  const [banner, setBanner] = useState('')

  const fetchQuarantined = useCallback(async () => {
    setStatus('loading')
    setErrorMessage('')
    try {
      const res = await fetch(`${API_BASE}/api/quarantine`)
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'NOVA could not load the quarantine list.')
      }
      setItems(data)
      setActions({})
      setStatus('loaded')
    } catch (err) {
      setItems([])
      setStatus('error')
      setErrorMessage(
        err instanceof TypeError
          ? "Couldn't reach the NOVA backend at 127.0.0.1:8756 — is it running?"
          : err.message,
      )
    }
  }, [])

  useEffect(() => {
    fetchQuarantined()
  }, [fetchQuarantined])

  useEffect(() => {
    if (!banner) return undefined
    const timer = setTimeout(() => setBanner(''), 4000)
    return () => clearTimeout(timer)
  }, [banner])

  async function handleRestore(item) {
    setBanner('')
    setActions((prev) => ({ ...prev, [item.quarantine_id]: { phase: 'restoring' } }))
    try {
      const res = await fetch(`${API_BASE}/api/quarantine/${item.quarantine_id}/restore`, {
        method: 'POST',
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'NOVA could not restore this file.')
      }
      setItems((prev) => prev.filter((i) => i.quarantine_id !== item.quarantine_id))
      setActions((prev) => {
        const next = { ...prev }
        delete next[item.quarantine_id]
        return next
      })
      setBanner(`Restored to ${item.original_path}`)
    } catch (err) {
      setActions((prev) => ({
        ...prev,
        [item.quarantine_id]: { phase: 'error', message: err.message },
      }))
    }
  }

  return (
    <div>
      <div className="q-header">
        <div>
          <h1 className="view-title">Quarantine</h1>
          <p className="text-dim view-subtitle">
            Files NOVA has set aside are held here until you restore them.
          </p>
        </div>
        <button
          type="button"
          className="q-refresh"
          onClick={fetchQuarantined}
          disabled={status === 'loading'}
          aria-label="Refresh quarantine list"
        >
          ↻ Refresh
        </button>
      </div>

      {banner && <p className="status-message confirm-safe">{banner}</p>}

      {status === 'loading' && (
        <p className="status-message text-dim">Loading quarantined items…</p>
      )}

      {status === 'error' && <p className="status-message status-blocked">{errorMessage}</p>}

      {status === 'loaded' && items.length === 0 && (
        <p className="status-message text-dim">Nothing in quarantine right now.</p>
      )}

      {status === 'loaded' && items.length > 0 && (
        <div className="q-list">
          {items.map((item) => (
            <QuarantineCard
              key={item.quarantine_id}
              item={item}
              actionState={actions[item.quarantine_id]}
              onRestore={handleRestore}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default Quarantine
