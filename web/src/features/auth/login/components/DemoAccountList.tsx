import { ChevronRight } from "lucide-react";

import type { User } from "../../../../types";

interface Props {
  users: User[];
  loading: boolean;
  selectedEmail: string;
  onPick: (user: User) => void;
}

/** Chữ cái đầu của hai từ cuối — "Nguyễn Quang Hưng" → "QH". */
function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[parts.length - 2][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * Danh sách tài khoản minh hoạ.
 *
 * Là danh sách hàng, không phải chồng thẻ. Bản cũ cho mỗi tài khoản một hộp có
 * viền và nền riêng, nên bốn tài khoản chiếm gần nửa chiều cao thẻ đăng nhập và
 * nặng ngang với chính cái nút truy cập. Ở đây chỉ hàng đang chọn mới có nền.
 *
 * Vai trò lấy nguyên `roleLabel` từ `/auth/users`. Không tự đặt nhãn ngắn kiểu
 * "Admin" hay "Analyst" cho đẹp: nhãn vai trò ở đây phải khớp đúng phân quyền
 * thật, nếu không người demo sẽ trông đợi quyền mà tài khoản không có.
 */
export function DemoAccountList({ users, loading, selectedEmail, onPick }: Props) {
  return (
    <section className="fc-auth-tight mt-5 border-t border-line-faint pt-4">
      <h3 className="fc-eyebrow mb-1.5">Tài khoản minh hoạ</h3>

      {loading && (
        <div className="flex flex-col gap-1">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-9 animate-pulse rounded-control bg-elev/60" />
          ))}
        </div>
      )}

      {!loading && !users.length && (
        <p className="text-2xs text-ink-low">Không tải được danh sách tài khoản minh hoạ.</p>
      )}

      <ul className="fc-auth-list -mx-1.5 flex max-h-[168px] flex-col overflow-y-auto">
        {users.map((user) => {
          const active = user.email === selectedEmail;
          return (
            <li key={user.id}>
              <button
                type="button"
                onClick={() => onPick(user)}
                aria-pressed={active}
                className={[
                  "group flex w-full items-center gap-2.5 rounded-control px-1.5 py-1.5 text-left transition-colors",
                  active ? "bg-primary-soft" : "hover:bg-elev",
                ].join(" ")}
              >
                <span
                  className={[
                    "flex h-7 w-7 flex-none items-center justify-center rounded-full font-mono text-3xs font-semibold",
                    active ? "bg-primary/20 text-primary" : "bg-elev text-ink-soft",
                  ].join(" ")}
                  aria-hidden
                >
                  {initials(user.name)}
                </span>

                <span className="min-w-0 flex-1">
                  <span className="block truncate text-2xs font-medium text-ink-hi">{user.name}</span>
                  <span className="block truncate text-3xs text-ink-low">{user.roleLabel}</span>
                </span>

                <ChevronRight
                  size={14}
                  aria-hidden
                  className="flex-none text-ink-dim transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-ink-soft"
                />
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
