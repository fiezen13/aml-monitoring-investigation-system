import { AnimatePresence, motion } from "motion/react";
import { Maximize2, Minimize2, Sparkles, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../../api/client";
import type { ApiCopilotAction } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { PERMISSIONS } from "../../rbac/permissions";
import { transitions, useReduced } from "../../design/motion";
import { ActionProposalCard } from "./ActionProposalCard";
import { ActionReceipt } from "./ActionReceipt";
import {
  AssistantMessage,
  type ChatMessage,
  ConversationScroll,
  MessageRow,
  ThinkingRow,
  UserMessage,
} from "./Conversation";
import { CopilotComposer } from "./CopilotComposer";

/**
 * Trợ lý điều phối trên trang Phê duyệt SAR.
 *
 * Là một NGĂN KÉO rộng bám mép phải, không phải hộp thoại nhỏ giữa màn hình:
 * người dùng cần vẫn nhìn thấy hàng đợi phía sau trong lúc hỏi về nó, và một
 * thẻ đề xuất kèm danh sách hồ sơ không vừa trong một cột 512px.
 *
 * TRẠNG THÁI NGHIỆP VỤ ≠ TRẠNG THÁI TRÌNH BÀY. Đề xuất và kết cục của nó do máy
 * chủ giữ; ở đây chỉ giữ thêm việc thẻ nào đang mở rộng, đang bận, hiện câu báo
 * gì. Thu gọn một thẻ đã xong là thay đổi cách nhìn, không đụng tới dữ liệu
 * kiểm toán.
 */

interface ActionState {
  status: "pending" | "busy" | "done" | "cancelled" | "failed";
  message?: string;
  at?: string;
}

/**
 * Gợi ý mở đầu, KHÁC NHAU theo vai.
 *
 * Đưa "giao 3 hồ sơ cho Lan" cho một chuyên viên là mời họ làm việc mà máy chủ
 * sẽ từ chối, và bảo họ hỏi "ai đang ít việc nhất" là mời hỏi thứ trợ lý không
 * có dữ liệu để trả lời — ngữ cảnh của họ chỉ chứa hồ sơ của chính họ.
 */
const QUICK_ACTIONS_MANAGER = [
  { label: "Hồ sơ cần ưu tiên", prompt: "Hồ sơ nào cần ưu tiên xử lý trước?" },
  { label: "Chưa phân công", prompt: "Hồ sơ nào chưa có người xử lý?" },
  { label: "Quá hạn", prompt: "Hồ sơ nào đã quá hạn hoặc sắp tới hạn?" },
  { label: "Tải công việc nhóm", prompt: "Khối lượng công việc của từng chuyên viên hiện ra sao?" },
];

const QUICK_ACTIONS_SPECIALIST = [
  { label: "Hồ sơ của tôi", prompt: "Tôi đang có những hồ sơ nào?" },
  { label: "Đang chờ duyệt", prompt: "Hồ sơ nào tôi đã trình và đang chờ quản lý quyết định?" },
  { label: "Cần bổ sung", prompt: "Hồ sơ nào của tôi bị trả lại và cần bổ sung gì?" },
  { label: "Thiếu bằng chứng", prompt: "Hồ sơ nào của tôi còn câu chưa dẫn bằng chứng?" },
];

const EXAMPLES_MANAGER = [
  "Giao 3 hồ sơ ưu tiên cao nhất cho Lan",
  "Ai đang có ít hồ sơ nhất?",
  "Hồ sơ nào sắp quá hạn?",
];

const EXAMPLES_SPECIALIST = [
  "Hồ sơ nào tôi đã trình còn đang chờ duyệt?",
  "Hồ sơ nào của tôi bị trả lại?",
  "Hồ sơ nào của tôi còn thiếu bằng chứng?",
];

export function SarCopilotDrawer({
  open,
  onClose,
  onExecuted,
}: {
  open: boolean;
  onClose: () => void;
  /** Hàng đợi vừa đổi — trang cha nạp lại danh sách. */
  onExecuted: () => void;
}) {
  const reduced = useReduced();
  const { currentUser } = useApp();
  // Phân nhánh theo QUYỀN, không theo chuỗi vai trò — máy chủ cũng quyết định
  // như vậy, nên hai bên không thể lệch.
  const canCoordinate = currentUser?.permissions?.includes(PERMISSIONS.SAR_ASSIGN) ?? false;
  const quickActions = canCoordinate ? QUICK_ACTIONS_MANAGER : QUICK_ACTIONS_SPECIALIST;
  const examples = canCoordinate ? EXAMPLES_MANAGER : EXAMPLES_SPECIALIST;
  const [expanded, setExpanded] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [actions, setActions] = useState<Record<string, ActionState>>({});

  // Esc đóng ngăn kéo — nhưng KHÔNG khi còn một đề xuất đang chờ quyết định.
  // Bấm nhầm Esc mà mất một phương án vừa soạn xong là mất việc, nên ở trạng
  // thái đó người dùng phải chọn rõ Huỷ hoặc Xác nhận.
  const hasPending = useMemo(
    () => messages.some((m) => m.action && (actions[m.action.action_id]?.status ?? "pending") === "pending"),
    [messages, actions],
  );

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !hasPending) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, hasPending]);

  const send = useCallback(
    async (text: string) => {
      const q = text.trim();
      if (!q || sending) return;
      const history = messages.slice(-6).map((m) => ({ role: m.role, text: m.text }));
      setMessages((m) => [...m, { role: "user", text: q }]);
      setInput("");
      setSending(true);
      try {
        const res = await api.sarAiChat(q, history);
        setMessages((m) => [...m, { role: "assistant", text: res.answer, action: res.action ?? null }]);
      } catch {
        setMessages((m) => [
          ...m,
          { role: "assistant", text: "Không gọi được trợ lý. Thử lại sau." },
        ]);
      } finally {
        setSending(false);
      }
    },
    [messages, sending],
  );

  async function decide(actionId: string, confirm: boolean) {
    setActions((s) => ({ ...s, [actionId]: { status: "busy" } }));
    try {
      const res = confirm
        ? await api.confirmCopilotAction(actionId)
        : await api.cancelCopilotAction(actionId);
      const status: ActionState["status"] =
        res.status === "executed" ? "done" : res.status === "cancelled" ? "cancelled" : "failed";
      setActions((s) => ({
        ...s,
        [actionId]: { status, message: res.message, at: new Date().toISOString() },
      }));
      if (res.status === "executed") onExecuted();
    } catch (cause) {
      setActions((s) => ({
        ...s,
        [actionId]: {
          status: "failed",
          message: cause instanceof Error ? cause.message : "Không thực hiện được, thử lại sau.",
          at: new Date().toISOString(),
        },
      }));
    }
  }

  /** "Chỉnh sửa" = soạn lại yêu cầu; đề xuất cũ bị huỷ để không còn treo. */
  function editAction(action: ApiCopilotAction) {
    void decide(action.action_id, false);
    setInput(`Điều chỉnh phương án vừa rồi: `);
  }

  const width = expanded ? "min(88vw, 1280px)" : "clamp(620px, 48vw, 760px)";

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={reduced ? { duration: 0.01 } : transitions.state}
            onClick={() => !hasPending && onClose()}
            className="fixed inset-0 z-drawer bg-scrim"
            aria-hidden
          />
          <motion.aside
            role="dialog"
            aria-label="Trợ lý phê duyệt SAR"
            initial={reduced ? { opacity: 0 } : { x: 40, opacity: 0 }}
            animate={reduced ? { opacity: 1 } : { x: 0, opacity: 1 }}
            exit={reduced ? { opacity: 0 } : { x: 40, opacity: 0 }}
            transition={reduced ? { duration: 0.01 } : transitions.enter}
            style={{ width }}
            className="fixed inset-y-0 right-0 z-drawer flex h-dvh max-w-full flex-col border-l border-line-strong bg-side shadow-modal"
          >
            {/* Header — dính, không cuộn theo hội thoại. */}
            <header className="flex flex-none items-start gap-3 border-b border-line px-5 py-3.5">
              <Sparkles size={16} className="mt-0.5 flex-none text-primary" aria-hidden />
              <div className="min-w-0 flex-1">
                <h2 className="text-h3 font-semibold text-ink-hi">
                  {canCoordinate ? "Trợ lý phê duyệt SAR" : "Trợ lý công việc của bạn"}
                </h2>
                <p className="mt-0.5 text-data text-ink-low">
                  {canCoordinate
                    ? "Hỗ trợ tra cứu và điều phối công việc"
                    : "Hỗ trợ tra cứu phần việc của bạn"}
                </p>
              </div>
              <span className="mt-1 hidden items-center gap-1.5 text-data text-ink-low sm:flex">
                <span className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden />
                Đang hoạt động
              </span>
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                aria-label={expanded ? "Thu gọn bảng trợ lý" : "Mở rộng bảng trợ lý"}
                className="rounded-control p-1.5 text-ink-mid transition-colors hover:bg-elev hover:text-ink-hi focus:outline-none focus-visible:ring-1 focus-visible:ring-line-emphasis"
              >
                {expanded ? <Minimize2 size={14} aria-hidden /> : <Maximize2 size={14} aria-hidden />}
              </button>
              <button
                type="button"
                onClick={onClose}
                aria-label="Đóng bảng trợ lý"
                className="rounded-control p-1.5 text-ink-mid transition-colors hover:bg-elev hover:text-ink-hi focus:outline-none focus-visible:ring-1 focus-visible:ring-line-emphasis"
              >
                <X size={15} aria-hidden />
              </button>
            </header>

            {/* Gợi ý nhanh — cuộn ngang khi hẹp, không xuống dòng thành hai hàng. */}
            <div className="copilot-scroll flex flex-none gap-2 overflow-x-auto border-b border-line-faint px-5 py-2.5">
              {quickActions.map((q) => (
                <button
                  key={q.label}
                  type="button"
                  onClick={() => void send(q.prompt)}
                  disabled={sending}
                  className="whitespace-nowrap rounded-full border border-line px-2.5 py-1 text-data text-ink-mid transition-colors hover:border-line-emphasis hover:text-ink-hi focus:outline-none focus-visible:ring-1 focus-visible:ring-line-emphasis disabled:opacity-50"
                >
                  {q.label}
                </button>
              ))}
            </div>

            <ConversationScroll deps={messages.length + (sending ? 1 : 0)}>
              {messages.length === 0 && !sending && (
                <div className="flex flex-col items-center px-6 py-14 text-center">
                  <Sparkles size={20} className="text-primary" aria-hidden />
                  <h3 className="mt-3 text-h3 font-semibold text-ink-hi">
                    {canCoordinate ? "Trợ lý phê duyệt SAR" : "Trợ lý công việc của bạn"}
                  </h3>
                  <p className="mt-1.5 max-w-sm text-body leading-relaxed text-ink-low">
                    {canCoordinate
                      ? "Tra cứu hàng đợi, kiểm tra tải công việc và chuẩn bị giao việc cho chuyên viên. Mọi thay đổi đều cần bạn xác nhận."
                      : "Tra cứu hồ sơ bạn đang giữ và hồ sơ đã trình lên quản lý. Trợ lý chỉ đọc dữ liệu phần việc của bạn."}
                  </p>
                  <ul className="mt-5 space-y-1.5">
                    {examples.map((e) => (
                      <li key={e}>
                        <button
                          type="button"
                          onClick={() => void send(e)}
                          className="text-data text-ink-dim transition-colors hover:text-ink-mid focus:outline-none focus-visible:ring-1 focus-visible:ring-line-emphasis"
                        >
                          “{e}”
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {messages.map((m, i) => {
                const state = m.action ? (actions[m.action.action_id] ?? { status: "pending" }) : null;
                return (
                  <MessageRow key={i}>
                    {m.role === "user" ? <UserMessage text={m.text} /> : <AssistantMessage text={m.text} />}
                    {m.action &&
                      state &&
                      (state.status === "pending" || state.status === "busy" ? (
                        <ActionProposalCard
                          action={m.action}
                          busy={state.status === "busy"}
                          onConfirm={() => void decide(m.action!.action_id, true)}
                          onEdit={() => editAction(m.action!)}
                          onCancel={() => void decide(m.action!.action_id, false)}
                        />
                      ) : (
                        <ActionReceipt
                          action={m.action}
                          status={state.status}
                          message={state.message}
                          at={state.at}
                        />
                      ))}
                  </MessageRow>
                );
              })}

              {sending && <ThinkingRow />}
            </ConversationScroll>

            <CopilotComposer
              value={input}
              onChange={setInput}
              onSend={() => void send(input)}
              sending={sending}
            />
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
