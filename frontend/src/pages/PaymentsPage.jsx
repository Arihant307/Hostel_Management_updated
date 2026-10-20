import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Download, Receipt, Search, Undo2, Wallet } from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext.jsx';
import { useToast } from '../features/toast/ToastContext.jsx';
import { paymentService, reportService } from '../services/resources.js';
import { getErrorMessage } from '../services/api.js';
import usePaginatedList from '../hooks/usePaginatedList.js';
import useForm from '../hooks/useForm.js';
import PageHeader from '../components/PageHeader.jsx';
import ListToolbar, { toOptions } from '../components/ListToolbar.jsx';
import StatusBadge, { label } from '../components/StatusBadge.jsx';
import Card from '../components/ui/Card.jsx';
import Badge from '../components/ui/Badge.jsx';
import Button from '../components/ui/Button.jsx';
import Input from '../components/ui/Input.jsx';
import Modal from '../components/ui/Modal.jsx';
import DataTable from '../components/ui/DataTable.jsx';
import { FormError } from '../components/ui/Misc.jsx';
import { EmptyState } from '../components/ui/States.jsx';
import { formatDate, formatMoney } from '../utils/format.js';

export default function PaymentsPage() {
  const { user } = useAuth();
  const isAdmin = user.role === 'admin';
  const isStudent = user.role === 'student';
  const toast = useToast();
  const [reversing, setReversing] = useState(null);
  const list = usePaginatedList(paymentService.list, {
    initialFilters: { method: '', status: '', from: '', to: '' },
    initialSort: { key: 'paid_on', order: 'desc' },
    perPage: 15,
  });

  const exportCsv = () => reportService.download('payments', list.filters).catch((err) => toast.error(getErrorMessage(err)));

  const columns = [
    {
      key: 'receipt', header: 'Receipt',
      render: (p) => (
        <span>
          <span className="block font-mono text-xs font-medium text-slate-800">{p.receipt_number}</span>
          <span className="block text-xs text-slate-500">{p.fee.description || label(p.fee.fee_type)}</span>
        </span>
      ),
    },
    ...(isStudent ? [] : [{
      key: 'student', header: 'Student', sortable: true,
      render: (p) => (
        <span>
          <span className="block font-medium text-slate-900">{p.student.full_name}</span>
          <span className="block text-xs text-slate-500">{p.student.student_code}</span>
        </span>
      ),
    }]),
    { key: 'paid_on', header: 'Paid on', sortable: true, render: (p) => formatDate(p.paid_on) },
    {
      key: 'method', header: 'Method', className: 'hidden md:table-cell',
      render: (p) => (
        <span>
          {label(p.method)}
          <span className="block"><Badge tone="neutral">{p.is_verified_online ? 'Verified online' : 'Manual'}</Badge></span>
        </span>
      ),
    },
    { key: 'amount', header: 'Amount', sortable: true, className: 'text-right', render: (p) => <span className="tabular-nums font-medium">{formatMoney(p.amount_minor)}</span> },
    { key: 'status', header: 'Status', render: (p) => <StatusBadge status={p.status} /> },
    {
      key: 'actions', header: <span className="sr-only">Actions</span>, className: 'text-right',
      render: (p) => (
        <div className="flex justify-end gap-1">
          {p.status === 'completed' && (
            <Link to={`/receipts/${p.id}`} className="inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-xs font-medium text-slate-600 hover:bg-slate-100">
              <Receipt className="h-4 w-4" /> Receipt
            </Link>
          )}
          {isAdmin && p.status === 'completed' && (
            <Button variant="ghost" size="sm" icon={Undo2} onClick={() => setReversing(p)}>Reverse</Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={isStudent ? 'My payments' : 'Payments'}
        description="Every recorded transaction. Reversed payments stay listed for the audit trail."
        actions={isAdmin && <Button variant="secondary" icon={Download} onClick={exportCsv}>Export CSV</Button>}
      />
      <Card>
        <ListToolbar
          list={list}
          placeholder={isStudent ? 'Search' : 'Search student, receipt or reference'}
          filters={[
            { key: 'method', label: 'All methods', options: toOptions(['cash', 'upi', 'bank_transfer', 'card', 'cheque'], label) },
            { key: 'status', label: 'Any status', options: toOptions(['completed', 'reversed', 'pending', 'failed'], label) },
          ]}
        >
          <div className="grid grid-cols-2 gap-3">
            <Input type="date" aria-label="Paid from" value={list.filters.from} onChange={(e) => list.setFilter('from', e.target.value)} />
            <Input type="date" aria-label="Paid until" value={list.filters.to} onChange={(e) => list.setFilter('to', e.target.value)} />
          </div>
        </ListToolbar>
        {list.extra.totals && (
          <p className="border-b border-slate-100 px-4 py-2.5 text-sm text-slate-600">
            Completed total for these filters: <span className="font-semibold tabular-nums text-slate-900">{formatMoney(list.extra.totals.completed_minor)}</span>
          </p>
        )}
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
            ? <EmptyState icon={Search} title="No matching payments" message="Try different dates or clear the filters." />
            : <EmptyState icon={Wallet} title="No payments yet" message="Payments appear here once they are recorded against a fee." />}
        />
      </Card>
      <ReverseModal payment={reversing} onClose={() => setReversing(null)}
        onDone={() => { setReversing(null); toast.success('Payment reversed.'); list.reload(); }} />
    </>
  );
}

function ReverseModal({ payment, onClose, onDone }) {
  const form = useForm({ reason: '' });
  const save = async (e) => {
    e.preventDefault();
    const result = await form.submit((v) => paymentService.reverse(payment.id, v.reason.trim()),
      { validate: (v) => ({ reason: v.reason.trim().length < 3 && 'Give a short reason.' }) });
    if (result) { form.reset({ reason: '' }); onDone(); }
  };
  return (
    <Modal open={Boolean(payment)} onClose={form.submitting ? undefined : onClose} size="sm" title="Reverse payment?"
      description={payment ? `${payment.receipt_number} · ${formatMoney(payment.amount_minor)}. The amount is added back to the fee balance.` : undefined}
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={form.submitting}>Cancel</Button>
        <Button variant="danger" type="submit" form="reverse-form" loading={form.submitting}>Reverse</Button>
      </>}>
      <form id="reverse-form" onSubmit={save} noValidate className="space-y-3">
        <FormError message={form.formError} />
        <Input label="Reason" required {...form.bind('reason')} placeholder="e.g. Cheque bounced" />
      </form>
    </Modal>
  );
}
