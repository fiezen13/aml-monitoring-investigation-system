import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { SAR_DRAFT } from "../data/mockSar";
import { USERS } from "../data/mockUsers";
import type { SarStatus, SarValidationIssue, User } from "../types";

export interface ToastItem {
  id: number;
  tone: "success" | "error" | "info";
  title: string;
  detail?: string;
}

interface AppState {
  currentUser: User | null;
  login: (userId: string) => User | null;
  logout: () => void;

  /** Trạng thái SAR-2026-007 — mô phỏng luồng soạn → kiểm chứng → phê duyệt. */
  sarStatus: SarStatus;
  sarIssues: SarValidationIssue[];
  runValidation: () => void;
  fixIssues: () => void;
  submitForApproval: (reason: string) => void;
  approveSar: (reason: string) => void;
  rejectSar: (reason: string) => void;
  sarSubmittedBy: string;

  /** Vụ việc được tạo từ cảnh báo trong phiên demo. */
  caseCreated: boolean;
  createCase: (reason: string) => void;

  toasts: ToastItem[];
  pushToast: (toast: Omit<ToastItem, "id">) => void;
  dismissToast: (id: number) => void;
}

const AppContext = createContext<AppState | null>(null);

let toastSeq = 0;

/**
 * Khoá lưu phiên đăng nhập trong sessionStorage.
 *
 * Giữ phiên qua một lần tải lại trang là điều kiện để đường dẫn sâu dùng
 * được: không có nó, mở thẳng /alerts/ALT-004-rule hay bấm F5 giữa buổi
 * demo đều rơi về màn hình đăng nhập.
 *
 * Đây là phiên mô phỏng, không phải xác thực thật: không có mật khẩu nào
 * được kiểm tra và không có token nào được cấp. sessionStorage (hết khi
 * đóng tab) thay vì localStorage là chủ ý — một danh tính giả không nên
 * sống lâu hơn cái tab tạo ra nó.
 */
const SESSION_KEY = "fin07.session.userId";

function readStoredUser(): User | null {
  try {
    const userId = window.sessionStorage.getItem(SESSION_KEY);
    return userId ? (USERS.find((u) => u.id === userId) ?? null) : null;
  } catch {
    // Trình duyệt chặn storage (chế độ riêng tư, cookie bị khoá) — chạy tiếp
    // không có phiên lưu sẵn thay vì làm hỏng cả ứng dụng.
    return null;
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [currentUser, setCurrentUser] = useState<User | null>(readStoredUser);
  const [sarStatus, setSarStatus] = useState<SarStatus>(SAR_DRAFT.status);
  const [sarIssues, setSarIssues] = useState<SarValidationIssue[]>(
    SAR_DRAFT.validationIssues,
  );
  const [sarSubmittedBy, setSarSubmittedBy] = useState<string>(
    SAR_DRAFT.submittedBy,
  );
  const [caseCreated, setCaseCreated] = useState(true);
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const pushToast = useCallback((toast: Omit<ToastItem, "id">) => {
    const id = ++toastSeq;
    setToasts((prev) => [...prev, { ...toast, id }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4200);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const login = useCallback((userId: string) => {
    const user = USERS.find((u) => u.id === userId) ?? null;
    setCurrentUser(user);
    try {
      if (user) window.sessionStorage.setItem(SESSION_KEY, user.id);
    } catch {
      /* không lưu được thì phiên chỉ sống trong bộ nhớ — vẫn dùng được */
    }
    return user;
  }, []);

  const logout = useCallback(() => {
    setCurrentUser(null);
    try {
      window.sessionStorage.removeItem(SESSION_KEY);
    } catch {
      /* xoá thất bại không ngăn được việc đăng xuất khỏi bộ nhớ */
    }
  }, []);

  const runValidation = useCallback(() => {
    setSarStatus((prev) => {
      if (prev !== "DRAFT" && prev !== "VALIDATION_FAILED") return prev;
      return sarIssues.some((i) => i.severity === "error")
        ? "VALIDATION_FAILED"
        : "VALIDATION_PASSED";
    });
  }, [sarIssues]);

  const fixIssues = useCallback(() => {
    setSarIssues((prev) => prev.filter((i) => i.severity !== "error"));
    setSarStatus("VALIDATION_PASSED");
  }, []);

  const submitForApproval = useCallback(
    (_reason: string) => {
      setSarStatus("PENDING_REVIEW");
      if (currentUser) setSarSubmittedBy(currentUser.name);
    },
    [currentUser],
  );

  const approveSar = useCallback((_reason: string) => {
    setSarStatus("APPROVED");
  }, []);

  const rejectSar = useCallback((_reason: string) => {
    setSarStatus("REJECTED");
  }, []);

  const createCase = useCallback((_reason: string) => {
    setCaseCreated(true);
  }, []);

  const value = useMemo<AppState>(
    () => ({
      currentUser,
      login,
      logout,
      sarStatus,
      sarIssues,
      runValidation,
      fixIssues,
      submitForApproval,
      approveSar,
      rejectSar,
      sarSubmittedBy,
      caseCreated,
      createCase,
      toasts,
      pushToast,
      dismissToast,
    }),
    [
      currentUser,
      login,
      logout,
      sarStatus,
      sarIssues,
      runValidation,
      fixIssues,
      submitForApproval,
      approveSar,
      rejectSar,
      sarSubmittedBy,
      caseCreated,
      createCase,
      toasts,
      pushToast,
      dismissToast,
    ],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp phải được dùng bên trong AppProvider");
  return ctx;
}
