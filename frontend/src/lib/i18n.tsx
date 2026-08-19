import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "mk" | "en";

const dict = {
  brand: { mk: "FinkiBOT", en: "FinkiBOT" },
  tagline: { mk: "Асистент за студенти на ФИНКИ", en: "Assistant for FINKI students" },
  nav_chat: { mk: "Разговор", en: "Chat" },
  nav_search: { mk: "Пребарување", en: "Search" },
  nav_quiz: { mk: "Квиз", en: "Quiz" },
  nav_subscribe: { mk: "Известувања", en: "Notifications" },
  nav_insights: { mk: "Insights", en: "Insights" },
  nav_mcp: { mk: "MCP алатки", en: "MCP tools" },
  profile: { mk: "Профил", en: "Profile" },
  guest: { mk: "Гостин", en: "Guest" },
  no_login: { mk: "Без најава", en: "No sign-in needed" },
  settings: { mk: "Поставки", en: "Settings" },
  theme: { mk: "Тема", en: "Theme" },
  light: { mk: "Светла", en: "Light" },
  dark: { mk: "Темна", en: "Dark" },
  system: { mk: "Систем", en: "System" },
  language: { mk: "Јазик", en: "Language" },
  history: { mk: "Историја на разговори", en: "Chat history" },
  new_chat: { mk: "Нов разговор", en: "New chat" },
  no_history: { mk: "Сè уште нема разговори", en: "No conversations yet" },
  chat_placeholder: { mk: "Прашај нешто за ФИНКИ…", en: "Ask something about FINKI…" },
  send: { mk: "Испрати", en: "Send" },
  chat_empty: {
    mk: "Постави прашање за соопштенија, предмети, професори или распоред.",
    en: "Ask about announcements, courses, professors or schedules.",
  },
  search_placeholder: { mk: "Пребарај содржина…", en: "Search content…" },
  all_sources: { mk: "Сите извори", en: "All sources" },
  submit_search: { mk: "Пребарај", en: "Search" },
  no_results: { mk: "Нема резултати", en: "No results" },
  loading: { mk: "Се вчитува…", en: "Loading…" },
  error: { mk: "Грешка", en: "Error" },
  source_ref: { mk: "Извор", en: "Source" },
  back: { mk: "← Назад", en: "← Back" },
  professors: { mk: "Професори", en: "Professors" },
  assistants: { mk: "Асистенти", en: "Assistants" },
  tags: { mk: "Тагови", en: "Tags" },
  quiz_from_course: { mk: "Од предмет", en: "From a course" },
  quiz_upload: { mk: "Прикачи материјал", en: "Upload material" },
  course_query: { mk: "Предмет", en: "Course" },
  num_questions: { mk: "Број на прашања", en: "Number of questions" },
  generate: { mk: "Генерирај квиз", en: "Generate quiz" },
  sources_label: { mk: "Извори", en: "Sources" },
  check_answers: { mk: "Провери одговори", en: "Check answers" },
  reset: { mk: "Ресетирај", en: "Reset" },
  email: { mk: "Е-пошта", en: "Email" },
  keywords: { mk: "Клучни зборови", en: "Keywords" },
  course_codes: { mk: "Кодови на предмети", en: "Course codes" },
  add: { mk: "Додај", en: "Add" },
  subscribe: { mk: "Претплати се", en: "Subscribe" },
  subscribe_ok: {
    mk: "Испративме е-порака за потврда. Провери го сандачето.",
    en: "We sent a confirmation email. Please check your inbox.",
  },
  insights_docs: { mk: "Документи по извор и тип", en: "Documents by source and type" },
  insights_months: { mk: "Соопштенија по месец", en: "Announcements by month" },
  insights_tags: { mk: "Најчести тагови на предмети", en: "Most common course tags" },
  insights_sem: { mk: "Предмети по семестар", en: "Courses by semester" },
  run: { mk: "Изврши", en: "Run" },
  results_count: { mk: "Резултати", en: "Results" },
  mcp_intro: {
    mk: "Овие MCP алатки ги изложуваме кон надворешни AI клиенти (на пр. Claude Desktop). Тука можеш да ги пробаш директно.",
    en: "These MCP tools are exposed to external AI clients (e.g. Claude Desktop). You can try them here.",
  },
} as const;

export type TKey = keyof typeof dict;

const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: (k: TKey) => string }>({
  lang: "mk",
  setLang: () => {},
  t: (k) => dict[k].mk,
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("mk");

  useEffect(() => {
    const saved = localStorage.getItem("finkibot-lang");
    if (saved === "en" || saved === "mk") setLangState(saved);
  }, []);

  const setLang = (l: Lang) => {
    setLangState(l);
    localStorage.setItem("finkibot-lang", l);
  };

  const t = (k: TKey) => dict[k][lang];

  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>;
}

export function useI18n() {
  return useContext(Ctx);
}
