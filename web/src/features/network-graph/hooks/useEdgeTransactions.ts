import { useCallback, useEffect, useRef, useState } from "react";

import { api, type FcTxPage, type FcTxRow } from "../../../api/client";

export type TxScope =
  | { kind: "edge"; id: string }
  | { kind: "node"; id: string }
  | { kind: "none" };

interface State {
  rows: FcTxRow[];
  total: number;
  page: number;
  pageSize: number;
  loading: boolean;
  error: string | null;
}

const EMPTY: State = { rows: [], total: 0, page: 1, pageSize: 25, loading: false, error: null };

/**
 * Tải giao dịch thật của thứ đang chọn trên đồ thị.
 *
 * Chỉ gọi API khi analyst đã chọn một cạnh hoặc một đỉnh. Đây là điểm mấu chốt
 * của kiến trúc: đồ thị chở *quan hệ* và bốn con số tóm tắt, còn danh sách sự
 * kiện chỉ được kéo về khi có người hỏi tới. Nhét sẵn giao dịch vào phản hồi đồ
 * thị sẽ biến một màn hình 60 cạnh thành vài MB JSON mà gần như không ai mở.
 *
 * Mỗi lần đổi phạm vi hoặc trang sẽ huỷ kết quả của lần gọi trước bằng một
 * token tăng dần — không có nó thì phản hồi chậm của lựa chọn cũ có thể về sau
 * và ghi đè lên danh sách của lựa chọn mới.
 */
export function useEdgeTransactions(scope: TxScope, pageSize = 25) {
  const [state, setState] = useState<State>(EMPTY);
  const [page, setPage] = useState(1);
  const seq = useRef(0);

  const key = scope.kind === "none" ? "none" : `${scope.kind}:${scope.id}`;

  // Đổi phạm vi thì quay về trang 1; giữ nguyên trang cũ sẽ hiện "trang 4 của 1".
  useEffect(() => {
    setPage(1);
  }, [key]);

  const load = useCallback(
    async (targetPage: number) => {
      if (scope.kind === "none") {
        setState(EMPTY);
        return;
      }
      const token = ++seq.current;
      setState((s) => ({ ...s, loading: true, error: null }));
      try {
        const res: FcTxPage =
          scope.kind === "edge"
            ? await api.graphEdgeTransactions(scope.id, { page: targetPage, page_size: pageSize })
            : await api.graphNodeTransactions(scope.id, { page: targetPage, page_size: pageSize });
        if (token !== seq.current) return;
        setState({
          rows: res.rows,
          total: res.total,
          page: res.page,
          pageSize: res.pageSize,
          loading: false,
          error: null,
        });
      } catch (cause) {
        if (token !== seq.current) return;
        setState({
          ...EMPTY,
          error: cause instanceof Error ? cause.message : "Không tải được giao dịch",
        });
      }
    },
    // `scope.kind`/`scope.id` gộp trong `key`; dùng key để không tạo lại hàm
    // mỗi lần component cha render ra một object scope mới cùng nội dung.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key, pageSize],
  );

  useEffect(() => {
    void load(page);
  }, [load, page]);

  return { ...state, setPage, reload: () => void load(page) };
}
