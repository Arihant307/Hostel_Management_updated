import { useEffect, useId, useState } from 'react';
import { Search, X } from 'lucide-react';
import useDebounce from '../hooks/useDebounce.js';
import { studentService } from '../services/resources.js';
import { Field } from './ui/Input.jsx';

/** Searchable student picker (combobox) backed by /api/students. */
export default function StudentSelect({ label = 'Student', value, onChange, error, required, params = {} }) {
  const id = useId();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState([]);
  const debounced = useDebounce(query, 250);
  const paramKey = JSON.stringify(params);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    studentService.list({ search: debounced, per_page: 8, sort: 'name', ...JSON.parse(paramKey) })
      .then((d) => !cancelled && setResults(d.items))
      .catch(() => !cancelled && setResults([]));
    return () => { cancelled = true; };
  }, [debounced, open, paramKey]);

  if (value) {
    return (
      <Field id={id} label={label} required={required} error={error}>
        <div className="flex h-10 items-center justify-between rounded-lg border border-slate-200 bg-surface-muted px-3 text-sm">
          <span className="truncate">
            <span className="font-medium text-slate-800">{value.full_name}</span>
            <span className="ml-2 text-slate-500">{value.student_code}</span>
          </span>
          <button type="button" onClick={() => onChange(null)} className="rounded p-0.5 text-slate-400 hover:text-slate-600" aria-label="Clear student">
            <X className="h-4 w-4" />
          </button>
        </div>
      </Field>
    );
  }

  return (
    <Field id={id} label={label} required={required} error={error}>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          placeholder="Search by name or student ID"
          className={`h-10 w-full rounded-lg border bg-white pl-9 pr-3 text-sm focus:outline-none focus:ring-2 ${error ? 'border-rose-300 focus:ring-rose-100' : 'border-slate-200 focus:border-navy-400 focus:ring-navy-100'}`}
        />
        {open && (
          <ul id={`${id}-list`} role="listbox" className="absolute z-10 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-slate-200 bg-white py-1 shadow-raised">
            {results.length === 0 && <li className="px-3 py-2 text-sm text-slate-500">No students found.</li>}
            {results.map((s) => (
              <li key={s.id} role="option" aria-selected="false">
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => { onChange(s); setQuery(''); setOpen(false); }}
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                >
                  <span className="font-medium text-slate-800">{s.full_name}</span>
                  <span className="ml-2 text-xs text-slate-500">{s.student_code}</span>
                  {s.current_allocation && (
                    <span className="ml-2 text-xs text-slate-400">Room {s.current_allocation.room.block}-{s.current_allocation.room.room_number}</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Field>
  );
}
