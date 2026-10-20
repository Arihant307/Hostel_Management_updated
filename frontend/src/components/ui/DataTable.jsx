import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { EmptyState, ErrorState, Skeleton } from './States.jsx';

/**
 * Server-driven table. Sorting and pagination are controlled by the parent
 * (which passes them to the API), so it scales to large data sets.
 *
 * columns: [{ key, header, sortable?, render?(row), className? }]
 */
export default function DataTable({
  columns,
  rows,
  loading,
  error,
  onRetry,
  sort,
  onSortChange,
  pagination,
  onPageChange,
  empty,
  rowKey = (row) => row.id,
}) {
  const toggleSort = (key) => {
    if (!onSortChange) return;
    const order = sort?.key === key && sort.order === 'asc' ? 'desc' : 'asc';
    onSortChange({ key, order });
  };

  let body;
  if (error) {
    body = (
      <tr>
        <td colSpan={columns.length}>
          <ErrorState message={error} onRetry={onRetry} />
        </td>
      </tr>
    );
  } else if (loading && !rows?.length) {
    body = Array.from({ length: 5 }, (_, i) => (
      <tr key={i}>
        {columns.map((c) => (
          <td key={c.key} className="px-4 py-4">
            <Skeleton className="h-4 w-3/4" />
          </td>
        ))}
      </tr>
    ));
  } else if (!rows?.length) {
    body = (
      <tr>
        <td colSpan={columns.length}>{empty}</td>
      </tr>
    );
  } else {
    body = rows.map((row) => (
      <tr key={rowKey(row)} className="transition-colors hover:bg-slate-50/70">
        {columns.map((c) => (
          <td key={c.key} className={`px-4 py-3 text-sm text-slate-700 ${c.className ?? ''}`}>
            {c.render ? c.render(row) : row[c.key]}
          </td>
        ))}
      </tr>
    ));
  }

  return (
    <div>
      <div className={`relative overflow-x-auto ${loading && rows?.length ? 'opacity-60' : ''}`}>
        <table className="min-w-full divide-y divide-slate-100">
          <thead className="bg-surface-muted">
            <tr>
              {columns.map((c) => {
                const active = sort?.key === c.key;
                const SortIcon = !active ? ArrowUpDown : sort.order === 'asc' ? ArrowUp : ArrowDown;
                return (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={active ? (sort.order === 'asc' ? 'ascending' : 'descending') : undefined}
                    className={`whitespace-nowrap px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 ${c.className ?? ''}`}
                  >
                    {c.sortable ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(c.key)}
                        className="inline-flex items-center gap-1 uppercase hover:text-slate-800"
                      >
                        {c.header}
                        <SortIcon className={`h-3.5 w-3.5 ${active ? 'text-navy-600' : 'text-slate-300'}`} />
                      </button>
                    ) : (
                      c.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">{body}</tbody>
        </table>
      </div>
      {pagination && pagination.total > 0 && (
        <Pagination pagination={pagination} onPageChange={onPageChange} />
      )}
    </div>
  );
}

export function Pagination({ pagination, onPageChange }) {
  const { page, per_page: perPage, total, pages } = pagination;
  const from = (page - 1) * perPage + 1;
  const to = Math.min(page * perPage, total);
  return (
    <div className="flex items-center justify-between gap-4 border-t border-slate-100 px-4 py-3">
      <p className="text-xs text-slate-500">
        Showing <span className="font-medium text-slate-700">{from}</span>–
        <span className="font-medium text-slate-700">{to}</span> of{' '}
        <span className="font-medium text-slate-700">{total}</span>
      </p>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="px-2 text-xs text-slate-600">
          Page {page} of {Math.max(pages, 1)}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pages}
          className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Next page"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
