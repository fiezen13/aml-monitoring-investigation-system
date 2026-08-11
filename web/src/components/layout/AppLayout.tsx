import { useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { api } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ROUTE_TITLES } from "../../config/nav";
import { useApp } from "../../context/AppContext";
import { ToastRegion } from "../common/Toast";
import { CommandPalette } from "./CommandPalette";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

/**
 * Khung ứng dụng: sidebar trái + header + vùng nội dung.
 *
 * Vùng nội dung **không** tự thêm padding. Một nửa số màn hình (World Monitor,
 * Case workspace, Network Graph) là bố cục toàn khung có panel riêng chạm sát
 * mép; padding ở đây sẽ khiến chúng phải tự bù trừ ngược lại. Các trang dạng
 * danh sách tự đặt `p-4` của mình.
 */
export function AppLayout() {
  const { currentUser } = useApp();
  const location = useLocation();
  const [paletteQuery, setPaletteQuery] = useState("");

  const counts = useApi(() => api.navCounts(), []);
  // Chỉ tra cứu khi đã gõ đủ để kết quả có nghĩa — mỗi ký tự là một lượt gọi.
  const search = useApi(
    () => (paletteQuery.trim().length >= 2 ? api.search(paletteQuery.trim()) : Promise.resolve([])),
    [paletteQuery],
  );

  if (!currentUser) {
    return <Navigate to="/login" replace />;
  }

  const crumb = ROUTE_TITLES.find(([prefix]) => location.pathname.startsWith(prefix))?.[1] ?? "FIN-07";

  return (
    <div className="flex h-screen overflow-hidden bg-app">
      <Sidebar counts={counts.data ?? {}} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header crumb={crumb} criticalCount={counts.data?.critical ?? 0} />
        <main className="relative min-h-0 min-w-0 flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
      <CommandPalette entities={search.data ?? []} onQueryChange={setPaletteQuery} />
      <ToastRegion />
    </div>
  );
}
