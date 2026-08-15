/**
 * Design System V2 của F7 Console.
 *
 * Đây là bộ component duy nhất được phép dùng cho code mới. Hai bộ cũ —
 * `components/fc/` và `components/common/` — đang được migrate về đây; xem
 * ghi chú trong từng file của chúng để biết cái nào đã có bản thay thế.
 */

export { PageShell, type PageVariant } from "./PageShell";
export { Panel, Eyebrow, SectionHeader, Divider } from "./Panel";
export { Badge, PulseDot, ProgressBar } from "./Badge";
export { RiskIndicator } from "./RiskIndicator";
export { MetricCard, StatTile } from "./MetricCard";
export { AnimatedNumber } from "./AnimatedNumber";
export { Button, IconButton } from "./Button";
export { Tabs, SegmentedControl } from "./Tabs";
export { Input, Select, SearchInput, Checkbox, Switch, Label } from "./Field";
export { DataTable, type Column } from "./DataTable";
export { EmptyState, ErrorState, LoadingState, TableSkeleton, CardSkeleton } from "./States";
export { Popover, Tooltip, Drawer, Modal, Inspector, useDismiss } from "./Overlay";
export { Toolbar, ToolbarGroup } from "./Toolbar";
