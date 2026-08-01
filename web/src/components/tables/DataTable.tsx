import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  className?: string;
  headerClassName?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  dense?: boolean;
}

/**
 * Bảng dữ liệu chuẩn: header uppercase nhỏ, hàng 40–44px,
 * hover highlight, cuộn ngang trong khối riêng khi hẹp.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  dense = false,
}: DataTableProps<T>) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-left">
        <thead>
          <tr className="border-b border-line">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`whitespace-nowrap px-3 py-2.5 text-2xs font-semibold uppercase tracking-wider text-ink-mid ${col.headerClassName ?? ""}`}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={`border-b border-line/60 transition-colors last:border-0 ${
                onRowClick ? "cursor-pointer hover:bg-elev/70" : ""
              }`}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`px-3 ${dense ? "py-2" : "py-2.5"} text-[13px] text-ink-hi ${col.className ?? ""}`}
                >
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
