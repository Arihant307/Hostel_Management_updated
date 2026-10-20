import { useState } from 'react';
import { CalendarPlus, Download, IndianRupee, Plus, ReceiptText, Search, Wallet } from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext.jsx';
import { useToast } from '../features/toast/ToastContext.jsx';
import { feeService, reportService } from '../services/resources.js';
import { getErrorMessage } from '../services/api.js';
import usePaginatedList from '../hooks/usePaginatedList.js';
import PageHeader from '../components/PageHeader.jsx';
import ListToolbar, { toOptions } from '../components/ListToolbar.jsx';
import StatusBadge, { label } from '../components/StatusBadge.jsx';
import Card from '../components/ui/Card.jsx';
import Button from '../components/ui/Button.jsx';
import DataTable from '../components/ui/DataTable.jsx';
import { StatCard } from '../components/ui/Misc.jsx';
import { EmptyState } from '../components/ui/States.jsx';
import { AssignFeeModal, FeeDetailModal, GenerateRentModal, RecordPaymentModal } from '../features/fees/FeeModals.jsx';
import { formatDate, formatMoney } from '../utils/format.js';

const STATUS_OPTIONS = ['outstanding', 'pending', 'partially_paid', 'overdue', 'paid', 'cancelled'];

export default function FeesPage() {
  const { user } = useAuth();
  const isAdmin = user.role === 'admin';
  const isStudent = user.role === 'student';
  const toast = useToast();
  const [assigning, setAssigning] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [viewing, setViewing] = useState(null);
  const [paying, setPaying] = useState(null);
  const list = usePaginatedList(feeService.list, {
    initialFilters: { status: '', fee_type: '' },
    initialSort: { key: 'due_date', order: 'desc' },
    perPage: 15,
  });
  const totals = list.extra.totals;

  const exportCsv = () => reportService.download('fees', list.filters).catch((err) => toast.error(getErrorMessage(err)));

  const columns = [
    ...(isStudent ? [] : [{
      key: 'student', header: 'Student', sortable: true,
      render: (f) => (
        <span>
          <span className="block font-medium text-slate-900">{f.student.full_name}</span>
          <span className="block text-xs text-slate-500">{f.student.student_code}</span>
        </span>
      ),
    }]),
    {
      key: 'fee', header: 'Fee',
      render: (f) => (
        <button type="button" onClick={() => setViewing(f.id)} className="text-left">
          <span className="block font-medium text-slate-800 hover:text-navy-700">{f.description || label(f.fee_type)}</span>
          <span className="block text-xs text-slate-500">{label(f.fee_type)} · {formatDate(f.period_start)} – {formatDate(f.period_end)}</span>
        </button>
      ),
    },
    { key: 'due_date', header: 'Due', sortable: true, render: (f) => formatDate(f.due_date) },
    { key: 'amount', header: 'Amount', sortable: true, className: 'text-right', render: (f) => <span className="tabular-nums">{formatMoney(f.amount_due_minor)}</span> },
    { key: 'balance', header: 'Balance', className: 'text-right hidden sm:table-cell', render: (f) => <span className="tabular-nums font-medium">{formatMoney(f.balance_minor)}</span> },
    { key: 'status', header: 'Status', render: (f) => <StatusBadge status={f.status} /> },
    {
      key: 'actions', header: <span className="sr-only">Actions</span>, className: 'text-right',
      render: (f) => (
        <div className="flex justify-end gap-1">
          {isAdmin && f.balance_minor > 0 && f.status !== 'cancelled' && (
            <Button variant="ghost" size="sm" icon={Wallet} onClick={() => setPaying(f)}>Pay</Button>
          )}
          <Button variant="ghost" size="sm" onClick={() => setViewing(f.id)}>View</Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={isStudent ? 'My fees' : 'Fees'}
        description={isStudent ? 'Your hostel bills, payments and receipts.' : 'Billing, balances and fee status for all students.'}
        actions={isAdmin && (
          <>
            <Button variant="secondary" icon={Download} onClick={exportCsv}>Export CSV</Button>
            <Button variant="secondary" icon={CalendarPlus} onClick={() => setGenerating(true)}>Generate rent</Button>
            <Button icon={Plus} onClick={() => setAssigning(true)}>Assign fee</Button>
          </>
        )}
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <StatCard icon={ReceiptText} label="Billed" value={formatMoney(totals?.billed_minor)} sub="Excludes cancelled fees" loading={!totals} />
        <StatCard icon={IndianRupee} tone="green" label="Collected" value={formatMoney(totals?.paid_minor)} sub="Completed payments only" loading={!totals} />
        <StatCard icon={Wallet} tone="amber" label="Outstanding" value={formatMoney(totals?.outstanding_minor)} sub="For the current filters" loading={!totals} />
      </div>

      <Card>
        <ListToolbar
          list={list}
          placeholder={isStudent ? 'Search description' : 'Search student, ID or description'}
          filters={[
            { key: 'status', label: 'Any status', options: toOptions(STATUS_OPTIONS, (s) => (s === 'outstanding' ? 'Outstanding (unpaid)' : label(s))) },
            { key: 'fee_type', label: 'All fee types', options: toOptions(['hostel_rent', 'mess', 'security_deposit', 'fine', 'other'], label) },
          ]}
        />
        <DataTable
          columns={columns}
          rows={list.items}
          loading={list.loading}
          error={list.error}
          onRetry={list.reload}
          sort={list.sort}
          onSortChange={list.setSort}
          pagination={list.pagination}
          onPageChange={list.setPage}
          empty={list.hasFilters
            ? <EmptyState icon={Search} title="No matching fees" message="Try a different search or clear the filters." />
            : <EmptyState icon={ReceiptText} title="No fees yet" message={isStudent ? 'You have no hostel bills.' : 'Assign a fee or generate monthly rent to get started.'} />}
        />
      </Card>

      <AssignFeeModal open={assigning} onClose={() => setAssigning(false)}
        onSaved={() => { setAssigning(false); toast.success('Fee assigned.'); list.reload(); }} />
      <GenerateRentModal open={generating} onClose={() => setGenerating(false)}
        onDone={(res) => { setGenerating(false); toast.success(res.message); list.reload(); }} />
      <RecordPaymentModal fee={paying} onClose={() => setPaying(null)}
        onSaved={(p) => { setPaying(null); toast.success(`Payment recorded. Receipt ${p.receipt_number}.`); list.reload(); }} />
      <FeeDetailModal feeId={viewing} canManage={isAdmin} onClose={() => setViewing(null)} onChanged={list.reload} />
    </>
  );
}
