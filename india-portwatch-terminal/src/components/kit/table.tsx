/**
 * The operational table.
 *
 * Dense by default (24px rows), sticky header, sortable columns, selectable
 * rows, and it scrolls inside its own box so a wide table never pushes the page
 * sideways at 1366px. One component so every list on every screen behaves the
 * same way.
 */

import { useMemo, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface Column<T> {
  key: string;
  header: string;
  align?: "left" | "right" | "center";
  /** Fixed pixel width; omit to let the column take remaining space. */
  width?: number;
  /** Returning null sorts the row to the bottom in either direction. */
  sort?: (row: T) => number | string | null;
  render: (row: T) => ReactNode;
  hint?: string;
}

type Direction = "asc" | "desc";

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  onRowClick,
  selectedKey,
  emptyLabel = "No rows in this artefact",
  initialSort,
  initialDirection = "desc",
  className,
  rowTone,
}: {
  rows: T[];
  columns: Array<Column<T>>;
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  selectedKey?: string | null;
  emptyLabel?: string;
  initialSort?: string;
  initialDirection?: Direction;
  className?: string;
  /** Optional 3px status stripe on the row's leading edge. */
  rowTone?: (row: T) => string | null;
}) {
  const [sortKey, setSortKey] = useState<string | null>(initialSort ?? null);
  const [direction, setDirection] = useState<Direction>(initialDirection);

  const sorted = useMemo(() => {
    const column = columns.find((c) => c.key === sortKey && c.sort);
    if (!column?.sort) return rows;
    const factor = direction === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = column.sort!(a);
      const bv = column.sort!(b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * factor;
      return String(av).localeCompare(String(bv)) * factor;
    });
  }, [columns, direction, rows, sortKey]);

  const toggle = (column: Column<T>) => {
    if (!column.sort) return;
    if (sortKey === column.key) {
      setDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(column.key);
      setDirection("desc");
    }
  };

  return (
    <div className={cn("h-full min-h-0 overflow-auto", className)}>
      <table className="data-grid">
        <colgroup>
          {rows.length > 0 && rowTone ? <col style={{ width: 3 }} /> : null}
          {columns.map((column) => (
            <col key={column.key} style={column.width ? { width: column.width } : undefined} />
          ))}
        </colgroup>
        <thead className="sticky top-0 z-10">
          <tr>
            {rows.length > 0 && rowTone ? (
              <th className="border-b border-[var(--line)] bg-[var(--panel-2)] p-0" />
            ) : null}
            {columns.map((column) => {
              const active = sortKey === column.key;
              return (
                <th
                  key={column.key}
                  title={column.hint}
                  scope="col"
                  aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : undefined}
                  className={cn(
                    "whitespace-nowrap border-b border-[var(--line)] bg-[var(--panel-2)] px-2.5 py-[6px]",
                    "text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-3)]",
                    column.align === "right" && "text-right",
                    column.align === "center" && "text-center",
                    column.sort && "cursor-pointer select-none hover:text-[var(--text-2)]",
                  )}
                  onClick={() => toggle(column)}
                >
                  <span className="inline-flex items-center gap-1">
                    {column.header}
                    {column.sort ? (
                      <span
                        className={cn(
                          "text-[8px] leading-none transition-opacity",
                          active ? "text-[var(--info)] opacity-100" : "opacity-25",
                        )}
                        aria-hidden
                      >
                        {active && direction === "asc" ? "▲" : "▼"}
                      </span>
                    ) : null}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length + (rowTone ? 1 : 0)}
                className="px-3 py-8 text-center text-[12px] text-[var(--text-3)]"
              >
                {emptyLabel}
              </td>
            </tr>
          ) : (
            sorted.map((row) => {
              const key = rowKey(row);
              const selected = selectedKey === key;
              const tone = rowTone?.(row) ?? null;
              return (
                <tr
                  key={key}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={cn(
                    "border-b border-[var(--line)]/45 transition-colors",
                    onRowClick && "cursor-pointer",
                    selected
                      ? "bg-[color-mix(in_srgb,var(--info)_12%,transparent)]"
                      : "hover:bg-[var(--panel-2)]",
                  )}
                >
                  {rowTone ? (
                    <td className="p-0">
                      <span
                        className="block h-full w-[3px]"
                        style={{ background: tone ?? "transparent", minHeight: 24 }}
                      />
                    </td>
                  ) : null}
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={cn(
                        "whitespace-nowrap px-2.5 py-[5px] text-[12px] text-[var(--text-2)]",
                        column.align === "right" && "text-right",
                        column.align === "center" && "text-center",
                      )}
                    >
                      {column.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

/** Filter box used above tables. */
export function SearchInput({
  value,
  onChange,
  placeholder = "Filter",
  className,
}: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-1.5 rounded-[2px] border border-[var(--line-strong)] bg-[var(--panel-2)] px-2",
        className,
      )}
    >
      <svg
        width="11"
        height="11"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        className="shrink-0 text-[var(--text-3)]"
        aria-hidden
      >
        <circle cx="7" cy="7" r="4.5" />
        <path d="M10.5 10.5L14 14" />
      </svg>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="min-w-0 flex-1 bg-transparent py-[4px] text-[12px] text-[var(--text)] outline-none placeholder:text-[var(--text-3)]"
      />
      {value ? (
        <button
          type="button"
          aria-label="Clear filter"
          onClick={() => onChange("")}
          className="shrink-0 text-[var(--text-3)] hover:text-[var(--text)]"
        >
          <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M4 4l8 8M12 4l-8 8" />
          </svg>
        </button>
      ) : null}
    </div>
  );
}
