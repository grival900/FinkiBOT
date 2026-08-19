import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  MessageSquare,
  Search,
  ListChecks,
  Bell,
  BarChart3,
  Wrench,
  Sun,
  Moon,
  Monitor,
  Plus,
  User,
} from "lucide-react";
import { useI18n, type TKey } from "@/lib/i18n";
import { useTheme, type ThemeMode } from "@/lib/theme";
import { loadConversations, type Conversation } from "@/lib/chat-history";
import { cn } from "@/lib/utils";

const NAV: { to: string; key: TKey; icon: typeof Search }[] = [
  { to: "/", key: "nav_chat", icon: MessageSquare },
  { to: "/search", key: "nav_search", icon: Search },
  { to: "/quiz", key: "nav_quiz", icon: ListChecks },
  { to: "/subscribe", key: "nav_subscribe", icon: Bell },
  { to: "/insights", key: "nav_insights", icon: BarChart3 },
  { to: "/mcp", key: "nav_mcp", icon: Wrench },
];

const THEMES: { mode: ThemeMode; key: TKey; icon: typeof Sun }[] = [
  { mode: "light", key: "light", icon: Sun },
  { mode: "dark", key: "dark", icon: Moon },
  { mode: "system", key: "system", icon: Monitor },
];

export function Sidebar() {
  const { t, lang, setLang } = useI18n();
  const { mode, setMode } = useTheme();
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const [conversations, setConversations] = useState<Conversation[]>([]);

  useEffect(() => {
    const sync = () => setConversations(loadConversations());
    sync();
    window.addEventListener("finkibot-conversations", sync);
    return () => window.removeEventListener("finkibot-conversations", sync);
  }, []);

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-border bg-sidebar text-sidebar-foreground">
      <div className="border-b border-border px-4 py-4">
        <Link to="/" className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-md bg-primary text-sm font-bold text-primary-foreground">
            FB
          </span>
          <span>
            <span className="block text-sm font-semibold">{t("brand")}</span>
            <span className="block text-xs text-muted-foreground">{t("tagline")}</span>
          </span>
        </Link>
      </div>

      <nav className="flex flex-col gap-0.5 p-2">
        {NAV.map(({ to, key, icon: Icon }) => {
          const active = to === "/" ? pathname === "/" : pathname.startsWith(to);
          return (
            <Link
              key={to}
              to={to}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary/12 font-medium text-primary"
                  : "text-sidebar-foreground hover:bg-sidebar-accent",
              )}
            >
              <Icon className="size-4" />
              {t(key)}
            </Link>
          );
        })}
      </nav>

      <div className="flex min-h-0 flex-1 flex-col border-t border-border p-2">
        <div className="flex items-center justify-between px-2 py-1.5">
          <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {t("history")}
          </span>
          <button
            type="button"
            onClick={() => navigate({ to: "/", search: { new: Date.now() } })}
            className="rounded-md p-1 text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
            aria-label={t("new_chat")}
          >
            <Plus className="size-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {conversations.length === 0 ? (
            <p className="px-2 py-1 text-xs text-muted-foreground">{t("no_history")}</p>
          ) : (
            conversations.map((c) => (
              <Link
                key={c.id}
                to="/"
                search={{ c: c.id }}
                className="block truncate rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-sidebar-accent hover:text-foreground"
              >
                {c.title}
              </Link>
            ))
          )}
        </div>
      </div>

      <div className="space-y-3 border-t border-border p-3">
        <div className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-full bg-secondary text-secondary-foreground">
            <User className="size-4" />
          </span>
          <span className="leading-tight">
            <span className="block text-sm font-medium">{t("guest")}</span>
            <span className="block text-xs text-muted-foreground">{t("no_login")}</span>
          </span>
        </div>

        <div>
          <span className="mb-1 block text-xs text-muted-foreground">{t("theme")}</span>
          <div className="flex gap-1 rounded-md border border-border p-0.5">
            {THEMES.map(({ mode: m, key, icon: Icon }) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={cn(
                  "flex flex-1 items-center justify-center gap-1 rounded px-1.5 py-1 text-xs transition-colors",
                  mode === m
                    ? "bg-primary/12 text-primary"
                    : "text-muted-foreground hover:bg-sidebar-accent",
                )}
              >
                <Icon className="size-3.5" />
                {t(key)}
              </button>
            ))}
          </div>
        </div>

        <div>
          <span className="mb-1 block text-xs text-muted-foreground">{t("language")}</span>
          <div className="flex gap-1 rounded-md border border-border p-0.5">
            {(["mk", "en"] as const).map((l) => (
              <button
                key={l}
                onClick={() => setLang(l)}
                className={cn(
                  "flex-1 rounded px-2 py-1 text-xs uppercase transition-colors",
                  lang === l
                    ? "bg-primary/12 text-primary"
                    : "text-muted-foreground hover:bg-sidebar-accent",
                )}
              >
                {l === "mk" ? "МК" : "EN"}
              </button>
            ))}
          </div>
        </div>
      </div>
    </aside>
  );
}
