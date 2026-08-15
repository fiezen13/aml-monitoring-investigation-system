import { animate, useMotionValue } from "motion/react";
import { useEffect, useState } from "react";

import { duration, easing } from "../../design/tokens";
import { useReduced } from "../../design/motion";

/**
 * Số liệu chuyển từ giá trị cũ sang giá trị mới.
 *
 * Cố ý KHÔNG đếm từ 0 lên: đây là bảng giám sát, không phải trang giới thiệu.
 * Đếm từ 0 mỗi khi cửa sổ thời gian đổi sẽ nói dối người xem trong nửa giây —
 * họ thấy "12" trên đường tới "1.204". Lần dựng đầu tiên hiện thẳng giá trị
 * thật; chỉ các lần đổi sau mới nội suy, và đó chính là lúc chuyển động mang
 * thông tin: nó cho biết con số vừa thay đổi và theo hướng nào.
 */

interface Props {
  value: number;
  /** Định dạng cuối cùng — nhận số đã nội suy, trả chuỗi hiển thị. */
  format?: (value: number) => string;
}

const defaultFormat = (value: number) => Math.round(value).toLocaleString("vi-VN");

export function AnimatedNumber({ value, format = defaultFormat }: Props) {
  const reduced = useReduced();
  const motionValue = useMotionValue(value);
  const [display, setDisplay] = useState(() => format(value));

  useEffect(() => {
    if (reduced || motionValue.get() === value) {
      motionValue.set(value);
      setDisplay(format(value));
      return;
    }
    const controls = animate(motionValue, value, {
      duration: duration.slow,
      ease: easing.standard as unknown as [number, number, number, number],
      onUpdate: (current) => setDisplay(format(current)),
    });
    return () => controls.stop();
    // `format` cố ý không nằm trong deps: chỗ dùng thường truyền hàm inline, và
    // đưa nó vào sẽ khởi động lại animation ở mỗi lần render cha.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, reduced]);

  return <>{display}</>;
}
