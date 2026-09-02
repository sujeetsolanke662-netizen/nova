import { useEffect, useRef, useState } from 'react'
import './Recommendations.css'
import './AskNova.css'

const API_BASE = 'http://127.0.0.1:8756'

// Ask NOVA needs a root to scan (same as Recommendations/Copilot search),
// but the chat interface itself shouldn't be cluttered with a full scan
// form - so it's a small, secondary field above the input, not a second
// prominent control. Defaults to the same directory Recommendations.jsx
// hints at; the backend expands "~" itself (see main.py's
// _validate_scan_root / scanner.py's _resolve), so this works even though
// it isn't pre-expanded here.
const DEFAULT_ROOT = '~/Downloads'

function ChatMessage({ message }) {
  const isUser = message.role === 'user'
  const bubbleClass = [
    'chat-bubble',
    isUser ? 'chat-bubble-user' : 'chat-bubble-nova',
    message.role === 'error' ? 'chat-bubble-error' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={isUser ? 'chat-row chat-row-user' : 'chat-row chat-row-nova'}>
      <div className={bubbleClass}>
        <p className="chat-text">{message.text}</p>

        {message.citedPaths && message.citedPaths.length > 0 && (
          <div className="chat-citations">
            <p className="chat-citations-label">Based on:</p>
            <ul className="chat-citations-list">
              {message.citedPaths.map((path) => (
                <li key={path} className="mono">
                  {path}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

function nextId() {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
}

function AskNova() {
  const [root, setRoot] = useState(DEFAULT_ROOT)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState([])
  const [isThinking, setIsThinking] = useState(false)
  const historyRef = useRef(null)

  useEffect(() => {
    if (historyRef.current) {
      historyRef.current.scrollTop = historyRef.current.scrollHeight
    }
  }, [messages, isThinking])

  async function handleSubmit(event) {
    event.preventDefault()
    const question = input.trim()
    const target = root.trim()
    if (!question || isThinking) return

    setMessages((prev) => [...prev, { id: nextId(), role: 'user', text: question }])
    setInput('')
    setIsThinking(true)

    try {
      const res = await fetch(`${API_BASE}/api/copilot/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, root: target }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || "NOVA couldn't answer that.")
      }
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: 'nova',
          text: data.answer_text,
          citedPaths: data.cited_paths,
        },
      ])
    } catch (err) {
      const text =
        err instanceof TypeError
          ? "I couldn't reach the NOVA backend at 127.0.0.1:8756 — is it running?"
          : `I ran into a problem answering that: ${err.message}`
      setMessages((prev) => [...prev, { id: nextId(), role: 'error', text }])
    } finally {
      setIsThinking(false)
    }
  }

  return (
    <div>
      <h1 className="view-title">Ask NOVA</h1>
      <p className="text-dim view-subtitle">
        Ask a plain-English question about your files — NOVA searches your real scan data to
        answer, it never invents one.
      </p>

      <div className="chat-shell">
        <div className="chat-scan-row">
          <span className="text-dim">Scanning</span>
          <input
            type="text"
            className="chat-root-input mono"
            value={root}
            onChange={(e) => setRoot(e.target.value)}
            aria-label="Root directory to scan"
          />
        </div>

        <div className="chat-history" ref={historyRef}>
          {messages.length === 0 && !isThinking && (
            <p className="chat-empty text-dim">
              Ask NOVA about your storage — try "why is my disk almost full?"
            </p>
          )}

          {messages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))}

          {isThinking && (
            <div className="chat-row chat-row-nova">
              <div className="chat-bubble chat-bubble-nova chat-bubble-thinking text-dim">
                Scanning and searching…
              </div>
            </div>
          )}
        </div>

        <form className="chat-input-row" onSubmit={handleSubmit}>
          <input
            type="text"
            className="chat-input"
            placeholder="Ask a question about your files…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isThinking}
          />
          <button
            type="submit"
            className="btn btn-primary"
            disabled={isThinking || !input.trim()}
          >
            {isThinking ? 'Asking…' : 'Ask'}
          </button>
        </form>
      </div>
    </div>
  )
}

export default AskNova
