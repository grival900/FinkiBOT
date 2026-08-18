import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getDocument } from '../api'

function AccreditationCard({ accreditation }) {
  return (
    <div className="accreditation-card">
      <h3>Акредитација {accreditation.year}</h3>
      <dl className="accreditation-fields">
        {accreditation.Код && (
          <>
            <dt>Код</dt>
            <dd>{accreditation.Код}</dd>
          </>
        )}
        {accreditation.Ниво && (
          <>
            <dt>Ниво</dt>
            <dd>{accreditation.Ниво}</dd>
          </>
        )}
        {accreditation.Семестар && (
          <>
            <dt>Семестар</dt>
            <dd>{accreditation.Семестар}</dd>
          </>
        )}
        {accreditation.Канал && (
          <>
            <dt>Канал</dt>
            <dd>{accreditation.Канал}</dd>
          </>
        )}
        {accreditation.Предуслов && (
          <>
            <dt>Предуслов</dt>
            <dd>
              {accreditation.prerequisite_links?.length > 0
                ? accreditation.prerequisite_links.map((p, i) => (
                    <span key={`${p.text}-${i}`}>
                      {i > 0 && ' / '}
                      {p.document_id ? <Link to={`/documents/${p.document_id}`}>{p.text}</Link> : p.text}
                    </span>
                  ))
                : accreditation.Предуслов}
            </dd>
          </>
        )}
      </dl>
    </div>
  )
}

export default function DocumentDetailPage() {
  const { id } = useParams()
  const [doc, setDoc] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getDocument(id)
      .then(setDoc)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return <p className="empty-hint">Вчитувам...</p>
  if (error) return <p className="error">Грешка: {error}</p>
  if (!doc) return null

  const meta = doc.doc_metadata || {}
  const accreditations = meta.accreditations || []

  return (
    <div className="page">
      <Link to="/search" className="back-link">
        ← Назад на пребарување
      </Link>
      <h1>{doc.title}</h1>

      {(meta.professors?.length > 0 || meta.assistants?.length > 0 || meta.tags?.length > 0) && (
        <div className="doc-chips">
          {meta.professors?.map((p) => (
            <span key={`prof-${p}`} className="chip chip-professor">
              {p}
            </span>
          ))}
          {meta.assistants?.map((a) => (
            <span key={`asst-${a}`} className="chip chip-assistant">
              {a}
            </span>
          ))}
          {meta.tags?.map((t) => (
            <span key={`tag-${t}`} className="chip">
              {t}
            </span>
          ))}
        </div>
      )}

      {accreditations.length > 0 ? (
        <div className="accreditation-grid">
          {accreditations.map((a) => (
            <AccreditationCard key={a.year} accreditation={a} />
          ))}
        </div>
      ) : (
        <p className="result-excerpt">{doc.content}</p>
      )}

      {meta.official_subject_url && (
        <p className="doc-source-link">
          Извор:{' '}
          <a href={meta.official_subject_url} target="_blank" rel="noreferrer">
            {meta.official_subject_url}
          </a>
        </p>
      )}
    </div>
  )
}
