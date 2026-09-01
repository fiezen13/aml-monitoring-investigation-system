import { Bell, Menu, Search } from "lucide-react";
import { useState } from "react";
import { useLocation } from "react-router-dom";

import { useApp } from "../../context/AppContext";
import { OPERATIONAL_DATASETS, useConsole } from "../../context/ConsoleContext";
import { TEXT } from "../../design/typography";
import { Badge, IconButton, Popover, PulseDot, Select } from "../ui";

// Bộ chọn "môi trường mô phỏng" đã gỡ: chỉ còn một môi trường thật nên nó là
// một dropdown chết (không nối vào truy vấn nào). Nhãn POC + kỳ dữ liệu bên phải
// đã nói đủ đây là bản trình diễn.

interface Props {
  /** Tên màn hình hiện tại. Đây là chỗ DUY NHẤT hiển thị nó. */
  crumb?: string;
  /** Số cảnh báo mức nghiêm trọng, hiện ở chuông thông báo. */
  criticalCount?: number;
  /** Chỉ có ở khung hẹp, nơi sidebar là lớp phủ. */
  onOpenNav?: () => void;
  /** Kỳ dữ liệu đang hiển thị, lấy từ `/nav-counts`. */
  dataPeriod?: { start: string | null; end: string | null };
}

/** `2022-09-01` → `01/09/2022`. Giữ nguyên chuỗi ISO nếu định dạng lạ. */
function viDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const [y, m, d] = iso.split("-");
  return y && m && d ? `${d}/${m}/${y}` : iso;
}

export function Header({ crumb, criticalCount = 0, onOpenNav, dataPeriod }: Props) {
  const { currentUser } = useApp();
  const { dataset, setDataset, setPaletteOpen } = useConsole();
  const [bellOpen, setBellOpen] = useState(false);

  // Bộ chọn bộ dữ liệu chỉ có nghĩa ở các trang vận hành ĐỌC theo bộ dữ liệu:
  // Tổng quan, Cảnh báo, Vụ việc, Tra cứu giao dịch. Mọi trang khác — Giám sát
  // địa lý (chỉ SAML-D), Tài sản mã hoá (Bitcoin), Đồ thị mạng lưới, và các trang
  // KỸ THUẬT/QUẢN TRỊ — không đọc giá trị này, nên ẩn bộ chọn cho nhất quán (chọn
  // ở đó không đổi gì mà còn âm thầm đổi trạng thái toàn cục cho trang khác).
  const pathname = useLocation().pathname;
  // `/world` (Giám sát địa lý) CŨNG đọc bộ dữ liệu: bộ IBM không có trường quốc
  // gia nên trang tắt bản đồ. Trước đây bộ chọn bị ẩn ở đây, thành ra người dùng
  // rơi vào một màn hình rỗng mà không có cách nào đổi sang bộ có địa lý.
  const showDatasetSelector = ["/dashboard", "/alerts", "/cases", "/transactions", "/world"].some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  );

  const start = viDate(dataPeriod?.start);
  const end = viDate(dataPeriod?.end);
  const periodLabel = start && end ? `${start} – ${end}` : null;

  const initials = (currentUser?.name ?? "")
    .split(" ")
    .slice(-2)
    .map((word) => word[0])
    .join("");

  return (
    <header className="flex h-14 flex-none items-center gap-2 border-b border-line-soft bg-side px-3 lg:px-4">
      {onOpenNav && (
        <IconButton label="Mở thanh điều hướng" icon={<Menu size={17} />} onClick={onOpenNav} size="sm" />
      )}

      <h1 className={`truncate-1 flex-none ${TEXT.h3}`}>{crumb}</h1>

      <button
        type="button"
        onClick={() => setPaletteOpen(true)}
        className="ml-1 flex h-8 min-w-0 flex-[0_1_300px] items-center gap-2 overflow-hidden rounded-control border border-line-strong bg-sunken px-2.5 text-ink-low transition-colors hover:border-line-emphasis hover:text-ink-mid"
      >
        <Search size={13} className="flex-none" aria-hidden />
        <span className="truncate-1 flex-1 text-left text-data">Tìm thực thể, vụ việc, cảnh báo…</span>
        <span className="hidden flex-none rounded-sm border border-line-strong px-1.5 font-mono text-micro sm:block">
          ⌘K
        </span>
      </button>

      <div className="flex-1" />

      {/* Bộ dữ liệu đang xem — bộ chọn TOÀN CỤC cho các trang vận hành đọc theo
          bộ dữ liệu (Tổng quan, Cảnh báo, Vụ việc, Tra cứu giao dịch). Ẩn ở mọi
          trang khác vì chúng không dùng giá trị này. */}
      {showDatasetSelector && (
        <Select
          aria-label="Bộ dữ liệu đang xem"
          value={dataset}
          onChange={(event) => setDataset(event.target.value)}
          className="w-[150px] sm:w-[190px]"
        >
          {OPERATIONAL_DATASETS.map((ds) => (
            <option key={ds.value} value={ds.value}>
              Bộ dữ liệu: {ds.label}
            </option>
          ))}
        </Select>
      )}

      {/* Đây từng là bộ chọn 1h/24h/7d/30d. Nó không nối vào truy vấn nào —
          `/dashboard` chỉ trả tổng của một lô chạy, không có trường nào theo
          trục thời gian — nên bấm vào không có gì đổi ngoài một dòng nhãn.
          Tệ hơn: nối thật cũng vô nghĩa, vì cảnh báo chỉ được tạo ở ba mốc và
          mốc gần nhất đã cách hiện tại hơn một ngày, nên "1h" và "24h" sẽ luôn
          trả về rỗng.

          Thay bằng câu trả lời thật cho đúng câu hỏi mà bộ chọn ấy gợi ra:
          người dùng đang nhìn khoảng thời gian nào. */}
      {periodLabel && (
        <Badge
          tone="neutral"
          icon={false}
          className="hidden whitespace-nowrap sm:inline-flex"
          title="Toàn bộ số liệu trên console tính trên đúng khoảng thời gian này"
        >
          Dữ liệu {periodLabel}
        </Badge>
      )}

      <div
        title="Trạng thái luồng dữ liệu"
        className="hidden items-center gap-1.5 whitespace-nowrap text-meta text-ink-soft lg:flex"
      >
        <PulseDot />
        Đang hoạt động
      </div>

      <Popover
        open={bellOpen}
        onClose={() => setBellOpen(false)}
        align="right"
        width={288}
        trigger={
          <button
            type="button"
            onClick={() => setBellOpen((open) => !open)}
            aria-label={`Thông báo${criticalCount > 0 ? ` — ${criticalCount} cảnh báo nghiêm trọng` : ""}`}
            aria-expanded={bellOpen}
            className="relative grid h-8 w-8 place-items-center rounded-control text-ink-soft transition-colors hover:bg-elev hover:text-ink-hi"
          >
            <Bell size={17} strokeWidth={1.8} />
            {criticalCount > 0 && (
              <span
                className="absolute right-1.5 top-1.5 h-[7px] w-[7px] rounded-full border-[1.5px] border-side bg-risk"
                aria-hidden
              />
            )}
          </button>
        }
      >
        <div className={`${TEXT.eyebrow} mb-2`}>Thông báo nội bộ</div>
        <p className="text-meta leading-relaxed text-ink-mid">
          {criticalCount} cảnh báo đang ở mức nghiêm trọng{periodLabel ? ` trong kỳ dữ liệu ${periodLabel}` : ""}.
          Thông báo chỉ phát trong nội bộ — hệ thống không có kênh nào gửi tới chủ thể đang bị rà soát.
        </p>
      </Popover>

      <div
        title={`${currentUser?.name} · ${currentUser?.roleLabel}`}
        className="grid h-[30px] w-[30px] flex-none place-items-center rounded-full border border-line-strong bg-elev text-meta font-semibold text-ink-mid"
      >
        {initials}
      </div>
    </header>
  );
}
