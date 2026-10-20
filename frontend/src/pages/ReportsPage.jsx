import { useCallback, useEffect, useState } from 'react';
import { Download, FileSpreadsheet, History } from 'lucide-react';
import { useToast } from '../features/toast/ToastContext.jsx';
import { reportService } from '../services/resources.js';
import { getErrorMessage } from '../services/api.js';
import usePaginatedList from '../hooks/usePaginatedList.js';
import PageHeader from '../components/PageHeader.jsx';
import ListToolbar from '../components/ListToolbar.jsx';
import { label } from '../components/StatusBadge.jsx';
import Card from '../components/ui/Card.jsx';
import Button from '../components/ui/Button.jsx';
import { Select } from '../components/ui/Input.jsx';
import DataTable from '../components/ui/DataTable.jsx';
import { StatCard, Tabs } from '../components/ui/Misc.jsx';
import { EmptyState, ErrorState, Skeleton } from '../components/ui/States.jsx';
import { HorizontalBarChart, OccupancyChart, PaymentTrendChart } from '../components/charts.jsx';
import { formatDateTime, formatMoney, plural } from '../utils/format.js';

const EXPORTS = [
  { kind: 'fees', title: 'Fee records', text: 'Every fee with amount, paid, balance and status.' },
  { kind: 'payments', title: 'Payments', text: 'All transactions, including reversed ones.' },
  { kind: 'students', title: 'Students', text: 'Student register with current room.' },
  { kind: 'rooms', title: 'Rooms & occupancy', text: 'Capacity, occupied and free beds per room.' },
];

export default function ReportsPage() {
  const [tab, setTab] = useState('overview');
  return (
    <>
      <PageHeader title="Reports" description="Financial and occupancy reports, CSV exports and the audit trail." />
      <div className="mb-5">
        <Tabs active={tab} onChange={setTab} tabs={[
          { key: 'overview', label: 'Overview' },
          { key: 'exports', label: 'CSV exports' },
          { key: 'audit', label: 'Audit log' },
        ]} />
      </div>
      {tab === 'overview' && <Overview />}
      {tab === 'exports' && <Exports />}
      {tab === 'audit' && <AuditLog />}
    </>
  );
}

function Table({ head, rows }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
            {head.map((h, i) => <th key={h} className={`pb-2 font-semibold ${i > 0 ? 'text-right' : ''}`}>{h}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={r[0]}>
              {r.map((c, i) => <td key={i} className={`py-2 ${i > 0 ? 'text-right tabular-nums' : 'text-slate-700'}`}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Overview() {
  const [months, setMonths] = useState('12');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setError('');
    reportService.summary({ months }).then(setData).catch((err) => setError(getErrorMessage(err)));
  }, [months]);
  useEffect(() => { load(); }, [load]);

  if (error) return <Card><ErrorState message={error} onRetry={load} /></Card>;
  if (!data) return <div className="grid gap-4 md:grid-cols-3">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}</div>;

  const t = data.totals;
  const periodTotal = data.revenue_by_month.reduce((s, m) => s + m.amount_minor, 0);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label={`Collected (last ${months} months)`} tone="green" value={formatMoney(periodTotal)} />
        <StatCard label="Outstanding balance" tone="amber" value={formatMoney(t.fees.outstanding_minor)} sub={plural(t.fees.unpaid_count, 'unpaid fee')} />
        <StatCard label="Overdue" tone="rose" value={formatMoney(t.fees.overdue_minor)} sub={`${plural(t.fees.overdue_count, 'fee')} past due`} />
        <StatCard label="Occupancy" value={`${t.rooms.occupancy_percent}%`} sub={`${t.rooms.beds_occupied}/${t.rooms.beds_total} beds`} />
      </div>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
          <h2 className="text-sm font-semibold text-slate-900">Revenue by month</h2>
          <Select aria-label="Period" value={months} onChange={(e) => setMonths(e.target.value)} className="w-40">
            <option value="6">Last 6 months</option>
            <option value="12">Last 12 months</option>
            <option value="24">Last 24 months</option>
          </Select>
        </div>
        <div className="p-5"><PaymentTrendChart data={data.revenue_by_month} height={280} /></div>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="p-5">
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Fees by type</h2>
          {data.fees_by_type.length === 0 ? <p className="text-sm text-slate-500">No fees billed yet.</p> : (
            <Table head={['Type', 'Fees', 'Billed', 'Outstanding']}
              rows={data.fees_by_type.map((f) => [label(f.fee_type), f.count, formatMoney(f.billed_minor), formatMoney(f.outstanding_minor)])} />
          )}
          <h2 className="mb-3 mt-6 text-sm font-semibold text-slate-900">Collections by method</h2>
          {data.revenue_by_method.length === 0 ? <p className="text-sm text-slate-500">No payments yet.</p> : (
            <Table head={['Method', 'Payments', 'Amount']}
              rows={data.revenue_by_method.map((m) => [label(m.method), m.count, formatMoney(m.amount_minor)])} />
          )}
        </Card>
        <Card className="p-5">
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Highest outstanding balances</h2>
          {data.top_outstanding.length === 0 ? <p className="text-sm text-slate-500">No outstanding balances. </p> : (
            <Table head={['Student', 'Outstanding']}
              rows={data.top_outstanding.map((s) => [`${s.full_name} (${s.student_code})`, formatMoney(s.outstanding_minor)])} />
          )}
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="p-5">
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Occupancy by block</h2>
          {data.occupancy_by_block.length === 0 ? <p className="text-sm text-slate-500">No active rooms.</p> : (
            <>
              <OccupancyChart data={data.occupancy_by_block} />
              <div className="mt-4">
                <Table head={['Block', 'Rooms', 'Beds', 'Occupied', 'Free']}
                  rows={data.occupancy_by_block.map((b) => [`Block ${b.block}`, b.rooms, b.beds, b.occupied, b.available])} />
              </div>
            </>
          )}
        </Card>
        <Card className="p-5">
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Complaints by category</h2>
          {data.complaints_by_category.length === 0 ? <p className="text-sm text-slate-500">No complaints filed.</p> : (
            <>
              <HorizontalBarChart data={data.complaints_by_category.map((c) => ({ ...c, name: label(c.category) }))}
                dataKey="total" nameKey="name" name="Complaints" />
              <div className="mt-4">
                <Table head={['Category', 'Total', 'Active']}
                  rows={data.complaints_by_category.map((c) => [label(c.category), c.total, c.active])} />
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

function Exports() {
  const toast = useToast();
  const [busy, setBusy] = useState('');
  const download = async (kind) => {
    setBusy(kind);
    try {
      await reportService.download(kind);
      toast.success('Export downloaded.');
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBusy('');
    }
  };
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {EXPORTS.map((e) => (
        <Card key={e.kind} className="flex items-start justify-between gap-4 p-5">
          <div className="flex gap-3">
            <FileSpreadsheet className="mt-0.5 h-5 w-5 text-navy-600" />
            <div>
              <p className="text-sm font-semibold text-slate-900">{e.title}</p>
              <p className="mt-0.5 text-sm text-slate-500">{e.text}</p>
            </div>
          </div>
          <Button variant="secondary" size="sm" icon={Download} loading={busy === e.kind} onClick={() => download(e.kind)}>CSV</Button>
        </Card>
      ))}
      <p className="text-xs text-slate-500 sm:col-span-2">
        Filtered exports are also available from the Fees, Payments, Students and Rooms pages; they use the filters you have applied there.
      </p>
    </div>
  );
}

function AuditLog() {
  // The audit endpoint filters by action prefix; map the search box onto it.
  const list = usePaginatedList(
    ({ search, ...p }) => reportService.auditLogs({ ...p, action: search }),
    { initialFilters: { entity_type: '' }, perPage: 20 },
  );
  const columns = [
    { key: 'created_at', header: 'When', render: (a) => <span className="whitespace-nowrap text-slate-500">{formatDateTime(a.created_at)}</span> },
    { key: 'actor', header: 'Who', render: (a) => a.actor ? <span>{a.actor.full_name}<span className="block text-xs text-slate-400">{label(a.actor.role)}</span></span> : <span className="text-slate-400">System</span> },
    { key: 'action', header: 'Action', render: (a) => <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">{a.action}</code> },
    { key: 'entity', header: 'Record', className: 'hidden md:table-cell', render: (a) => <span className="text-slate-600">{a.entity_type}{a.entity_id ? ` #${a.entity_id}` : ''}</span> },
    {
      key: 'details', header: 'Details', className: 'hidden lg:table-cell',
      render: (a) => <span className="line-clamp-2 max-w-md break-all font-mono text-xs text-slate-500">{Object.keys(a.details).length ? JSON.stringify(a.details) : '—'}</span>,
    },
  ];
  return (
    <Card>
      <ListToolbar
        list={list}
        placeholder="Filter by action prefix, e.g. payment."
        filters={[{ key: 'entity_type', label: 'All records', options: ['user', 'student', 'room', 'allocation', 'fee', 'payment', 'complaint', 'notice'].map((v) => ({ value: v, label: label(v) })) }]}
      />
      <DataTable
        columns={columns}
        rows={list.items}
        loading={list.loading}
        error={list.error}
        onRetry={list.reload}
        pagination={list.pagination}
        onPageChange={list.setPage}
        empty={<EmptyState icon={History} title="No audit entries" message="Administrative actions will be recorded here." />}
      />
    </Card>
  );
}
