import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, AUTH_EXPIRED_EVENT, SESSION_TOKEN_KEY } from "../api/client";
import type { User } from "../types";

export interface ToastItem {
  id: number;
  tone: "success" | "error" | "info";
  title: string;
  detail?: string;
}

interface AppState {
  currentUser: User | null;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  toasts: ToastItem[];
  pushToast: (toast: Omit<ToastItem, "id">) => void;
  dismissToast: (id: number) => void;
}

const AppContext = createContext<AppState | null>(null);
const SESSION_USER_KEY = "fin07.session.user";
const GRAFANA_SESSION_COOKIE = "fin07_session";
let toastSeq = 0;

function syncGrafanaSession(token: string | null): void {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  if (token) {
    document.cookie = `${GRAFANA_SESSION_COOKIE}=${encodeURIComponent(token)}; Path=/; SameSite=Strict${secure}`;
  } else {
    document.cookie = `${GRAFANA_SESSION_COOKIE}=; Path=/; SameSite=Strict; Max-Age=0${secure}`;
  }
}

function readStoredUser(): User | null {
  try {
    const raw = window.sessionStorage.getItem(SESSION_USER_KEY);
    const token = window.sessionStorage.getItem(SESSION_TOKEN_KEY);
    if (!raw || !token) {
      syncGrafanaSession(null);
      return null;
    }
    const user = JSON.parse(raw) as User;
    syncGrafanaSession(token);
    return user;
  } catch {
    syncGrafanaSession(null);
    return null;
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [currentUser, setCurrentUser] = useState<User | null>(readStoredUser);
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const pushToast = useCallback((toast: Omit<ToastItem, "id">) => {
    const id = ++toastSeq;
    setToasts((prev) => [...prev, { ...toast, id }]);
    window.setTimeout(() => setToasts((prev) => prev.filter((item) => item.id !== id)), 4200);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const clearLocalSession = useCallback(() => {
    window.sessionStorage.removeItem(SESSION_TOKEN_KEY);
    window.sessionStorage.removeItem(SESSION_USER_KEY);
    syncGrafanaSession(null);
    setCurrentUser(null);
  }, []);

  useEffect(() => {
    const expired = () => clearLocalSession();
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, expired);
  }, [clearLocalSession]);

  useEffect(() => {
    if (!currentUser) return;
    void api.me().then(setCurrentUser).catch(() => clearLocalSession());
    // Chỉ xác minh token đã lưu khi provider mount; không gọi lại sau mỗi render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await api.login(email, password);
    window.sessionStorage.setItem(SESSION_TOKEN_KEY, result.token);
    window.sessionStorage.setItem(SESSION_USER_KEY, JSON.stringify(result.user));
    syncGrafanaSession(result.token);
    setCurrentUser(result.user);
    return result.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      clearLocalSession();
    }
  }, [clearLocalSession]);

  const value = useMemo<AppState>(
    () => ({ currentUser, login, logout, toasts, pushToast, dismissToast }),
    [currentUser, login, logout, toasts, pushToast, dismissToast],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp phải được dùng bên trong AppProvider");
  return ctx;
}
