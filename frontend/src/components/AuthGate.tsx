import { useEffect } from "react";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { isGuest, useAuth } from "@/lib/auth";

// Pages reachable without being logged in or having picked "Continue as guest" —
// otherwise every other route redirects here first. Chat/search/quiz/subscribe
// themselves still work with no account at all, same as always; this only gates the
// very first landing, not per-page access. Exported so AppShell can block rendering
// the protected page's content until the redirect below actually lands, instead of
// briefly flashing it — see AppShell.tsx.
export const PUBLIC_PATHS = new Set(["/login", "/register", "/reset-password"]);

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
