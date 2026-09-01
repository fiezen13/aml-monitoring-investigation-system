import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  onForgot: () => void;
}

export function PasswordField({ value, onChange, disabled, onForgot }: Props) {
  const [visible, setVisible] = useState(false);

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <label htmlFor="password" className="text-2xs font-medium text-ink-mid">
          Mật khẩu
        </label>
        <button
          type="button"
          onClick={onForgot}
          className="rounded text-2xs text-ink-low transition-colors hover:text-ink-hi"
        >
          Quên mật khẩu?
        </button>
      </div>

      <div className="relative">
        <input
          id="password"
          name="password"
          type={visible ? "text" : "password"}
          autoComplete="current-password"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className="h-11 w-full rounded-control border border-line-strong bg-sunken pl-3 pr-10 text-md text-ink-hi outline-none transition-[border-color,box-shadow] placeholder:text-ink-dim hover:border-line-emphasis focus:border-primary/60 focus:shadow-[0_0_0_3px_rgba(32,199,167,0.14)] disabled:opacity-60"
        />
        <button
          type="button"
          // Mật khẩu đang hiện là một trạng thái, không phải một nhãn tĩnh —
          // trình đọc màn hình cần biết bấm vào sẽ ra gì.
          aria-label={visible ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
          aria-pressed={visible}
          onClick={() => setVisible((v) => !v)}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1 text-ink-low transition-colors hover:text-ink-hi"
        >
          {visible ? <EyeOff size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
        </button>
      </div>
    </div>
  );
}
