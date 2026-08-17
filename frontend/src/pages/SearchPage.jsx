import { useState } from 'react'
import { searchDocuments } from '../api'

const SOURCES = [
  { value: '', label: 'Сите извори' },
  { value: 'official', label: 'finki.ukim.mk' },
  { value: 'finki_hub', label: 'finki-hub.com' },
]

export default function SearchPage() {
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [searched, setSearched] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const data = await searchDocuments(query, { source: source || undefined, limit: 15 })
      setResults(data)
      setSearched(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <h1>Пребарување</h1>
      <p className="subtitle">Пребарувај соопштенија, предмети и друга индексирана содржина.</p>

      <form className="search-form" onSubmit={handleSubmit}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="на пр. Бази на податоци"
        />
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          {SOURCES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <button type="submit" disabled={loading || !query.trim()}>
          {loading ? 'Пребарувам...' : 'Пребарај'}
        </button>
      </form>

      {error && <p className="error">Грешка: {error}</p>}

      {searched && !loading && results.length === 0 && !error && <p className="empty-hint">Нема резултати.</p>}

      <ul className="result-list">
        {results.map((r) => (
          <li key={`${r.document_id}-${r.chunk_text.slice(0, 20)}`} className="result-item">
            <a href={r.url} target="_blank" rel="noreferrer">
              {r.title}
            </a>
            <div className="result-meta">
              {r.source} · {r.type}
              {r.published_at ? ` · ${new Date(r.published_at).toLocaleDateString('mk-MK')}` : ''}
            </div>
            <p className="result-excerpt">{r.chunk_text}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}
