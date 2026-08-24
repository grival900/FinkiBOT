export const API_BASE_URL: string =
  (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "http://localhost:8000";

export function apiUrl(path: string): string {
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
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
  return (await res.json()) as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  return handle<T>(await fetch(apiUrl(path)));
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return handle<T>(
    await fetch(apiUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  return handle<T>(await fetch(apiUrl(path), { method: "POST", body: form }));
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

/* ---------- streaming chat ---------- */

export async function streamChat(
  message: string,
  history: ChatMessage[],
  onChunk: (text: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(apiUrl("/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
