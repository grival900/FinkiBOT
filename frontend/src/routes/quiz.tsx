import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { apiPost, apiPostForm, type QuizResponse } from "@/lib/api";
import { Notice, Page } from "@/components/Page";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/quiz")({
  head: () => ({
    meta: [
      { title: "Квиз генератор — FinkiBOT" },
      {
        name: "description",
        content:
          "Генерирај квиз со прашања од предмет на ФИНКИ или од сопствен PDF/PPTX материјал.",
      },
      { property: "og:title", content: "Квиз генератор — FinkiBOT" },
      {
        property: "og:description",
        content: "Автоматски квизови за подготовка на испити на ФИНКИ.",
      },
    ],
  }),
  component: QuizPage,
});

function QuizPage() {
  const { t } = useI18n();
  const [mode, setMode] = useState<"course" | "upload">("course");
  const [courseQuery, setCourseQuery] = useState("");
  const [num, setNum] = useState(5);
  const [file, setFile] = useState<File | null>(null);
  const [quiz, setQuiz] = useState<QuizResponse | null>(null);
  const [picks, setPicks] = useState<Record<number, number>>({});
  const [checked, setChecked] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setQuiz(null);
    setPicks({});
    setChecked(false);
    try {
      if (mode === "course") {
        setQuiz(
          await apiPost<QuizResponse>("/quiz/generate", {
            course_query: courseQuery,
            num_questions: num,
          }),
        );
      } else {
        if (!file) throw new Error("PDF / PPTX");
        const fd = new FormData();
        fd.append("file", file);
        fd.append("num_questions", String(num));
        setQuiz(await apiPostForm<QuizResponse>("/quiz/upload", fd));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Page title={t("nav_quiz")}>
      <div className="mb-4 inline-flex rounded-md border border-border p-0.5">
        {(["course", "upload"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={cn(
              "rounded px-3 py-1.5 text-sm transition-colors",
              mode === m ? "bg-primary/12 text-primary" : "text-muted-foreground hover:bg-accent",
            )}
          >
            {m === "course" ? t("quiz_from_course") : t("quiz_upload")}
          </button>
        ))}
      </div>

      <form onSubmit={generate} className="flex flex-wrap items-end gap-2">
        {mode === "course" ? (
          <label className="min-w-60 flex-1">
            <span className="mb-1 block text-xs text-muted-foreground">{t("course_query")}</span>
            <input
              value={courseQuery}
              onChange={(e) => setCourseQuery(e.target.value)}
              required
              className="w-full rounded-md border border-input bg-card px-3 py-2 text-sm outline-none focus:border-ring"
            />
          </label>
        ) : (
          <label className="min-w-60 flex-1">
            <span className="mb-1 block text-xs text-muted-foreground">PDF / PPTX</span>
            <input
              type="file"
              accept=".pdf,.pptx"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              required
              className="w-full rounded-md border border-input bg-card px-3 py-1.5 text-sm"
            />
          </label>
        )}
        <label className="w-40">
          <span className="mb-1 block text-xs text-muted-foreground">{t("num_questions")}</span>
          <input
            type="number"
            min={1}
            max={20}
            value={num}
            onChange={(e) => setNum(Number(e.target.value))}
            className="w-full rounded-md border border-input bg-card px-3 py-2 text-sm outline-none focus:border-ring"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {t("generate")}
        </button>
      </form>

      <div className="mt-6 space-y-4">
        {loading ? <Notice kind="info">{t("loading")}</Notice> : null}
        {error ? (
          <Notice kind="error">
            {t("error")}: {error}
          </Notice>
        ) : null}

        {quiz ? (
          <>
            {quiz.source_titles.length > 0 ? (
              <p className="text-xs text-muted-foreground">
                {t("sources_label")}: {quiz.source_titles.join(", ")}
              </p>
            ) : null}

            {quiz.questions.map((q, qi) => (
              <div key={qi} className="rounded-lg border border-border bg-card p-4">
                <p className="mb-3 text-sm font-medium">
                  {qi + 1}. {q.question}
                </p>
                <div className="space-y-1.5">
                  {q.choices.map((choice, ci) => {
                    const picked = picks[qi] === ci;
                    const correct = checked && ci === q.correct_index;
                    const wrong = checked && picked && ci !== q.correct_index;
                    return (
                      <button
                        key={ci}
                        onClick={() => !checked && setPicks({ ...picks, [qi]: ci })}
                        className={cn(
                          "block w-full rounded-md border px-3 py-2 text-left text-sm transition-colors",
                          correct
                            ? "border-success bg-success/10 text-success"
                            : wrong
                              ? "border-destructive bg-destructive/10 text-destructive"
                              : picked
                                ? "border-primary bg-primary/10 text-primary"
                                : "border-border hover:bg-accent",
                        )}
                      >
                        {choice}
                      </button>
                    );
                  })}
                </div>
                {checked ? (
                  <p className="mt-3 text-xs text-muted-foreground">{q.explanation}</p>
                ) : null}
              </div>
            ))}

            {quiz.questions.length > 0 ? (
              <div className="flex gap-2">
                <button
                  onClick={() => setChecked(true)}
                  disabled={checked}
                  className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
                >
                  {t("check_answers")}
                </button>
                <button
                  onClick={() => {
                    setChecked(false);
                    setPicks({});
                  }}
                  className="rounded-md border border-border px-4 py-2 text-sm"
                >
                  {t("reset")}
                </button>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </Page>
  );
}
