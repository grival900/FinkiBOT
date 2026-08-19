import type { ReactNode } from "react";

export function Page({
  title,
  description,
  children,
  wide,
  beforeHeader,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  wide?: boolean;
  beforeHeader?: ReactNode;
}) {
  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-8" style={wide ? { maxWidth: "80rem" } : undefined}>
      {beforeHeader}
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      </header>
      {children}
    </div>
  );
}

export function Notice({ kind, children }: { kind: "error" | "info"; children: ReactNode }) {
  return (
    <div
      className={
        kind === "error"
          ? "rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          : "rounded-md border border-border bg-muted px-3 py-2 text-sm text-muted-foreground"
      }
    >
      {children}
    </div>
  );
}
