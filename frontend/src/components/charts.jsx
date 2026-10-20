import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { formatMoney } from '../utils/format.js';

// Chart tokens: one navy hue for single-series magnitude; neutral gray for "remainder".
const NAVY = '#253c76';
const REMAINDER = '#cbd5e1';
const GRID = '#eef0f3';
const AXIS = { fontSize: 12, fill: '#64748b' };

function ChartTooltip({ active, payload, label, formatter }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-raised">
      <p className="mb-1 font-medium text-slate-800">{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="flex items-center gap-2 text-slate-600">
          <span className="h-2 w-2 rounded-sm" style={{ background: p.color }} aria-hidden="true" />
          {p.name}: <span className="font-medium tabular-nums text-slate-900">{formatter ? formatter(p.value, p) : p.value}</span>
        </p>
      ))}
    </div>
  );
}

const compactMoney = (minor) => {
  const rupees = (minor ?? 0) / 100;
  if (rupees >= 100000) return `₹${(rupees / 100000).toFixed(1)}L`;
  if (rupees >= 1000) return `₹${+(rupees / 1000).toFixed(rupees % 1000 ? 1 : 0)}k`;
  return `₹${rupees}`;
};

/** Monthly collected payments (single series). */
export function PaymentTrendChart({ data, height = 260 }) {
  return (
    <div style={{ height }} role="img" aria-label="Bar chart of payments collected per month">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap="28%">
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false}
            tickFormatter={(v) => v.split(' ')[0]} interval="preserveStartEnd" minTickGap={8} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={56} tickFormatter={compactMoney}
            allowDecimals={false} domain={[0, (max) => Math.max(max, 100000)]} />
          <Tooltip cursor={{ fill: 'rgba(37,60,118,0.06)' }}
            content={<ChartTooltip formatter={(v, p) => `${formatMoney(v)} (${p.payload.count} payments)`} />} />
          <Bar dataKey="amount_minor" name="Collected" fill={NAVY} radius={[4, 4, 0, 0]} maxBarSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Occupied vs free beds per block (stacked: navy = occupied, gray = remainder). */
export function OccupancyChart({ data, height = 260 }) {
  return (
    <div style={{ height }} role="img" aria-label="Stacked bar chart of occupied and free beds per block">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data.map((d) => ({ ...d, name: `Block ${d.block}` }))}
          margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap="32%">
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="name" tick={AXIS} tickLine={false} axisLine={false} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} width={32} />
          <Tooltip cursor={{ fill: 'rgba(37,60,118,0.06)' }} content={<ChartTooltip formatter={(v) => `${v} beds`} />} />
          <Legend iconType="square" iconSize={10} wrapperStyle={{ fontSize: 12, color: '#475569' }} />
          <Bar dataKey="occupied" name="Occupied" stackId="beds" fill={NAVY} stroke="#fff" strokeWidth={2} maxBarSize={44} />
          <Bar dataKey="available" name="Free" stackId="beds" fill={REMAINDER} stroke="#fff" strokeWidth={2} radius={[4, 4, 0, 0]} maxBarSize={44} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Horizontal bars, single series (e.g. complaints by category). */
export function HorizontalBarChart({ data, dataKey, nameKey, name, height = 240, formatter }) {
  return (
    <div style={{ height }} role="img" aria-label={`Bar chart of ${name.toLowerCase()}`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, left: 8, bottom: 0 }} barCategoryGap="30%">
          <CartesianGrid horizontal={false} stroke={GRID} />
          <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
          <YAxis type="category" dataKey={nameKey} tick={AXIS} tickLine={false} axisLine={false} width={96} />
          <Tooltip cursor={{ fill: 'rgba(37,60,118,0.06)' }} content={<ChartTooltip formatter={formatter} />} />
          <Bar dataKey={dataKey} name={name} fill={NAVY} radius={[0, 4, 4, 0]} maxBarSize={18} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
