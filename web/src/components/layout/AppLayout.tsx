import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { api } from "../../api/client";
import { useApi } from "../../api/useApi";
import { ROUTE_TITLES, canAccess } from "../../config/nav";
import { useApp } from "../../context/AppContext";
import { useConsole } from "../../context/ConsoleContext";
import { pageVariants, safeVariants, transitions, useReduced } from "../../design/motion";
import { useIsNarrow } from "../../hooks/useMediaQuery";
import { ToastRegion } from "../common/Toast";
import { CommandPalette } from "./CommandPalette";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

/**
 * Khung ứng dụng: sidebar trái + header + vùng nội dung.
 *
 * Vùng nội dung **không** tự thêm padding — `PageShell` của từng trang quyết
 * định điều đó qua biến thể của nó. Ở đây chỉ còn ba việc: bầu không khí nền,
 * chuyển màn hình, và bố cục thích ứng khi khung hẹp.
 *
 * Dưới 1024px sidebar rời khỏi dòng chảy bố cục và trở thành lớp phủ: giữ
 * nguyên một cột cố định 218px trên màn 1024 nghĩa là chỉ còn 806px cho một
 * bảng mười cột.
 */

/**
 * Các route là không gian làm việc — chúng giữ camera, lựa chọn và vị trí cuộn
 * giữa các lần điều hướng, nên không được fade toàn khung khi vào: cú fade ấy
 * phá đúng cảm giác liên tục mà chúng phải có.
 */
const WORKSPACE_PREFIXES = ["/world", "/network"];

function isWorkspace(pathname: string): boolean {
  return WORKSPACE_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

export function AppLayout() {
  const { currentUser } = useApp();
  const location = useLocation();
  const reduced = useReduced();
  const narrow = useIsNarrow();
  const [paletteQuery, setPaletteQuery] = useState("");
  const [navOpen, setNavOpen] = useState(false);

  // Badge sidebar và dải ngày trên header phải theo bộ dữ liệu đang chọn:
  // không lọc thì badge cộng cảnh báo của hai bộ, và dải ngày ghép min của
  // bộ này với max của bộ kia.
  const { dataset } = useConsole();
  const counts = useApi(() => api.navCounts({ dataset }), [dataset], `nav-counts:${dataset}`);
  // Ô lệnh tra ra cảnh báo, vụ việc và tài khoản. Vai trò không được vào hồ sơ
  // điều tra thì cũng không được tra cứu chúng ở đây — API sẽ trả 403, và gọi
  // để nhận về 403 sau mỗi ký tự chỉ tạo tiếng ồn.
  const canSearch = canAccess("/alerts", currentUser?.role);
  // Chỉ tra cứu khi đã gõ đủ để kết quả có nghĩa — mỗi ký tự là một lượt gọi.
  const search = useApi(
    () =>
      canSearch && paletteQuery.trim().length >= 2 ? api.search(paletteQuery.trim()) : Promise.resolve([]),
    [paletteQuery, canSearch],
  );

  // Chuyển sang khung rộng thì lớp phủ không còn lý do tồn tại; để nguyên sẽ có
  // một tấm scrim vô hình chặn mọi cú bấm.
  useEffect(() => {
    if (!narrow) setNavOpen(false);
  }, [narrow]);

  if (!currentUser) {
    return <Navigate to="/login" replace />;
  }

  // Lọc menu chỉ giấu lối vào. Chốt chặn thật cho việc gõ thẳng URL nằm ở đây —
  // và ở tầng API, nơi dữ liệu bị từ chối kể cả khi màn hình đã mở.
  if (!canAccess(location.pathname, currentUser.role)) {
    return <Navigate to="/403" replace />;
  }

  const crumb = ROUTE_TITLES.find(([prefix]) => location.pathname.startsWith(prefix))?.[1] ?? "FIN-07";
  const workspace = isWorkspace(location.pathname);

  return (
    <div className="fc-atmosphere flex h-screen overflow-hidden bg-app">
      <div className="flex h-full min-w-0 flex-1">
        {!narrow && <Sidebar counts={counts.data ?? {}} />}

        <div className="flex min-w-0 flex-1 flex-col">
          <Header
            crumb={crumb}
            criticalCount={counts.data?.critical ?? 0}
            dataPeriod={{
              start: counts.data?.data_period_start ?? null,
              end: counts.data?.data_period_end ?? null,
            }}
            onOpenNav={narrow ? () => setNavOpen(true) : undefined}
          />
          <main className="relative min-h-0 min-w-0 flex-1 overflow-auto">
            <motion.div
              key={location.pathname}
              variants={workspace ? undefined : safeVariants(pageVariants, reduced)}
              initial={workspace ? false : "initial"}
              animate={workspace ? undefined : "animate"}
              className={workspace ? "h-full" : "min-h-full"}
            >
              <Outlet />
            </motion.div>
          </main>
        </div>
      </div>

      {/* Sidebar dạng lớp phủ cho khung hẹp. */}
      <AnimatePresence>
        {narrow && navOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={reduced ? { duration: 0.01 } : transitions.state}
              onClick={() => setNavOpen(false)}
              className="fixed inset-0 z-drawer bg-scrim"
              aria-hidden
            />
            <motion.div
              initial={reduced ? { opacity: 0 } : { x: -240 }}
              animate={reduced ? { opacity: 1 } : { x: 0 }}
              exit={reduced ? { opacity: 0 } : { x: -240 }}
              transition={reduced ? { duration: 0.01 } : transitions.layout}
              className="fixed inset-y-0 left-0 z-drawer"
            >
              <Sidebar counts={counts.data ?? {}} onNavigate={() => setNavOpen(false)} />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <CommandPalette entities={search.data ?? []} onQueryChange={setPaletteQuery} />
      <ToastRegion />
    </div>
  );
}
