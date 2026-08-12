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
 * Danh sách tài khoản demo.
 *
 * Vai trò lấy nguyên `roleLabel` từ `/auth/users`. Không tự đặt nhãn ngắn kiểu
 * "Admin" hay "Analyst" cho đẹp: nhãn vai trò ở đây phải khớp đúng phân quyền
 * thật, nếu không người demo sẽ trông đợi quyền mà tài khoản không có.
 */
export function DemoAccountList({ users, loading, selectedEmail, onPick }: Props) {
  return (
    <section className="mt-5 border-t border-line pt-4">
      <h3 className="mb-2.5 text-3xs font-semibold uppercase tracking-[0.14em] text-ink-dim">Tài khoản demo</h3>

      {loading && (
        <div className="flex flex-col gap-1.5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-[46px] animate-pulse rounded-control bg-elev/60" />
          ))}
        </div>
      )}

      {!loading && !users.length && (
        <p className="text-2xs text-ink-low">Không tải được danh sách tài khoản demo.</p>
      )}

      <ul className="flex max-h-[212px] flex-col gap-1.5 overflow-y-auto pr-0.5 [@media(max-height:830px)]:max-h-[104px]">
        {users.map((user) => {
          const active = user.email === selectedEmail;
          return (
            <li key={user.id}>
              <button
                type="button"
                onClick={() => onPick(user)}
                aria-pressed={active}
                className={[
                  "group flex w-full items-center gap-2.5 rounded-control border px-2.5 py-2 text-left transition-[background-color,border-color,transform]",
                  active
                    ? "border-primary-line bg-primary-soft"
                    : "border-line bg-sunken hover:border-line-strong hover:bg-elev",
                ].join(" ")}
              >
                <span
                  className={[
                    "flex h-8 w-8 flex-none items-center justify-center rounded-full font-mono text-2xs font-semibold",
                    active ? "bg-primary/20 text-primary" : "bg-elev text-ink-soft",
                  ].join(" ")}
                  aria-hidden
                >
                  {initials(user.name)}
                </span>

                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-medium text-ink-hi">{user.name}</span>
                  <span className="mt-0.5 block truncate text-3xs text-ink-low">{user.roleLabel}</span>
                </span>

                <span className="flex flex-none items-center gap-1 text-3xs text-ink-dim transition-colors group-hover:text-primary">
                  Dùng thử
                  <ChevronRight
                    size={13}
                    aria-hidden
                    className="transition-transform duration-150 group-hover:translate-x-0.5"
                  />
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
