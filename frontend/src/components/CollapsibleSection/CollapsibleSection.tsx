import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { ReactNode } from "react";

export function CollapsibleSection({
  id,
  title,
  collapsed,
  onToggleCollapse,
  headerExtra,
  children,
  className = "",
}: {
  id: string;
  title: ReactNode;
  collapsed: boolean;
  onToggleCollapse: () => void;
  headerExtra?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`bg-[var(--surface)] border border-[var(--border)] rounded flex flex-col ${className}`}
    >
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[var(--border)]">
        <button
          {...attributes}
          {...listeners}
          className="cursor-grab text-[var(--muted)] px-1"
          title="Drag to reorder"
        >
          ⠿
        </button>
        <button
          onClick={onToggleCollapse}
          className="text-[var(--muted)] hover:text-[var(--text)] px-1"
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? "▸" : "▾"}
        </button>
        <div className="flex-1 min-w-0 text-sm font-semibold text-[var(--text)] truncate">
          {title}
        </div>
        {headerExtra}
      </div>
      {!collapsed && <div className="p-3 flex flex-col gap-3">{children}</div>}
    </div>
  );
}
