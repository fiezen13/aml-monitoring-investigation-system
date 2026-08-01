import { Bell, MessageSquare, Moon } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useApp } from "../../context/AppContext";
import { USERS } from "../../data/mockUsers";
import { SearchInput } from "../common/SearchInput";

interface HeaderProps {
  title?: string;
}

export function Header({ title }: HeaderProps) {
  const { currentUser, login, pushToast } = useApp();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [accountOpen, setAccountOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-4 border-b border-line bg-app/95 px-4 backdrop-blur">
      {title && (
        <h1 className="whitespace-nowrap text-[16px] font-bold text-ink-hi">{title}</h1>
      )}
      <div className="max-w-md flex-1">
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Tìm kiếm giao dịch, khách hàng, hồ sơ... (⌘K)"
        />
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        <div className="relative">
          <button
            type="button"
            aria-label="Thông báo"
            onClick={() => setNotifOpen((v) => !v)}
            className="relative rounded p-2 text-ink-mid hover:bg-panel hover:text-ink-hi"
          >
            <Bell size={16} />
            <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-risk" aria-hidden />
          </button>
          {notifOpen && (
            <div className="absolute right-0 top-full z-40 mt-1 w-72 rounded-panel border border-line bg-elev p-3 shadow-xl">
              <div className="mb-2 text-2xs font-semibold uppercase tracking-wide text-ink-mid">
                Thông báo nội bộ
              </div>
              <p className="text-2xs leading-relaxed text-ink-mid">
                3 cảnh báo mới vượt ngưỡng rủi ro cao. Thông báo chỉ gửi nội bộ —
                không có kênh nào tới khách hàng đang bị điều tra (NT6).
              </p>
            </div>
          )}
        </div>
        <button
          type="button"
          aria-label="Tin nhắn"
          onClick={() => pushToast({ tone: "info", title: "Hộp thư nội bộ (mô phỏng)" })}
          className="rounded p-2 text-ink-mid hover:bg-panel hover:text-ink-hi"
        >
          <MessageSquare size={16} />
        </button>
        <button
          type="button"
          aria-label="Chế độ tối"
          className="rounded p-2 text-ink-mid hover:bg-panel hover:text-ink-hi"
        >
          <Moon size={16} />
        </button>

        <span className="mx-1 h-6 w-px bg-line" aria-hidden />

        {currentUser && (
          <div className="relative">
            <button
              type="button"
              onClick={() => setAccountOpen((v) => !v)}
              aria-expanded={accountOpen}
              className="flex items-center gap-2.5 rounded-control px-2 py-1 hover:bg-panel"
            >
              <div className="text-right">
                <div className="text-[13px] font-semibold leading-tight text-ink-hi">
                  {currentUser.name}
                </div>
                <div className="text-2xs uppercase tracking-wide text-ink-low">
                  {currentUser.roleLabel}
                </div>
              </div>
              <span className="flex h-8 w-8 items-center justify-center rounded-full border border-primary/40 bg-elev text-2xs font-bold text-primary">
                {currentUser.name
                  .split(" ")
                  .slice(-2)
                  .map((w) => w[0])
                  .join("")}
              </span>
            </button>
            {accountOpen && (
              <div className="absolute right-0 top-full z-40 mt-1 w-60 rounded-panel border border-line bg-elev py-1 shadow-xl">
                <div className="border-b border-line px-3 py-2 text-2xs uppercase tracking-wide text-ink-low">
                  Chuyển vai trò demo
                </div>
                {USERS.map((user) => (
                  <button
                    key={user.id}
                    type="button"
                    onClick={() => {
                      login(user.id);
                      setAccountOpen(false);
                      pushToast({
                        tone: "info",
                        title: `Đang làm việc với vai trò ${user.roleLabel}`,
                        detail: user.name,
                      });
                    }}
                    className={`block w-full px-3 py-1.5 text-left text-[13px] hover:bg-panel ${
                      user.id === currentUser.id ? "text-primary" : "text-ink-mid"
                    }`}
                  >
                    {user.name}
                    <span className="block text-2xs text-ink-low">{user.roleLabel}</span>
                  </button>
                ))}
                <div className="border-t border-line">
                  <button
                    type="button"
                    onClick={() => navigate("/login")}
                    className="block w-full px-3 py-2 text-left text-[13px] text-risk hover:bg-panel"
                  >
                    Đăng xuất
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
