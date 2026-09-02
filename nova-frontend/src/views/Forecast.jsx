import { useState } from 'react'
import './Recommendations.css'
import './Forecast.css'

const API_BASE = 'http://127.0.0.1:8756'

// NOVA doesn't expose a "configured scan root" endpoint, and a forecast is
// about a whole filesystem's capacity, not a single scan directory (see
// Recommendations.jsx for that) - so this defaults to the home directory,
// a reasonable "the disk I care about" starting point for a single-machine
// tool, and where this project's own seeded demo history
// (forecasting.generate_synthetic_history()) lives.
const DEFAULT_PATH = '/root'

function formatBytes(bytes) {
  if (bytes == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`
}

function usageBarClass(percent) {
  if (percent >= 90) return 'usage-bar-fill usage-bar-blocked'
  if (percent >= 70) return 'usage-bar-fill usage-bar-review'
  return 'usage-bar-fill usage-bar-safe'
}

// Every clause here is only ever reached using fields NOVA's own linear
// fit actually produced (trend_bytes_per_day, days_until_full) - nothing
// invented, matching forecasting.py's own "be honest rather than
// extrapolate from nothing" rule.
function forecastSentence(data) {
  if (data.trend_bytes_per_day <= 0) {
    return 'Usage is stable or decreasing — no fill date to project.'
  }
  if (data.days_until_full == null) {
    return 'Usage is trending upward and is already at or beyond its tracked capacity.'
  }
  return `At the current rate, this will be full in approximately ${Math.round(data.days_until_full)} days.`
}

function Forecast() {
  const [path, setPath] = useState(DEFAULT_PATH)
  const [status, setStatus] = useState('idle') // idle | loading | loaded | error
  const [data, setData] = useState(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [validationMessage, setValidationMessage] = useState('')
  const [snapshotState, setSnapshotState] = useState('idle') // idle | pending | done | error
  const [snapshotMessage, setSnapshotMessage] = useState('')

  async function handleCheck(event) {
    event.preventDefault()
    const target = path.trim()
    if (!target) {
      setValidationMessage('Enter a path to check.')
      return
    }
    setValidationMessage('')
    setStatus('loading')
    setErrorMessage('')

    try {
      const res = await fetch(`${API_BASE}/api/forecast?path=${encodeURIComponent(target)}`)
      const json = await res.json()
      if (!res.ok) {
        throw new Error(json.detail || 'NOVA could not check that path.')
      }
      setData(json)
      setStatus('loaded')
    } catch (err) {
      setData(null)
      setStatus('error')
      setErrorMessage(
        err instanceof TypeError
          ? "Couldn't reach the NOVA backend at 127.0.0.1:8756 — is it running?"
          : err.message,
      )
    }
  }

  async function handleSnapshot() {
    const target = path.trim()
    if (!target) {
      setValidationMessage('Enter a path to check.')
      return
    }
    setSnapshotState('pending')
    setSnapshotMessage('')

    try {
      const res = await fetch(`${API_BASE}/api/forecast/snapshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: target }),
      })
      const json = await res.json()
      if (!res.ok) {
        throw new Error(json.detail || 'NOVA could not record a snapshot.')
      }
      setSnapshotState('done')
      setSnapshotMessage(`Snapshot recorded — ${json.used_percent.toFixed(1)}% used.`)
    } catch (err) {
      setSnapshotState('error')
      setSnapshotMessage(
        err instanceof TypeError
          ? "Couldn't reach the NOVA backend at 127.0.0.1:8756 — is it running?"
          : err.message,
      )
    }
  }

  const percent = data?.used_percent ?? null

  return (
    <div>
      <h1 className="view-title">Forecast</h1>
      <p className="text-dim view-subtitle">
        Track disk usage over time and estimate when a path will run out of space.
      </p>

      <form className="scan-form" onSubmit={handleCheck}>
        <input
          type="text"
          className="scan-input mono"
          placeholder={DEFAULT_PATH}
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        <button type="submit" className="btn btn-primary" disabled={status === 'loading'}>
          {status === 'loading' ? 'Checking…' : 'Check'}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={handleSnapshot}
          disabled={snapshotState === 'pending'}
        >
          {snapshotState === 'pending' ? 'Recording…' : 'Record snapshot now'}
        </button>
      </form>
      {validationMessage && <p className="form-hint form-hint-blocked">{validationMessage}</p>}
      {snapshotMessage && (
        <p className={snapshotState === 'error' ? 'form-hint form-hint-blocked' : 'form-hint confirm-safe'}>
          {snapshotMessage}
        </p>
      )}

      {status === 'loading' && (
        <p className="status-message text-dim">Checking {path.trim() || 'that path'}…</p>
      )}

      {status === 'error' && <p className="status-message status-blocked">{errorMessage}</p>}

      {status === 'idle' && (
        <p className="status-message text-dim">Enter a path and check its forecast.</p>
      )}

      {status === 'loaded' && data && (
        <div className="forecast-panel">
          <div className="usage-block">
            <div className="usage-number mono">{percent.toFixed(1)}%</div>
            <div className="usage-bar-track">
              <div
                className={usageBarClass(percent)}
                style={{ width: `${Math.min(percent, 100)}%` }}
              />
            </div>
            <p className="usage-meta text-dim">
              {formatBytes(data.used_bytes)} used of {formatBytes(data.total_bytes)} (
              {formatBytes(data.free_bytes)} free)
            </p>
          </div>

          {data.status === 'ok' && (
            <p className="forecast-sentence">{forecastSentence(data)}</p>
          )}

          {data.status === 'insufficient_data' && (
            <p className="forecast-sentence text-dim">
              Not enough history yet to forecast a trend: {data.snapshots_available} of{' '}
              {data.snapshots_needed} snapshots recorded for this path. Use "Record snapshot
              now" to start building history.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export default Forecast
