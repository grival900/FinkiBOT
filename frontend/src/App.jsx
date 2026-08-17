import { NavLink, Route, Routes } from 'react-router-dom'
import ChatPage from './pages/ChatPage'
import SearchPage from './pages/SearchPage'
import QuizPage from './pages/QuizPage'
import SubscribePage from './pages/SubscribePage'
import DocumentDetailPage from './pages/DocumentDetailPage'
import MCPPage from './pages/MCPPage'

const NAV_LINKS = [
  { to: '/', label: 'Разговор', end: true },
  { to: '/search', label: 'Пребарување' },
  { to: '/quiz', label: 'Квиз' },
  { to: '/subscribe', label: 'Известувања' },
  { to: '/mcp', label: 'MCP алатки' },
]

export default function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-title">FinkiBOT</span>
        <nav className="app-nav">
          {NAV_LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end} className={({ isActive }) => (isActive ? 'active' : '')}>
              {link.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="app-main">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/documents/:id" element={<DocumentDetailPage />} />
          <Route path="/mcp" element={<MCPPage />} />
          <Route path="/quiz" element={<QuizPage />} />
          <Route path="/subscribe" element={<SubscribePage />} />
        </Routes>
      </main>
    </div>
  )
}
