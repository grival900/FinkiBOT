export const API_BASE_URL: string =
  (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "http://localhost:8000";

export function apiUrl(path: string): string {
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
}

// Set by AuthProvider on login/logout/hydration. A plain module-level variable rather
// than React context, since this file is a plain fetch wrapper, not a component — every
// apiGet/apiPost/etc. call reads whatever token is current at call time.
let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

function authHeaders(): Record<string, string> {
  return authToken ? { Authorization: `Bearer ${authToken}` } : {};
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.text();
      if (body) detail += ` — ${body.slice(0, 300)}`;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return handle<T>(
    await fetch(apiUrl(path), { ...init, headers: { ...authHeaders(), ...(init?.headers ?? {}) } }),
  );
}

export async function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export async function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  return request<T>(path, { method: "POST", body: form });
}

/* ---------- types ---------- */

export type ChatMessage = { role: "user" | "assistant"; content: string };

export type SearchResult = {
  document_id: string;
  title: string;
  url: string;
  source: "official" | "finki_hub" | string;
  type: string;
  published_at: string | null;
  chunk_text: string;
  score: number;
};

export type CourseCodeOption = { code: string; name: string };

export type PrerequisiteLink = { text: string; document_id: string | null };

export type Accreditation = {
  year?: string;
  official_url?: string;
  prerequisite_links?: PrerequisiteLink[];
  programs?: Record<string, string>;
  [key: string]: unknown;
};

export type DocMetadata = {
  accreditation_years?: string[];
  tags?: string[];
  professors?: string[];
  assistants?: string[];
  official_subject_url?: string;
  accreditations?: Accreditation[];
  [key: string]: unknown;
};

export type DocumentDetail = {
  id: string;
  source: string;
  type: string;
  title: string;
  url: string;
  published_at: string | null;
  content: string;
  doc_metadata: DocMetadata | null;
};

export type QuizQuestion = {
  question: string;
  choices: string[];
  correct_index: number;
  explanation: string;
};

export type QuizResponse = { questions: QuizQuestion[]; source_titles: string[] };

export type Insights = {
  documents_by_type: { source: string; type: string; count: number }[];
  announcements_by_month: { month: string; count: number }[];
  course_tags: { tag: string; count: number }[];
  course_semester_distribution: { semester: string; count: number }[];
};

export type McpParam = {
  name: string;
  type: string;
  required: boolean;
  default: unknown;
};

export type McpTool = {
  server: string;
  name: string;
  description: string;
  params: McpParam[];
};

export type AuthUser = {
  id: string;
  email: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
};

export type TokenResponse = { access_token: string; token_type: string; user: AuthUser };

export type ScraperEnabled = { name: string; enabled: boolean };

export type SiteSettings = {
  scrape_announcement_limit: number | null;
  scrape_subjects_limit: number | null;
  scrape_request_delay_seconds: number;
  enable_scheduler: boolean;
  scheduler_interval_minutes: number;
  scheduler_slow_interval_minutes: number;
  scrapers: ScraperEnabled[];
};

/* ---------- streaming chat ---------- */

export async function streamChat(
  message: string,
  history: ChatMessage[],
  onChunk: (text: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(apiUrl("/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ message, history }),
    signal: signal ?? null,
  });
  if (!res.ok || !res.body) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}
