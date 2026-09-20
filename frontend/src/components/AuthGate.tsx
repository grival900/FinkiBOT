import { useEffect } from "react";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { isGuest, useAuth } from "@/lib/auth";

// Pages reachable without being logged in or having picked "Continue as guest" —
// otherwise every other route redirects here first. Chat/search/quiz/subscribe
// themselves still work with no account at all, same as always; this only gates the
// very first landing, not per-page access. "/widget" is the bare embedded chat that
// runs inside the WordPress bubble widget's iframe (see routes/widget.tsx) — a first-
// time anonymous site visitor clicking the bubble must never be bounced to a login
// screen. Exported so AppShell can block rendering the protected page's content until
// the redirect below actually lands, instead of briefly flashing it — see
// AppShell.tsx.
export const PUBLIC_PATHS = new Set(["/login", "/register", "/reset-password", "/widget"]);

export function AuthGate() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  useEffect(() => {
    if (loading || user || isGuest() || PUBLIC_PATHS.has(pathname)) return;
    navigate({ to: "/login" });
  }, [loading, user, pathname, navigate]);

  return null;
}