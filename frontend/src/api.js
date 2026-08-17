const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function handleJson(response) {
  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new Error(`${response.status} ${response.statusText}: ${body}`)
  }
  return response.json()
}

export function searchDocuments(query, { source, type, limit = 10 } = {}) {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  if (source) params.set('source', source)
  if (type) params.set('type', type)
  return fetch(`${API_BASE_URL}/search?${params}`).then(handleJson)
}

export function getDocument(id) {
  return fetch(`${API_BASE_URL}/documents/${id}`).then(handleJson)
}

export function listMcpTools() {
  return fetch(`${API_BASE_URL}/mcp/tools`).then(handleJson)
}

export function callMcpTool(server, tool, query, limit) {
  return fetch(`${API_BASE_URL}/mcp/call`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ server, tool, query, limit }),
  }).then(handleJson)
}

export async function streamChat(message, history, onChunk) {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
  })
  if (!response.ok || !response.body) {
    const body = await response.text().catch(() => '')
    throw new Error(`${response.status} ${response.statusText}: ${body}`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    onChunk(decoder.decode(value, { stream: true }))
  }
}

export function subscribe(email, keywords, courseCodes) {
  return fetch(`${API_BASE_URL}/announcements/subscribe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, keywords, course_codes: courseCodes }),
  }).then(handleJson)
}

export function generateQuiz(courseQuery, numQuestions) {
  return fetch(`${API_BASE_URL}/quiz/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_query: courseQuery, num_questions: numQuestions }),
  }).then(handleJson)
}

export function uploadQuiz(file, numQuestions) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('num_questions', String(numQuestions))
  return fetch(`${API_BASE_URL}/quiz/upload`, { method: 'POST', body: formData }).then(handleJson)
}
