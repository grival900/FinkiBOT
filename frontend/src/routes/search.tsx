import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { apiGet, type SearchResult } from "@/lib/api";
import { Notice, Page } from "@/components/Page";
import { useI18n, type TKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const TYPE_LABEL_KEYS: Record<string, TKey> = {
  announcement: "type_announcement",
  course: "type_course",
  professor: "type_professor",
  staff: "type_staff",
  material: "type_material",
  schedule: "type_schedule",
  thesis: "type_thesis",
  page: "type_page",
};

function typeLabel(type: string, t: (k: TKey) => string): string {
  const key = TYPE_LABEL_KEYS[type];
  return key ? t(key) : type;
}

type SearchSearch = { q?: string | undefined; source?: string | undefined };

export const Route = createFileRoute("/search")({
  validateSearch: (search: Record<string, unknown>): SearchSearch => ({
    q: typeof search["q"] === "string" ? search["q"] : undefined,
    source: typeof search["source"] === "string" ? search["source"] : undefined,
  }),
  head: () => ({
    meta: [
      { title: "Пребарување — FinkiBOT" },
      {
        name: "description",
        content:
          "Пребарувај соопштенија, предмети и материјали од finki.ukim.mk и finki-hub.com на едно место.",
      },
      { property: "og:title", content: "Пребарување — FinkiBOT" },
      {
        property: "og:description",
        content: "Семантичко пребарување низ содржината на ФИНКИ и заедницата.",
      },
    ],
  }),
  component: SearchPage,
});

function fmtDate(d: string | null) {
  if (!d) return null;
  const date = new Date(d);
  return Number.isNaN(date.getTime()) ? d : date.toLocaleDateString("mk-MK");
}

function SearchPage() {
  const { t } = useI18n();
  const { q: urlQ, source: urlSource } = Route.useSearch();
  const navigate = Route.useNavigate();
  const [q, setQ] = useState(urlQ ?? "");
  const [source, setSource] = useState(urlSource ?? "");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set());

  function toggleType(type: string) {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }

  // The query itself lives in the URL, not just component state — so it survives a
  // page refresh, and browser back/forward after opening a result restores the exact
  // search instead of wiping it (this effect re-runs whenever those params change,
  // which covers both cases).
  useEffect(() => {
    setQ(urlQ ?? "");
    setSource(urlSource ?? "");
    if (!urlQ) {
      setResults(null);
      setActiveTypes(new Set());
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ q: urlQ, limit: "10" });
    if (urlSource) params.set("source", urlSource);
    apiGet<SearchResult[]>(`/search?${params.toString()}`)
      .then((r) => {
        if (!cancelled) {
          setResults(r);
          setActiveTypes(new Set());
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setResults(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [urlQ, urlSource]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    navigate({ search: { q: q.trim(), source: source || undefined } });
  }

  return (
    <Page title={t("nav_search")}>
      <form onSubmit={submit} className="flex flex-wrap gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("search_placeholder")}
          className="min-w-60 flex-1 rounded-md border border-input bg-card px-3 py-2 text-sm outline-none focus:border-ring"
        />
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="rounded-md border border-input bg-card px-3 py-2 text-sm outline-none focus:border-ring"
        >
          <option value="">{t("all_sources")}</option>
          <option value="official">finki.ukim.mk</option>
          <option value="finki_hub">finki-hub.com</option>
        </select>
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {t("submit_search")}
        </button>
      </form>

      {results && results.length > 0
        ? (() => {
            const typeCounts = new Map<string, number>();
            for (const r of results) typeCounts.set(r.type, (typeCounts.get(r.type) ?? 0) + 1);
            const types = Array.from(typeCounts.keys()).sort();
            if (types.length < 2) return null;
            return (
              <div className="mt-4 flex flex-wrap gap-1.5">
                <span className="self-center pr-1 text-xs text-muted-foreground">
                  {t("filter_by_type")}:
                </span>
                {types.map((type) => (
                  <button
                    key={type}
                    type="button"
                    onClick={() => toggleType(type)}
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-xs transition-colors",
                      activeTypes.has(type)
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border bg-card text-muted-foreground hover:bg-accent",
                    )}
                  >
                    {typeLabel(type, t)} ({typeCounts.get(type)})
                  </button>
                ))}
              </div>
            );
          })()
        : null}

      <div className="mt-6 space-y-3">
        {loading ? <Notice kind="info">{t("loading")}</Notice> : null}
        {error ? (
          <Notice kind="error">
            {t("error")}: {error}
          </Notice>
        ) : null}
        {results && results.length === 0 && !loading ? (
          <Notice kind="info">{t("no_results")}</Notice>
        ) : null}
        {results &&
        activeTypes.size > 0 &&
        results.filter((r) => activeTypes.has(r.type)).length === 0 ? (
          <Notice kind="info">{t("no_results")}</Notice>
        ) : null}
        {results
          ?.filter((r) => activeTypes.size === 0 || activeTypes.has(r.type))
          .map((r) => {
            const internal = r.source === "finki_hub" && r.type === "course";
            const date = fmtDate(r.published_at);
            return (
              <article
                key={`${r.document_id}-${r.chunk_text.slice(0, 12)}`}
                className="rounded-lg border border-border bg-card p-4"
              >
                {internal ? (
                  <Link
                    to="/documents/$id"
                    params={{ id: r.document_id }}
                    className="text-sm font-medium text-primary hover:underline"
                  >
                    {r.title}
                  </Link>
                ) : (
                  <a
                    href={r.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-medium text-primary hover:underline"
                  >
                    {r.title}
                  </a>
                )}
                <p className="mt-1 text-xs text-muted-foreground">
                  {r.source} · {r.type}
                  {date ? ` · ${date}` : ""}
                </p>
                <p className="mt-2 text-sm text-muted-foreground">{r.chunk_text}</p>
              </article>
            );
          })}
      </div>
    </Page>
  );
}
