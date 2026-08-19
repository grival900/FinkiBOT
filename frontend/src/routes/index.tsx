import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { streamChat, type ChatMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Notice } from "@/components/Page";
import {
  loadConversations,
  newId,
  saveConversations,
  type Conversation,
} from "@/lib/chat-history";

// Chat answers cite sources in three shapes Gemini isn't consistent about:
// markdown links ([text](url)), bare URLs, and — apparently — a bare URL wrapped in
// just brackets with no parens ([url]). All three are handled, rendering everything
// else as plain text. Every URL alternative excludes "]" so a stray closing bracket
// from the third shape can never get swallowed into a bare-URL match and corrupt it
// (this actually happened: a real page 404'd because its href ended in "%5D").
const LINK_PATTERN =
  /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\[(https?:\/\/[^\s\]]+)\]|https?:\/\/[^\s\])]+/g;

function linkifyMessage(content: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  let match: RegExpExecArray | null;

  const link = (href: string, text: string) => (
    <a
      key={key++}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary underline underline-offset-2 hover:opacity-80"
    >
      {text}
    </a>
  );

  LINK_PATTERN.lastIndex = 0;
  while ((match = LINK_PATTERN.exec(content)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(content.slice(lastIndex, match.index));
    }

    if (match[1] && match[2]) {
      nodes.push(link(match[2], match[1])); // [text](url)
    } else if (match[3]) {
      nodes.push(link(match[3], match[3])); // [url]
    } else {
      let url = match[0];
      const trailing = /[.,;:!?]+$/.exec(url)?.[0] ?? "";
      if (trailing) url = url.slice(0, -trailing.length);
      nodes.push(link(url, url));
      if (trailing) nodes.push(trailing);
    }
    lastIndex = LINK_PATTERN.lastIndex;
  }
  if (lastIndex < content.length) {
    nodes.push(content.slice(lastIndex));
  }
  return nodes;
}

type ChatSearch = { c?: string | undefined; new?: number | undefined };

export const Route = createFileRoute("/")({
  validateSearch: (search: Record<string, unknown>): ChatSearch => ({
    c: typeof search["c"] === "string" ? search["c"] : undefined,
    new: typeof search["new"] === "number" ? search["new"] : undefined,
  }),
  head: () => ({
    meta: [
      { title: "FinkiBOT — Разговор со асистентот за ФИНКИ" },
      {
        name: "description",
        content:
          "Прашај го FinkiBOT за соопштенија, предмети, професори и распореди на ФИНКИ — Скопје.",
      },
      { property: "og:title", content: "FinkiBOT — Разговор со асистентот за ФИНКИ" },
      {
        property: "og:description",
        content: "Паметен асистент за студентите на ФИНКИ: разговор, пребарување, квизови.",
      },
    ],
  }),
  component: ChatPage,
});

function ChatPage() {
  const { t } = useI18n();
  const { c: convId, new: newFlag } = Route.useSearch();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const idRef = useRef<string>(newId());
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (convId) {
      const conv = loadConversations().find((x) => x.id === convId);
      if (conv) {
        idRef.current = conv.id;
        setMessages(conv.messages);
        return;
      }
    }
    idRef.current = newId();
    setMessages([]);
  }, [convId, newFlag]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function persist(next: ChatMessage[]) {
    if (next.length === 0) return;
    const list = loadConversations();
    const title = next[0]?.content.slice(0, 48) || "…";
    const conv: Conversation = {
      id: idRef.current,
      title,
      updatedAt: Date.now(),
      messages: next,
    };
    const rest = list.filter((x) => x.id !== conv.id);
    saveConversations([conv, ...rest]);
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    setError(null);
    setInput("");
    const history = messages;
    const withUser: ChatMessage[] = [...history, { role: "user", content: text }];
    setMessages([...withUser, { role: "assistant", content: "" }]);
    setLoading(true);
    let acc = "";
    try {
      await streamChat(text, history, (chunk) => {
        acc += chunk;
        setMessages([...withUser, { role: "assistant", content: acc }]);
      });
      persist([...withUser, { role: "assistant", content: acc }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setMessages(withUser);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-6 py-8">
          <h1 className="sr-only">FinkiBOT — {t("nav_chat")}</h1>
          {messages.length === 0 ? (
            <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
              {t("chat_empty")}
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
                >
                  <div
                    className={
                      m.role === "user"
                        ? "max-w-[80%] rounded-lg bg-primary px-3.5 py-2.5 text-sm whitespace-pre-wrap break-words text-primary-foreground"
                        : "max-w-[85%] rounded-lg border border-border bg-card px-3.5 py-2.5 text-sm whitespace-pre-wrap break-words text-card-foreground"
                    }
                  >
                    {m.content ? linkifyMessage(m.content) : loading ? "…" : ""}
                  </div>
                </div>
              ))}
            </div>
          )}
          {error ? (
            <div className="mt-4">
              <Notice kind="error">
                {t("error")}: {error}
              </Notice>
            </div>
          ) : null}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t border-border bg-background">
        <form onSubmit={send} className="mx-auto flex w-full max-w-3xl gap-2 px-6 py-4">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t("chat_placeholder")}
            className="flex-1 rounded-md border border-input bg-card px-3 py-2 text-sm outline-none focus:border-ring"
          />
          <button
            type="submit"
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity disabled:opacity-50"
          >
            <Send className="size-4" />
            {t("send")}
          </button>
        </form>
      </div>
    </div>
  );
}
