import { useEffect, useState } from 'react'
import { callMcpTool, listMcpTools } from '../api'

const SERVER_LABELS = {
  official: 'finki-official — finki.ukim.mk',
  finki_hub: 'finki-hub — finki-hub.com',
}

function McpToolCard({ tool }) {
  const hasLimit = tool.params.some((p) => p.name === 'limit')
  const defaultQuery = tool.params.find((p) => p.name === 'query')?.default ?? ''
  const defaultLimit = tool.params.find((p) => p.name === 'limit')?.default ?? 5

  const [query, setQuery] = useState(defaultQuery)
  const [limit, setLimit] = useState(defaultLimit)
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleRun(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const data = await callMcpTool(tool.server, tool.name, query, limit)
      setResults(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mcp-tool-card">
      <div className="mcp-tool-header">
        <code className="mcp-tool-name">{tool.name}</code>
      </div>
      <p className="mcp-tool-desc">{tool.description}</p>

      <form className="mcp-tool-form" onSubmit={handleRun}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="на пр. Бази на податоци"
        />
        {hasLimit && (
          <label className="num-questions-label">
            limit:
            <input type="number" min={1} max={20} value={limit} onChange={(e) => setLimit(Number(e.target.value))} />
          </label>
        )}
        <button type="submit" disabled={loading || !query.trim()}>
          {loading ? 'Извршувам...' : 'Изврши'}
        </button>
      </form>

      {error && <p className="error">Грешка: {error}</p>}

      {results && (
        <>
          <p className="mcp-result-count">
            {results.length} резултат{results.length === 1 ? '' : 'и'}
          </p>
          <pre className="mcp-result-json">{JSON.stringify(results, null, 2)}</pre>
        </>
      )}
    </div>
  )
}

export default function MCPPage() {
  const [tools, setTools] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    listMcpTools()
      .then(setTools)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const byServer = tools.reduce((acc, t) => {
    ;(acc[t.server] ??= []).push(t)
    return acc
  }, {})

  return (
    <div className="page">
      <h1>MCP алатки</h1>
      <p className="subtitle">
        Ова се истите MCP (Model Context Protocol) алатки што надворешен AI клиент (на пр. Claude Desktop) може да ги
        повика за да пристапи до индексираните податоци на FinkiBOT — тука ги повикуваш директно преку прелистувач,
        врз истата база што ја користат и Разговор и Пребарување, за да видиш точно што AI клиент би добил наместо
        готов текстуален одговор.
      </p>

      {loading && <p className="empty-hint">Вчитувам алатки...</p>}
      {error && <p className="error">Грешка: {error}</p>}

      {Object.entries(byServer).map(([server, serverTools]) => (
        <section key={server} className="mcp-server-section">
          <h2 className="mcp-server-title">{SERVER_LABELS[server] || server}</h2>
          <div className="mcp-tool-grid">
            {serverTools.map((tool) => (
              <McpToolCard key={`${tool.server}-${tool.name}`} tool={tool} />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
