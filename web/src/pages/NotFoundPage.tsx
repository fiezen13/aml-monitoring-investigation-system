import { Link } from "react-router-dom";

import { Button, PageShell, Panel } from "../components/ui";

export function NotFoundPage() {
  return (
    <PageShell
      title="Không tìm thấy trang"
      subtitle="Đường dẫn này không tồn tại hoặc đã được thay đổi."
    >
      <Panel>
        <div className="flex flex-col items-start gap-3 py-5">
          <span className="font-mono text-h1 font-semibold text-primary">404</span>
          <p className="max-w-[56ch] text-body leading-relaxed text-ink-soft">
            Dữ liệu của bạn không bị thay đổi. Quay về trang tổng quan hoặc dùng thanh điều hướng để mở một chức năng khác.
          </p>
          <Link to="/dashboard">
            <Button>Về trang tổng quan</Button>
          </Link>
        </div>
      </Panel>
    </PageShell>
  );
}
