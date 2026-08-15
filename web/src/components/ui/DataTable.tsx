import { ChevronDown, ChevronUp } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";
import type { ReactNode } from "react";

import { TEXT } from "../../design/typography";
import { rowVariants, safeVariants, useReduced } from "../../design/motion";
import { EmptyState, ErrorState, TableSkeleton } from "./States";

/**
 * Bảng dữ liệu.
 *
 * Một bảng cho cả console. Trước đây tồn tại hai cách: `<table>` qua
 * `tables/DataTable` ở nhóm trang này, và lưới CSS viết tay với
 * `gridTemplateColumns` hardcode ở nhóm trang kia — nên chiều cao hàng, cỡ chữ
 * header và màu hover khác nhau giữa hai nửa ứng dụng.
 *
 * Bảng nắm luôn cả bốn trạng thái (đang tải, lỗi, rỗng, có dữ liệu) thay vì để
 * mỗi trang tự dựng: chúng là một phần của bảng, và tách ra là cách chắc chắn
 * nhất để mỗi trang có một trạng thái rỗng khác nhau.
 */

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  /** Hàm lấy giá trị để sắp xếp; bỏ trống nghĩa là cột không sắp xếp được. */
  sortValue?: (row: T) => string | number;
  className?: string;
  headerClassName?: string;
  /** Cột số căn phải để chữ số thẳng cột. */
  numeric?: boolean;
}

interface Props<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  /** Khoá của hàng đang chọn — hàng được tô nền và giữ vạch teal ở mép trái. */
  selectedKey?: string | null;
  dense?: boolean;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyDetail?: string;
  /** Bề rộng tối thiểu trước khi bảng cuộn ngang trong khối của chính nó. */
  minWidth?: number;
  footer?: ReactNode;
  /** Hàng mới vào có loé nền theo mức rủi ro — dùng cho hàng đợi cảnh báo. */
  flashKeys?: Set<string>;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  selectedKey = null,
  dense = false,
  loading = false,
  error = null,
  onRetry,
  emptyTitle,
  emptyDetail,
  minWidth = 640,
  footer,
  flashKeys,
}: Props<T>) {
  const reduced = useReduced();
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" } | null>(null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const column = columns.find((c) => c.key === sort.key);
    if (!column?.sortValue) return rows;
    const factor = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = column.sortValue!(a);
      const bv = column.sortValue!(b);
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * factor;
      return String(av).localeCompare(String(bv), "vi") * factor;
    });
  }, [rows, sort, columns]);

  if (loading) return <TableSkeleton rows={6} />;
  if (error) return <ErrorState detail={error} onRetry={onRetry} />;
  if (!rows.length) return <EmptyState title={emptyTitle} detail={emptyDetail} />;

  return (
    <div className="min-w-0">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left" style={{ minWidth }}>
          <thead>
            <tr className="border-b border-line">
              {columns.map((column) => {
                const sortable = Boolean(column.sortValue);
                const isSorted = sort?.key === column.key;
                return (
                  <th
                    key={column.key}
                    aria-sort={isSorted ? (sort!.dir === "asc" ? "ascending" : "descending") : undefined}
                    className={`whitespace-nowrap px-3 py-2 ${TEXT.columnLabel} ${
                      column.numeric ? "text-right" : ""
                    } ${column.headerClassName ?? ""}`}
                  >
                    {sortable ? (
                      <button
                        type="button"
                        onClick={() =>
                          setSort((current) =>
                            current?.key === column.key
                              ? { key: column.key, dir: current.dir === "asc" ? "desc" : "asc" }
                              : { key: column.key, dir: "desc" },
                          )
                        }
                        className={`inline-flex items-center gap-1 transition-colors hover:text-ink-hi ${
                          column.numeric ? "flex-row-reverse" : ""
                        }`}
                      >
                        {column.header}
                        {isSorted &&
                          (sort!.dir === "asc" ? (
                            <ChevronUp size={11} aria-hidden />
                          ) : (
                            <ChevronDown size={11} aria-hidden />
                          ))}
                      </button>
                    ) : (
                      column.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            <AnimatePresence initial={false}>
              {sorted.map((row) => {
                const key = rowKey(row);
                const selected = selectedKey === key;
                return (
                  <motion.tr
                    key={key}
                    layout={reduced ? false : "position"}
                    variants={safeVariants(rowVariants, reduced)}
                    initial="initial"
                    animate="animate"
                    exit="exit"
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    className={`border-b border-line-faint transition-colors last:border-0 ${
                      onRowClick ? "cursor-pointer hover:bg-elev/70" : ""
                    } ${selected ? "bg-primary-soft" : ""} ${
                      flashKeys?.has(key) && !reduced ? "animate-flash" : ""
                    }`}
                  >
                    {columns.map((column, index) => (
                      <td
                        key={column.key}
                        className={`relative px-3 ${dense ? "py-1.5" : "py-2"} text-body text-ink-hi ${
                          column.numeric ? "tabular text-right font-mono" : ""
                        } ${column.className ?? ""}`}
                      >
                        {/* Vạch teal mép trái thay cho tô đậm cả hàng: hàng đang
                            chọn phải định vị được mà không làm mất tương phản
                            của chữ bên trong. */}
                        {selected && index === 0 && (
                          <span className="absolute inset-y-0 left-0 w-0.5 bg-primary" aria-hidden />
                        )}
                        {column.render(row)}
                      </td>
                    ))}
                  </motion.tr>
                );
              })}
            </AnimatePresence>
          </tbody>
        </table>
      </div>
      {footer && <div className="border-t border-line px-3 py-2 text-meta text-ink-low">{footer}</div>}
    </div>
  );
}
