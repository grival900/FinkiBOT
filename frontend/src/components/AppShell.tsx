import type { ReactNode } from "react";
import { useRouterState } from "@tanstack/react-router";
import { isGuest, useAuth } from "@/lib/auth";
import { PUBLIC_PATHS } from "@/components/AuthGate";
import { Sidebar } from "@/components/Sidebar";

// The sidebar (nav, chat history, account) has nothing useful to show before the
// visitor has either logged in or picked "Continue as guest" on the login gate (see
// AuthGate.tsx) — showing it on /login itself would just be empty chrome around a
// form. Subscribing to the route here (not just auth state) forces a re-check on
// every navigation, since picking "Continue as guest" only sets a localStorage flag
// and navigates — it doesn't change any auth state on its own.
export function AppShell({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const authorized = user !== null || isGuest();
  const onPublicPath = PUBLIC_PATHS.has(pathname);

  // Auth state is client-only (localStorage), so the server has no way to know
  // whether this visitor is authorized — it always renders the actual page first.
  // Without this, an unauthenticated visitor landing on a protected route would
  // briefly see that page's real content (sidebar included) before AuthGate's
  // redirect effect has a chance to fire. Blocking render until we're sure — either
  // auth has resolved and we're authorized/on a public path, or a redirect is
  // already underway — trades that flash for a brief blank screen instead.
  if (loading || (!authorized && !onPublicPath)) {
    return <div className="h-screen bg-background" />;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      {authorized ? <Sidebar /> : null}
      <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
