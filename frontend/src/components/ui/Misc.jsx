import { AlertCircle } from 'lucide-react';
import Card from './Card.jsx';
import { Skeleton } from './States.jsx';

export function FormError({ message }) {
  if (!message) return null;
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-700">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

export function StatCard({ icon: Icon, label, value, sub, tone = 'navy', loading }) {
  const tones = {
    navy: 'bg-navy-50 text-navy-700',
    green: 'bg-emerald-50 text-emerald-700',
    amber: 'bg-amber-50 text-amber-700',
    rose: 'bg-rose-50 text-rose-700',
    slate: 'bg-slate-100 text-slate-600',
  };
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-slate-500">{label}</p>
        {Icon && (
          <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${tones[tone]}`}>
            <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
          </span>
        )}
      </div>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-24" />
      ) : (
        <p className="mt-1 text-2xl font-semibold tracking-tight text-slate-900 tabular-nums">{value}</p>
      )}
      {sub && <p className="mt-1 text-xs text-slate-500">{loading ? ' ' : sub}</p>}
    </Card>
  );
}

export function OccupancyBar({ occupied, capacity, showLabel = true }) {
  const pct = capacity ? Math.min(100, Math.round((occupied / capacity) * 100)) : 0;
  const color = pct >= 100 ? 'bg-rose-500' : pct > 0 ? 'bg-amber-500' : 'bg-emerald-500';
  return (
    <div className="flex items-center gap-2">
      <div
        className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-100"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={capacity}
        aria-valuenow={occupied}
        aria-label={`${occupied} of ${capacity} beds occupied`}
      >
        <div className={`h-full ${color}`} style={{ width: `${Math.max(pct, occupied ? 8 : 0)}%` }} />
      </div>
      {showLabel && (
        <span className="text-xs tabular-nums text-slate-600">
          {occupied}/{capacity}
        </span>
      )}
    </div>
  );
}

export function DetailList({ items }) {
  return (
    <dl className="divide-y divide-slate-100">
      {items.map(([term, value]) => (
        <div key={term} className="flex justify-between gap-4 py-2.5">
          <dt className="text-sm text-slate-500">{term}</dt>
          <dd className="text-right text-sm font-medium text-slate-800">{value ?? '—'}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-slate-200" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={active === t.key}
          onClick={() => onChange(t.key)}
          className={`-mb-px whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
            active === t.key
              ? 'border-navy-700 text-navy-800'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          {t.label}
          {t.count != null && <span className="ml-1.5 rounded-full bg-slate-100 px-1.5 text-xs text-slate-600">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}
