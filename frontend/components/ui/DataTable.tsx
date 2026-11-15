"use client";

import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react";
import { useCallback, useMemo, useState, type ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  sortable?: boolean;
  sortValue?: (row: T) => string | number;
  align?: "left" | "right" | "center";
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[] | null;
  keyFn: (row: T) => string;
  emptyMessage?: string;
  /** Sticky first column on mobile scroll. */
  stickyFirst?: boolean;
  onRowClick?: (row: T) => void;
}

type SortDir = "asc" | "desc";

export function DataTable<T>({
  columns,
  data,
  keyFn,
  emptyMessage = "No records found.",
  stickyFirst,
  onRowClick,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const toggleSort = useCallback(
    (key: string) => {
      if (sortKey === key) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortKey(key);
        setSortDir("asc");
      }
    },
    [sortKey]
  );

  const sorted = useMemo(() => {
    if (!data || !sortKey) return data;
    const col = columns.find((c) => c.key === sortKey);
    if (!col?.sortValue) return data;
    const fn = col.sortValue;
    return [...data].sort((a, b) => {
      const va = fn(a);
      const vb = fn(b);
      const cmp = va < vb ? -1 : va > vb ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [data, sortKey, sortDir, columns]);

  if (data === null) {
    return (
      <div className="space-y-3 py-4">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-10 animate-pulse rounded-lg bg-surface-elevated" />
        ))}
      </div>
    );
  }

  if (data.length === 0) {
    return <p className="py-8 text-center text-sm text-ink-soft">{emptyMessage}</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-surface-muted/50">
            {columns.map((col, i) => {
              const align = col.align ?? "left";
              return (
                <th
                  key={col.key}
                  className={`whitespace-nowrap px-4 py-3 font-medium text-ink-soft ${
                    align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left"
                  } ${stickyFirst && i === 0 ? "sticky left-0 z-10 bg-surface-muted/50" : ""} ${col.className ?? ""}`}
                >
                  {col.sortable ? (
                    <button
                      className="inline-flex items-center gap-1 hover:text-ink"
                      onClick={() => toggleSort(col.key)}
                    >
                      {col.header}
                      {sortKey === col.key ? (
                        sortDir === "asc" ? (
                          <ChevronUp className="h-3.5 w-3.5" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5" />
                        )
                      ) : (
                        <ChevronsUpDown className="h-3.5 w-3.5 opacity-40" />
                      )}
                    </button>
                  ) : (
                    col.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {(sorted ?? data).map((row) => (
            <tr
              key={keyFn(row)}
              className={`border-b border-border last:border-0 transition-colors ${
                onRowClick ? "cursor-pointer hover:bg-surface-elevated/50" : ""
              }`}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((col, i) => {
                const align = col.align ?? "left";
                return (
                  <td
                    key={col.key}
                    className={`px-4 py-3 text-ink ${
                      align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left"
                    } ${stickyFirst && i === 0 ? "sticky left-0 z-10 bg-surface" : ""} ${col.className ?? ""}`}
                  >
                    {col.render(row)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
