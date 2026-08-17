import { useState } from 'react'
import { subscribe } from '../api'

export default function SubscribePage() {
  const [email, setEmail] = useState('')
  const [keywords, setKeywords] = useState('')
  const [courseCodes, setCourseCodes] = useState('')
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  function splitList(value) {
    return value
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setStatus(null)
    try {
      await subscribe(email, splitList(keywords), splitList(courseCodes))
      setStatus('Проверете ја е-поштата за да ја потврдите претплатата.')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <h1>Известувања за нови соопштенија</h1>
      <p className="subtitle">
        Добивај е-пошта кога ќе се објави ново соопштение што одговара на твоите клучни зборови (на пр. „испитна
        сесија“). Остави ги полињата празни за да добиваш сè.
      </p>

      <form className="subscribe-form" onSubmit={handleSubmit}>
        <label>
          Е-пошта
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Клучни зборови (одделени со запирка)
          <input
            type="text"
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            placeholder="испитна сесија, запишување"
          />
        </label>
        <label>
          Шифри на предмети (одделени со запирка)
          <input type="text" value={courseCodes} onChange={(e) => setCourseCodes(e.target.value)} placeholder="F23L3S139" />
        </label>
        <button type="submit" disabled={loading || !email.trim()}>
          {loading ? 'Се претплаќам...' : 'Претплати се'}
        </button>
      </form>

      {status && <p className="success">{status}</p>}
      {error && <p className="error">Грешка: {error}</p>}
    </div>
  )
}
