import { Search, X } from 'lucide-react';
import { Select } from './ui/Input.jsx';

/** Search box + filter selects shown above every list. */
export default function ListToolbar({ list, placeholder = 'Search', filters = [], children }) {
  return (
    <div className="flex flex-col gap-3 border-b border-slate-100 p-4 lg:flex-row lg:items-center">
      <div className="relative flex-1">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          type="search"
          value={list.filters.search}
          onChange={(e) => list.setFilter('search', e.target.value)}
          placeholder={placeholder}
          aria-label={placeholder}
          className="h-10 w-full rounded-lg border border-slate-200 pl-9 pr-3 text-sm placeholder:text-slate-400 focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-100"
        />
      </div>
      {filters.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:flex sm:flex-wrap">
          {filters.map((f) => (
            <Select
              key={f.key}
              aria-label={f.label}
              value={list.filters[f.key] ?? ''}
              onChange={(e) => list.setFilter(f.key, e.target.value)}
              className="sm:w-44"
            >
              <option value="">{f.label}</option>
              {f.options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          ))}
        </div>
      )}
      {children}
      {list.hasFilters && (
        <button
          type="button"
          onClick={list.resetFilters}
          className="inline-flex items-center gap-1 self-start rounded-md px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-700 lg:self-center"
        >
          <X className="h-3.5 w-3.5" /> Clear
        </button>
      )}
    </div>
  );
}

export const toOptions = (values, labeler = (v) => v) => values.map((v) => ({ value: v, label: labeler(v) }));
