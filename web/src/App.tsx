import { useCallback, useEffect, useState } from "react";

import {
  type Case,
  type CaseDetail,
  type QueueStats,
  getCase,
  getQueueStats,
  investigate,
  listCases,
} from "./api";

/**
 * Khung màn hình AML Console.
 *
 * Đây là bộ khung hạ tầng: đủ để chứng minh chuỗi web → API → PostgreSQL →
 * Redis → worker chạy thông. Thiết kế giao diện chi tiết nằm ở wireframe của
 * epic E09 và do Hưng hiện thực.
 *
 * Một điểm đã cố tình làm đúng ngay từ khung: điểm rủi ro không bao giờ hiển
 * thị một mình. Mọi chỗ hiện điểm đều hiện kèm các yếu tố đóng góp (NT7).
 */
export default function App() {
  const [cases, setCases] = useState<Case[]>([]);
  const [selected, setSelected] = useState<CaseDetail | null>(null);
  const [queue, setQueue] = useState<QueueStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [rows, stats] = await Promise.all([listCases(), getQueueStats()]);
      setCases(rows);
      setQueue(stats);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 10_000);
    return () => clearInterval(timer);
  }, [refresh]);

  const open = async (caseId: string) => {
    try {
      setSelected(await getCase(caseId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const startInvestigation = async (caseId: string) => {
    setBusy(true);
    try {
      await investigate(caseId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app">
      <header>
        <h1>FIN-07 · AML Console</h1>
        <div className="status">
          {queue && (
            <>
              <span className={queue.worker_alive ? "pill ok" : "pill bad"}>
                worker {queue.worker_alive ? "đang chạy" : "không phản hồi"}
              </span>
              <span className="pill">hàng đợi: {queue.depth}</span>
            </>
          )}
        </div>
      </header>

      {error && <p className="error">Lỗi: {error}</p>}

      <main>
        <section className="queue">
          <h2>Hàng đợi vụ việc ({cases.length})</h2>
          <table>
            <thead>
              <tr>
                <th>Mã</th>
                <th>Chủ thể</th>
                <th>Trạng thái</th>
                <th>Điểm</th>
                <th>Cảnh báo</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {cases.map((row) => (
                <tr key={row.case_id} className={selected?.case_id === row.case_id ? "active" : ""}>
                  <td>
                    <button className="link" onClick={() => void open(row.case_id)}>
                      {row.case_id}
                    </button>
                  </td>
                  <td className="mono">{row.subject_account_key}</td>
                  <td>{row.state}</td>
                  <td className={`score ${row.priority}`}>{Number(row.risk_score).toFixed(1)}</td>
                  <td>{row.alert_count}</td>
                  <td>
                    <button disabled={busy} onClick={() => void startInvestigation(row.case_id)}>
                      Điều tra
                    </button>
                  </td>
                </tr>
              ))}
              {cases.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty">
                    Chưa có vụ việc nào. Chạy <code>make seed</code> để nạp dữ liệu mẫu.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </section>

        <section className="detail">
          {selected ? (
            <>
              <h2>{selected.title}</h2>
              <dl>
                <dt>Trạng thái</dt>
                <dd>{selected.state}</dd>
                <dt>Chủ thể</dt>
                <dd className="mono">{selected.subject_account_key}</dd>
                <dt>Bằng chứng đã thu thập</dt>
                <dd>{selected.evidence_count}</dd>
              </dl>

              <h3>Yếu tố đóng góp vào điểm rủi ro</h3>
              <table>
                <thead>
                  <tr>
                    <th>Yếu tố</th>
                    <th>Nguồn</th>
                    <th>Typology</th>
                    <th>Đóng góp</th>
                    <th>Trọng số</th>
                  </tr>
                </thead>
                <tbody>
                  {selected.reasons.map((reason, index) => (
                    <tr key={`${reason.detector}-${reason.factor_code}-${index}`}>
                      <td>{reason.factor_label}</td>
                      <td>{reason.detector}</td>
                      <td>{reason.typology_code}</td>
                      <td>{Number(reason.contribution).toFixed(2)}</td>
                      <td>{Number(reason.weight).toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <p className="empty">Chọn một vụ việc để xem chi tiết.</p>
          )}
        </section>
      </main>
    </div>
  );
}
