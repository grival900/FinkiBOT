import { useState } from 'react'
import { streamChat } from '../api'

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    const question = input.trim()
    if (!question || sending) return

    const history = messages.map(({ role, content }) => ({ role, content }))
    setMessages((prev) => [...prev, { role: 'user', content: question }, { role: 'assistant', content: '' }])
    setInput('')
    setSending(true)
    setError(null)

    try {
      await streamChat(question, history, (chunk) => {
        setMessages((prev) => {
          const next = [...prev]
          next[next.length - 1] = { role: 'assistant', content: next[next.length - 1].content + chunk }
          return next
        })
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="page chat-page">
      <h1>Прашај го FinkiBOT</h1>
      <p className="subtitle">Одговорите се засновани на соопштенија и предмети од finki.ukim.mk и finki-hub.com.</p>

      <div className="chat-log">
        {messages.length === 0 && <p className="empty-hint">Постави прашање, на пр. „Кога е јунска испитна сесија?“</p>}
        {messages.map((m, i) => (
          <div key={i} className={`chat-bubble ${m.role}`}>
            <div className="chat-role">{m.role === 'user' ? 'Ти' : 'FinkiBOT'}</div>
            <div className="chat-content">{m.content || (sending && i === messages.length - 1 ? '…' : '')}</div>
          </div>
        ))}
      </div>

      {error && <p className="error">Грешка: {error}</p>}

      <form className="chat-form" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Твоето прашање..."
          disabled={sending}
        />
        <button type="submit" disabled={sending || !input.trim()}>
          Испрати
        </button>
      </form>
    </div>
  )
}
