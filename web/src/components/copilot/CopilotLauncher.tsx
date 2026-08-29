import { Sparkles } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { useApp } from "../../context/AppContext";
import { PERMISSIONS } from "../../rbac/permissions";
import { SarCopilotDrawer } from "./SarCopilotDrawer";

/**
 * Lối vào trợ lý AI, có ở MỌI trang nghiệp vụ.
 *
 * Trước đây trợ lý chỉ mở được từ đúng một trang cho mỗi vai — quản lý ở màn
 * Phê duyệt, chuyên viên ở màn Báo cáo của tôi — và cả hai nút đều nằm khuất
 * trong nội dung trang. Người dùng đi tìm mà không thấy, nên một tính năng đã
 * dựng xong coi như không tồn tại.
 *
 * Nay một nút nổi cố định ở góc, và MỘT thể hiện ngăn kéo duy nhất dùng chung.
 * Các trang muốn có nút riêng theo ngữ cảnh thì gọi `useCopilot().open()` —
 * không tự dựng thêm ngăn kéo, để hội thoại không bị nhân bản.
 */

interface CopilotApi {
  open: () => void;
  /** Vai này có được dùng trợ lý không — Quản trị hệ thống thì không. */
  available: boolean;
}

const CopilotContext = createContext<CopilotApi>({ open: () => {}, available: false });

export function useCopilot(): CopilotApi {
  return useContext(CopilotContext);
}

export function CopilotProvider({ children }: { children: React.ReactNode }) {
  const { currentUser } = useApp();
  const [open, setOpen] = useState(false);
  // Trợ lý chỉ phục vụ hai vai NGHIỆP VỤ. Quản trị hệ thống không đọc hồ sơ
  // khách hàng, nên cũng không có hàng đợi nào để hỏi.
  const available = currentUser?.permissions?.includes(PERMISSIONS.SAR_READ) ?? false;

  const api = useMemo<CopilotApi>(
    () => ({ open: () => setOpen(true), available }),
    [available],
  );
  const onExecuted = useCallback(() => {
    // Một lượt giao việc vừa được thực thi từ trợ lý. Trang đang mở tự nạp lại
    // qua vòng đời của chính nó; ở đây không ép làm mới toàn ứng dụng.
  }, []);

  return (
    <CopilotContext.Provider value={api}>
      {children}
      {available && (
        <>
          {!open && (
            <button
              type="button"
              onClick={() => setOpen(true)}
              aria-label="Mở trợ lý AI"
              className="fixed bottom-5 right-5 z-drawer inline-flex items-center gap-2 rounded-full border border-accent-line bg-raised px-4 py-2.5 text-body font-medium text-ink-hi shadow-modal transition-colors hover:border-primary/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
            >
              <Sparkles size={15} className="text-primary" aria-hidden />
              Trợ lý AI
            </button>
          )}
          <SarCopilotDrawer open={open} onClose={() => setOpen(false)} onExecuted={onExecuted} />
        </>
      )}
    </CopilotContext.Provider>
  );
}
