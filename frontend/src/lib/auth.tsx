import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { apiGet, apiPost, setAuthToken, type AuthUser, type TokenResponse } from "@/lib/api";

type AuthState = {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const Ctx = createContext<AuthState>({
  user: null,
  loading: true,
  login: async () => {},
  register: async () => {},
  logout: () => {},
});

const STORAGE_KEY = "finkibot-token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  // Client-only, matching ThemeProvider/I18nProvider — localStorage doesn't exist
  // during SSR, so the token can only be read after mount.
  useEffect(() => {
    const token = localStorage.getItem(STORAGE_KEY);
    if (!token) {
      setLoading(false);
      return;
    }
    setAuthToken(token);
    apiGet<AuthUser>("/auth/me")
      .then(setUser)
      .catch(() => {
        localStorage.removeItem(STORAGE_KEY);
        setAuthToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  function applySession(res: TokenResponse) {
    localStorage.setItem(STORAGE_KEY, res.access_token);
    setAuthToken(res.access_token);
    setUser(res.user);
  }

  const login = useCallback(async (email: string, password: string) => {
    applySession(await apiPost<TokenResponse>("/auth/login", { email, password }));
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    applySession(await apiPost<TokenResponse>("/auth/register", { email, password }));
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setAuthToken(null);
    setUser(null);
  }, []);

  return <Ctx.Provider value={{ user, loading, login, register, logout }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  return useContext(Ctx);
}
