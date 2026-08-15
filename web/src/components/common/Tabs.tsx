import { SegmentedControl, Tabs as UiTabs } from "../ui/Tabs";

/**
 * Lớp tương thích — tab thật nằm ở `components/ui/Tabs`.
 *
 * Biến thể `pill` được ánh xạ sang `SegmentedControl`: đó chính là thứ nó cố
 * làm, chỉ khác là bản mới có chỉ báo trượt thay vì mỗi nút tự bật nền.
 *
 * @deprecated Import `Tabs` hoặc `SegmentedControl` từ `components/ui`.
 */
interface TabsProps {
  tabs: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
  variant?: "underline" | "pill";
}

export function Tabs({ tabs, active, onChange, variant = "underline" }: TabsProps) {
  if (variant === "pill") {
    return (
      <SegmentedControl
        label="Chế độ xem"
        size="sm"
        value={active}
        onChange={onChange}
        options={tabs.map((tab) => ({ value: tab.id, label: tab.label }))}
      />
    );
  }
  return <UiTabs tabs={tabs} active={active} onChange={onChange} />;
}
