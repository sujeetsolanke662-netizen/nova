import { useState } from 'react'
import './Recommendations.css'

const API_BASE = 'http://127.0.0.1:8756'

const ACTION_LABELS = {
  auto_apply: { label: 'Auto-apply', className: 'badge-safe' },
  review_recommended: { label: 'Review recommended', className: 'badge-review' },
  keep: { label: 'Keep', className: 'badge-keep' },
}

function ActionBadge({ action }) {
  const cfg = ACTION_LABELS[action] ?? { label: action, className: 'badge-keep' }
  return <span className={`badge ${cfg.className}`}>{cfg.label}</span>
}

// The recommendation payload only carries scored `factors`, not a
// human-readable "reason" - that sentence is built server-side just for
// the audit log entry, never returned here. So the quarantine reason we
// send has to be assembled client-side from the highest-contributing
// factor, per the demo spec ("top factor explanation").
function topFactorExplanation(rec) {
  const factors = rec.factors ?? []
  const contributing = factors.filter((f) => f.contribution > 0)
  const pool = contributing.length ? contributing : factors
  if (!pool.length) return 'Flagged by NOVA.'
  const top = pool.reduce((a, b) => (b.contribution > a.contribution ? b : a))
  return top.explanation
}

function RecommendationCard({ rec, actionState, onQuarantine, onRestore }) {
  const canAct = rec.recommended_action !== 'keep'

  return (
    <div className="rec-card">
      <div className="rec-card-header">
        <span className="rec-path mono">{rec.path}</span>
        <ActionBadge action={rec.recommended_action} />
      </div>

      <ul className="factor-list">
        {rec.factors.map((factor) => (
          <li
            key={factor.name}
            className={factor.contribution > 0 ? 'factor factor-active' : 'factor'}
          >
            {factor.explanation}
          </li>
        ))}
      </ul>

      {rec.duplicate_of && (
        <p className="rec-meta">
          Byte-identical duplicate of <span className="mono">{rec.duplicate_of}</span>
        </p>
      )}
      {rec.near_duplicate_of && rec.near_duplicate_of.length > 0 && (
        <p className="rec-meta">
          Near-duplicate of <span className="mono">{rec.near_duplicate_of.join(', ')}</span>
        </p>
      )}

      {canAct && (
        <div className="rec-actions">
          {(!actionState || actionState.phase === 'idle') && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onQuarantine(rec)}
            >
              Approve &amp; Quarantine
            </button>
          )}

          {actionState?.phase === 'pending' && (
            <span className="text-dim">Quarantining…</span>
          )}

          {actionState?.phase === 'quarantined' && (
            <div className="confirm confirm-safe">
              <span>Quarantined.</span>
              <button
                type="button"
                className="btn btn-link"
                onClick={() => onRestore(rec.path, actionState.quarantineId)}
              >
                Undo
              </button>
            </div>
          )}

          {actionState?.phase === 'restoring' && (
            <span className="text-dim">Restoring…</span>
          )}

          {actionState?.phase === 'restored' && (
            <div className="confirm confirm-review">
              <span>Restored to its original location.</span>
            </div>
          )}

          {actionState?.phase === 'error' && (
            <div className="confirm confirm-blocked">
              <span>{actionState.message}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Recommendations() {
  const [root, setRoot] = useState('')
  const [status, setStatus] = useState('idle') // idle | loading | loaded | error
  const [result, setResult] = useState(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [validationMessage, setValidationMessage] = useState('')
  const [actions, setActions] = useState({})

  async function handleScan(event) {
    event.preventDefault()
    const target = root.trim()
    if (!target) {
      setValidationMessage('Enter a path to scan.')
      return
    }
    setValidationMessage('')
    setStatus('loading')
    setErrorMessage('')
    setActions({})

    try {
      const res = await fetch(
        `${API_BASE}/api/recommendations?root=${encodeURIComponent(target)}`,
      )
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'That scan could not be completed.')
      }
      setResult(data)
      setStatus('loaded')
    } catch (err) {
      setResult(null)
      setStatus('error')
      setErrorMessage(
        err instanceof TypeError
          ? "Couldn't reach the NOVA backend at 127.0.0.1:8756 — is it running?"
          : err.message,
      )
    }
  }

  async function handleQuarantine(rec) {
    setActions((prev) => ({ ...prev, [rec.path]: { phase: 'pending' } }))
    try {
      const res = await fetch(`${API_BASE}/api/quarantine`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: rec.path, reason: topFactorExplanation(rec) }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'NOVA refused to quarantine this file.')
      }
      setActions((prev) => ({
        ...prev,
        [rec.path]: { phase: 'quarantined', quarantineId: data.quarantine_id },
      }))
    } catch (err) {
      setActions((prev) => ({
        ...prev,
        [rec.path]: { phase: 'error', message: err.message },
      }))
    }
  }

  async function handleRestore(path, quarantineId) {
    setActions((prev) => ({ ...prev, [path]: { phase: 'restoring', quarantineId } }))
    try {
      const res = await fetch(`${API_BASE}/api/quarantine/${quarantineId}/restore`, {
        method: 'POST',
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'NOVA could not restore this file.')
      }
      setActions((prev) => ({ ...prev, [path]: { phase: 'restored', quarantineId } }))
    } catch (err) {
      setActions((prev) => ({
        ...prev,
        [path]: { phase: 'error', message: err.message, quarantineId },
      }))
    }
  }

  const recommendations = result?.recommendations ?? []

  return (
    <div>
      <h1 className="view-title">Recommendations</h1>
      <p className="text-dim view-subtitle">
        Scan a directory for stale and duplicate files. Nothing is touched until you
        approve it.
      </p>

      <form className="scan-form" onSubmit={handleScan}>
        <input
          type="text"
          className="scan-input mono"
          placeholder="~/Downloads"
          value={root}
          onChange={(e) => setRoot(e.target.value)}
        />
        <button type="submit" className="btn btn-primary" disabled={status === 'loading'}>
          {status === 'loading' ? 'Scanning…' : 'Scan'}
        </button>
      </form>
      {validationMessage && <p className="form-hint form-hint-blocked">{validationMessage}</p>}

      {status === 'loading' && (
        <p className="status-message text-dim">
          Scanning {root.trim() || 'the target path'} for stale and duplicate files — this
          can take a few seconds on a large directory…
        </p>
      )}

      {status === 'error' && <p className="status-message status-blocked">{errorMessage}</p>}

      {status === 'idle' && (
        <p className="status-message text-dim">No files scanned yet — enter a path and scan.</p>
      )}

      {status === 'loaded' && (
        <>
          <div className="scan-summary mono">
            <span>{result.scanned_count} scanned</span>
            <span className="scan-summary-sep">·</span>
            <span>{result.protected_count} protected</span>
            <span className="scan-summary-sep">·</span>
            <span>{result.skipped_count} skipped</span>
            <span className="scan-summary-sep">·</span>
            <span>{recommendations.length} flagged</span>
          </div>

          {recommendations.length === 0 ? (
            <p className="status-message text-dim">
              NOVA didn't find anything to flag in this path — it looks clean.
            </p>
          ) : (
            <div className="rec-list">
              {recommendations.map((rec) => (
                <RecommendationCard
                  key={rec.path}
                  rec={rec}
                  actionState={actions[rec.path]}
                  onQuarantine={handleQuarantine}
                  onRestore={handleRestore}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default Recommendations
