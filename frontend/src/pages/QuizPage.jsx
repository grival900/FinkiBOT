import { useState } from 'react'
import { generateQuiz, uploadQuiz } from '../api'

function QuizResults({ quiz }) {
  const [selected, setSelected] = useState({})
  const [checked, setChecked] = useState(false)

  return (
    <div className="quiz-results">
      <p className="quiz-sources">Извори: {quiz.source_titles.join(', ')}</p>
      {quiz.questions.map((q, qi) => (
        <div key={qi} className="quiz-question">
          <p className="quiz-question-text">
            {qi + 1}. {q.question}
          </p>
          <div className="quiz-choices">
            {q.choices.map((choice, ci) => {
              const isSelected = selected[qi] === ci
              const isCorrect = checked && ci === q.correct_index
              const isWrongPick = checked && isSelected && ci !== q.correct_index
              return (
                <button
                  key={ci}
                  type="button"
                  className={`quiz-choice ${isSelected ? 'selected' : ''} ${isCorrect ? 'correct' : ''} ${isWrongPick ? 'wrong' : ''}`}
                  onClick={() => !checked && setSelected((prev) => ({ ...prev, [qi]: ci }))}
                >
                  {choice}
                </button>
              )
            })}
          </div>
          {checked && <p className="quiz-explanation">{q.explanation}</p>}
        </div>
      ))}
      {!checked && (
        <button type="button" className="quiz-check" onClick={() => setChecked(true)}>
          Провери одговори
        </button>
      )}
    </div>
  )
}

export default function QuizPage() {
  const [mode, setMode] = useState('course')
  const [courseQuery, setCourseQuery] = useState('')
  const [numQuestions, setNumQuestions] = useState(5)
  const [file, setFile] = useState(null)
  const [quiz, setQuiz] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setQuiz(null)
    try {
      const data =
        mode === 'course' ? await generateQuiz(courseQuery, numQuestions) : await uploadQuiz(file, numQuestions)
      setQuiz(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <h1>Квиз мејкер</h1>
      <p className="subtitle">
        Генерирај квиз од индексирана содржина за предмет, или прикачи сопствен материјал (PDF/PPTX).
      </p>

      <div className="quiz-mode-toggle">
        <button type="button" className={mode === 'course' ? 'active' : ''} onClick={() => setMode('course')}>
          Од предмет
        </button>
        <button type="button" className={mode === 'upload' ? 'active' : ''} onClick={() => setMode('upload')}>
          Прикачи материјал
        </button>
      </div>

      <form className="quiz-form" onSubmit={handleSubmit}>
        {mode === 'course' ? (
          <input
            type="text"
            value={courseQuery}
            onChange={(e) => setCourseQuery(e.target.value)}
            placeholder="на пр. Алгоритми и податочни структури"
          />
        ) : (
          <input type="file" accept=".pdf,.pptx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        )}
        <label className="num-questions-label">
          Прашања:
          <input
            type="number"
            min={1}
            max={15}
            value={numQuestions}
            onChange={(e) => setNumQuestions(Number(e.target.value))}
          />
        </label>
        <button type="submit" disabled={loading || (mode === 'course' ? !courseQuery.trim() : !file)}>
          {loading ? 'Генерирам...' : 'Генерирај квиз'}
        </button>
      </form>

      {error && <p className="error">Грешка: {error}</p>}
      {quiz && <QuizResults quiz={quiz} />}
    </div>
  )
}
