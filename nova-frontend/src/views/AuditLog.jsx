import { useCallback, useEffect, useState } from 'react'
import './Recommendations.css'
import './AuditLog.css'

const API_BASE = 'http://127.0.0.1:8756'

// action_type values written by backend/app/audit_log.py's call sites
// (guardrails.py, recommendation.py, quarantine.py) - see there for the
// full vocabulary. Reuses the same badge language as recommended_action
// badges in Recommendations.jsx (badge-safe/badge-review/badge-keep) plus
// one new variant, badge-blocked, for the one action_type that's a real
// refusal rather than a recommendation or a completed action.
const ACTION_TYPE_LABELS = {
  auto_apply: { label: 'Auto-apply', className: 'badge-safe' },
  quarantine: { label: 'Quarantine', className: 'badge-safe' },
  recommend: { label: 'Recommend', className: 'badge-review' },
  restore: { label: 'Restore', className: 'badge-keep' },
  guardrail_block: { label: 'Guardrail block', className: 'badge-blocked' },
}

function ActionTypeBadge({ actionType }) {
  const cfg = ACTION_TYPE_LABELS[actionType] ?? { label: actionType, className: 'badge-keep' }
  return <span className={`badge ${cfg.className}`}>{cfg.label}</span>
}

function formatTimestamp(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function VerifyBanner({ verify, reverifying, reverifyError, onReverify }) {
  const isValid = verify.valid

  return (
    <div className={isValid ? 'verify-banner verify-banner-safe' : 'verify-banner verify-banner-blocked'}>
      <div className="verify-banner-main">
        <div className="verify-banner-text">
          <span className="verify-banner-icon" aria-hidden="true">
            {isValid ? '✓' : '✕'}
          </span>
          <span>
            {isValid
              ? 'Chain verified — no tampering detected.'
              : `Chain broken — tampering detected at entry #${verify.broken_at_entry}.`}
          </span>
        </div>
        <button
          type="button"
          className="audit-reverify"
          onClick={onReverify}
          disabled={reverifying}
        >
          {reverifying ? 'Verifying…' : '↻ Re-verify'}
        </button>
      </div>
      {reverifyError && <p className="verify-banner-error">{reverifyError}</p>}
    </div>
  )
}

function AuditLogEntry({ entry }) {
  return (
    <div className="audit-card">
      <div className="audit-card-header">
        <span className="audit-entry-id mono">#{entry.entry_id}</span>
        <ActionTypeBadge actionType={entry.action_type} />
        <span className="audit-timestamp text-dim">{formatTimestamp(entry.timestamp)}</span>
      </div>

      <p className="audit-reason">{entry.reason}</p>

      {entry.target_paths && entry.target_paths.length > 0 && (
        <ul className="audit-paths">
          {entry.target_paths.map((path) => (
            <li key={path} className="mono">
              {path}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function AuditLog() {
  const [status, setStatus] = useState('loading') // loading | loaded | error
  const [entries, setEntries] = useState([])
  const [verify, setVerify] = useState(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [reverifying, setReverifying] = useState(false)
  const [reverifyError, setReverifyError] = useState('')

  const loadAll = useCallback(async () => {
    setStatus('loading')
    setErrorMessage('')
    setReverifyError('')
    try {
      const [logRes, verifyRes] = await Promise.all([
        fetch(`${API_BASE}/api/audit-log`),
        fetch(`${API_BASE}/api/audit-log/verify`),
      ])
      const logData = await logRes.json()
      const verifyData = await verifyRes.json()
      if (!logRes.ok) throw new Error(logData.detail || 'NOVA could not load the audit log.')
      if (!verifyRes.ok) {
        throw new Error(verifyData.detail || 'NOVA could not verify the audit log.')
      }

      setEntries(logData)
      setVerify(verifyData)
      setStatus('loaded')
    } catch (err) {
      setEntries([])
      setVerify(null)
      setStatus('error')
      setErrorMessage(
        err instanceof TypeError
          ? "Couldn't reach the NOVA backend at 127.0.0.1:8756 — is it running?"
          : err.message,
      )
    }
  }, [])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  async function handleReverify() {
    setReverifying(true)
    setReverifyError('')
    try {
      const res = await fetch(`${API_BASE}/api/audit-log/verify`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'NOVA could not verify the audit log.')
      setVerify(data)
    } catch (err) {
      setReverifyError(
        err instanceof TypeError
          ? "Couldn't reach the NOVA backend at 127.0.0.1:8756 — is it running?"
          : err.message,
      )
    } finally {
      setReverifying(false)
    }
  }

  // Newest first - the manifest/log itself is append-only in entry_id
  // order, but a human reading it wants the most recent action on top.
  const sortedEntries = [...entries].sort((a, b) => b.entry_id - a.entry_id)

  return (
    <div>
      <h1 className="view-title">Audit Log</h1>
      <p className="text-dim view-subtitle">
        A tamper-evident, append-only record of every action NOVA has taken or recommended.
      </p>

      {status === 'loaded' && verify && (
        <VerifyBanner
          verify={verify}
          reverifying={reverifying}
          reverifyError={reverifyError}
          onReverify={handleReverify}
        />
      )}

      {status === 'loading' && <p className="status-message text-dim">Loading the audit log…</p>}

      {status === 'error' && <p className="status-message status-blocked">{errorMessage}</p>}

      {status === 'loaded' && sortedEntries.length === 0 && (
        <p className="status-message text-dim">No actions have been recorded yet.</p>
      )}

      {status === 'loaded' && sortedEntries.length > 0 && (
        <div className="audit-list">
          {sortedEntries.map((entry) => (
            <AuditLogEntry key={entry.entry_id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  )
}

export default AuditLog
