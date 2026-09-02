import { useState } from 'react'
import './App.css'
import Recommendations from './views/Recommendations.jsx'
import Quarantine from './views/Quarantine.jsx'
import AuditLog from './views/AuditLog.jsx'
import Forecast from './views/Forecast.jsx'
import AskNova from './views/AskNova.jsx'

const NAV_ITEMS = [
  { id: 'recommendations', label: 'Recommendations' },
  { id: 'quarantine', label: 'Quarantine' },
  { id: 'audit-log', label: 'Audit Log' },
  { id: 'forecast', label: 'Forecast' },
  { id: 'ask-nova', label: 'Ask NOVA' },
]

function App() {
  const [activeView, setActiveView] = useState('recommendations')

  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="sidebar-brand">NOVA</div>
        <ul className="nav-list">
          {NAV_ITEMS.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className={
                  activeView === item.id ? 'nav-item nav-item-active' : 'nav-item'
                }
                onClick={() => setActiveView(item.id)}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <main className="main">
        <div className="main-inner">
          {activeView === 'recommendations' && <Recommendations />}
          {activeView === 'quarantine' && <Quarantine />}
          {activeView === 'audit-log' && <AuditLog />}
          {activeView === 'forecast' && <Forecast />}
          {activeView === 'ask-nova' && <AskNova />}
        </div>
      </main>
    </div>
  )
}

export default App
