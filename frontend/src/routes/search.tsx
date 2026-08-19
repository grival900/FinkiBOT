import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { apiGet, type SearchResult } from "@/lib/api";
import { Notice, Page } from "@/components/Page";
import { useI18n } from "@/lib/i18n";

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

  // The query itself lives in the URL, not just component state — so it survives a
  // page refresh, and browser back/forward after opening a result restores the exact
  // search instead of wiping it (this effect re-runs whenever those params change,
  // which covers both cases).
  useEffect(() => {
    setQ(urlQ ?? "");
    setSource(urlSource ?? "");
    if (!urlQ) {
      setResults(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ q: urlQ, limit: "10" });
    if (urlSource) params.set("source", urlSource);
    apiGet<SearchResult[]>(`/search?${params.toString()}`)
      .then((r) => {
        if (!cancelled) setResults(r);
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
        {results?.map((r) => {
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
