import { useEffect, useState } from 'react'
import { getInsights } from '../api'

function BarChart({ data, labelKey, valueKey, colorVar = '--accent' }) {
  const max = Math.max(...data.map((d) => d[valueKey]), 1)
  return (
    <div className="bar-chart">
      {data.map((d) => (
        <div className="bar-row" key={d[labelKey]}>
          <span className="bar-label">{d[labelKey]}</span>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{ width: `${(d[valueKey] / max) * 100}%`, background: `var(${colorVar})` }}
            />
          </div>
          <span className="bar-value">{d[valueKey]}</span>
        </div>
      ))}
    </div>
  )
}

export default function InsightsPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getInsights()
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="empty-hint">Вчитувам...</p>
  if (error) return <p className="error">Грешка: {error}</p>
  if (!data) return null

  const byType = data.documents_by_type.map((d) => ({
    label: `${d.source} / ${d.type}`,
    count: d.count,
  }))

  return (
    <div className="page">
      <h1>FINKI Insights</h1>
      <p className="subtitle">
        Статистика над она што веќе е индексирано — без ново скрепување, без LLM повици.
      </p>

      <section className="insights-section">
        <h2>Документи по извор и тип</h2>
        <BarChart data={byType} labelKey="label" valueKey="count" />
      </section>

      <section className="insights-section">
        <h2>Соопштенија по месец</h2>
        <BarChart data={data.announcements_by_month} labelKey="month" valueKey="count" colorVar="--success" />
      </section>

      <section className="insights-section">
        <h2>Најчести тагови на предмети</h2>
        <BarChart data={data.course_tags} labelKey="tag" valueKey="count" />
      </section>

      <section className="insights-section">
        <h2>Предмети по семестар</h2>
        <BarChart
          data={data.course_semester_distribution}
          labelKey="semester"
          valueKey="count"
          colorVar="--success"
        />
      </section>
    </div>
  )
}
