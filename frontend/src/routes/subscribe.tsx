import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { X } from "lucide-react";
import { apiPost } from "@/lib/api";
import { Notice, Page } from "@/components/Page";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/subscribe")({
  head: () => ({
    meta: [
      { title: "Известувања за соопштенија — FinkiBOT" },
      {
        name: "description",
        content:
          "Претплати се на е-пошта и добивај нови соопштенија од ФИНКИ по клучни зборови и кодови на предмети.",
      },
      { property: "og:title", content: "Известувања за соопштенија — FinkiBOT" },
      {
        property: "og:description",
        content: "Персонализирани е-известувања за нови соопштенија на ФИНКИ.",
      },
    ],
  }),
  component: SubscribePage,
});

function TokenInput({
  label,
  values,
  onChange,
  addLabel,
}: {
  label: string;
  values: string[];
  onChange: (v: string[]) => void;
  addLabel: string;
}) {
  const [draft, setDraft] = useState("");
  function add() {
    const v = draft.trim();
    if (!v || values.includes(v)) return;
    onChange([...values, v]);
    setDraft("");
  }
  return (
    <div>
      <span className="mb-1 block text-xs text-muted-foreground">{label}</span>
      <div className="flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          className="flex-1 rounded-md border border-input bg-card px-3 py-2 text-sm outline-none focus:border-ring"
        />
        <button type="button" onClick={add} className="rounded-md border border-border px-3 text-sm">
          {addLabel}
        </button>
      </div>
      {values.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {values.map((v) => (
            <span
              key={v}
              className="inline-flex items-center gap-1 rounded-full border border-border bg-accent px-2.5 py-0.5 text-xs text-accent-foreground"
            >
              {v}
              <button type="button" onClick={() => onChange(values.filter((x) => x !== v))}>
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function SubscribePage() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [codes, setCodes] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setDone(false);
    try {
      await apiPost("/announcements/subscribe", {
        email,
        keywords,
        course_codes: codes,
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Page title={t("nav_subscribe")}>
      <form onSubmit={submit} className="max-w-xl space-y-4">
        <label className="block">
          <span className="mb-1 block text-xs text-muted-foreground">{t("email")}</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-md border border-input bg-card px-3 py-2 text-sm outline-none focus:border-ring"
          />
        </label>
        <TokenInput
          label={t("keywords")}
          values={keywords}
          onChange={setKeywords}
          addLabel={t("add")}
        />
        <TokenInput
          label={t("course_codes")}
          values={codes}
          onChange={setCodes}
          addLabel={t("add")}
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {t("subscribe")}
        </button>

        {loading ? <Notice kind="info">{t("loading")}</Notice> : null}
        {error ? (
          <Notice kind="error">
            {t("error")}: {error}
          </Notice>
        ) : null}
        {done ? <Notice kind="info">{t("subscribe_ok")}</Notice> : null}
      </form>
    </Page>
  );
}
