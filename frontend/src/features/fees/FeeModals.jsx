import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Ban, Pencil, Receipt, Undo2, Wallet } from 'lucide-react';
import Modal from '../../components/ui/Modal.jsx';
import Button from '../../components/ui/Button.jsx';
import Input, { Select } from '../../components/ui/Input.jsx';
import Textarea from '../../components/ui/Textarea.jsx';
import Badge from '../../components/ui/Badge.jsx';
import { DetailList, FormError } from '../../components/ui/Misc.jsx';
import { Skeleton } from '../../components/ui/States.jsx';
import StatusBadge, { label } from '../../components/StatusBadge.jsx';
import StudentSelect from '../../components/StudentSelect.jsx';
import useForm from '../../hooks/useForm.js';
import { useToast } from '../toast/ToastContext.jsx';
import { feeService, paymentService } from '../../services/resources.js';
import { getErrorMessage } from '../../services/api.js';
import { formatDate, formatMoney, fromMinor, toMinor, todayISO } from '../../utils/format.js';

const FEE_TYPES = ['hostel_rent', 'mess', 'security_deposit', 'fine', 'other'];
const METHODS = ['cash', 'upi', 'bank_transfer', 'card', 'cheque'];
const moneyError = (v) => (Number.isNaN(toMinor(v)) || toMinor(v) <= 0) && 'Enter an amount greater than 0.';

function monthBounds() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const y = now.getFullYear();
  const m = now.getMonth() + 1;
  const last = new Date(y, m, 0).getDate();
  // Default due date: the 10th, or the month's last day once the 10th has passed.
  const dueDay = now.getDate() <= 10 ? 10 : last;
  return { start: `${y}-${pad(m)}-01`, end: `${y}-${pad(m)}-${pad(last)}`, due: `${y}-${pad(m)}-${pad(dueDay)}`, month: `${y}-${pad(m)}` };
}

export function AssignFeeModal({ open, onClose, onSaved }) {
  const b = monthBounds();
  const initial = { student: null, fee_type: 'hostel_rent', description: '', period_start: b.start, period_end: b.end, due_date: b.due, amount: '' };
  const form = useForm(initial);

  useEffect(() => {
    if (open) form.reset(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const save = async (e) => {
    e.preventDefault();
    const result = await form.submit(
      (v) => feeService.create({
        student_id: v.student.id, fee_type: v.fee_type, description: v.description.trim() || null,
        period_start: v.period_start, period_end: v.period_end, due_date: v.due_date, amount_due_minor: toMinor(v.amount),
      }),
      { validate: (v) => ({
        student: !v.student && 'Choose a student.',
        amount: moneyError(v.amount),
        period_end: v.period_end < v.period_start && 'Must be on or after the period start.',
      }) },
    );
    if (result) onSaved(result);
  };

  return (
    <Modal open={open} onClose={form.submitting ? undefined : onClose} title="Assign fee"
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={form.submitting}>Cancel</Button>
        <Button type="submit" form="assign-fee-form" loading={form.submitting}>Assign fee</Button>
      </>}>
      <form id="assign-fee-form" onSubmit={save} className="space-y-4" noValidate>
        <FormError message={form.formError} />
        <StudentSelect required value={form.values.student} error={form.errors.student || form.errors.student_id}
          onChange={(s) => form.setValues((v) => ({ ...v, student: s }))} params={{ status: 'active' }} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Fee type" required {...form.bind('fee_type')}>
            {FEE_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}
          </Select>
          <Input label="Amount (₹)" inputMode="decimal" required {...form.bind('amount')} error={form.errors.amount || form.errors.amount_due_minor} />
        </div>
        <Input label="Description" {...form.bind('description')} placeholder="e.g. October rent" />
        <div className="grid gap-4 sm:grid-cols-3">
          <Input label="Period start" type="date" required {...form.bind('period_start')} />
          <Input label="Period end" type="date" required {...form.bind('period_end')} />
          <Input label="Due date" type="date" required {...form.bind('due_date')} />
        </div>
      </form>
    </Modal>
  );
}

export function GenerateRentModal({ open, onClose, onDone }) {
  const b = monthBounds();
  const form = useForm({ month: b.month, due_date: b.due });

  useEffect(() => {
    if (open) form.reset({ month: b.month, due_date: b.due });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const save = async (e) => {
    e.preventDefault();
    const result = await form.submit((v) => feeService.generateRent(v));
    if (result) onDone(result);
  };

  return (
    <Modal open={open} onClose={form.submitting ? undefined : onClose} title="Generate monthly rent" size="sm"
      description="Bills one month's rent to every student with an active room allocation, using each room's monthly fee. Students already billed for that month are skipped."
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={form.submitting}>Cancel</Button>
        <Button type="submit" form="generate-rent-form" loading={form.submitting}>Generate</Button>
      </>}>
      <form id="generate-rent-form" onSubmit={save} className="space-y-4" noValidate>
        <FormError message={form.formError} />
        <Input label="Month" type="month" required {...form.bind('month')} />
        <Input label="Due date" type="date" required {...form.bind('due_date')} />
      </form>
    </Modal>
  );
}

export function RecordPaymentModal({ fee, onClose, onSaved }) {
  const form = useForm({ amount: '', method: 'cash', paid_on: todayISO(), reference: '', notes: '' });

  useEffect(() => {
    if (fee) form.reset({ amount: fromMinor(fee.balance_minor), method: 'cash', paid_on: todayISO(), reference: '', notes: '' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fee]);

  const save = async (e) => {
    e.preventDefault();
    const result = await form.submit(
      (v) => paymentService.record({
        fee_record_id: fee.id, amount_minor: toMinor(v.amount), method: v.method, paid_on: v.paid_on,
        reference: v.reference.trim() || null, notes: v.notes.trim() || null,
      }),
      { validate: (v) => ({
        amount: moneyError(v.amount) || (toMinor(v.amount) > fee.balance_minor && `Cannot exceed the balance of ${formatMoney(fee.balance_minor)}.`),
        reference: v.method !== 'cash' && !v.reference.trim() && 'Enter the transaction or cheque reference.',
        paid_on: v.paid_on > todayISO() && 'Cannot be in the future.',
      }) },
    );
    if (result) onSaved(result);
  };

  return (
    <Modal open={Boolean(fee)} onClose={form.submitting ? undefined : onClose} title="Record payment"
      description={fee ? `${fee.student?.full_name ?? ''} · ${fee.description || label(fee.fee_type)} · balance ${formatMoney(fee.balance_minor)}` : undefined}
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={form.submitting}>Cancel</Button>
        <Button type="submit" form="record-payment-form" loading={form.submitting}>Record payment</Button>
      </>}>
      <form id="record-payment-form" onSubmit={save} className="space-y-4" noValidate>
        <FormError message={form.formError} />
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
          Record only money the hostel office has actually received. It is saved as a manually recorded payment, not a verified online payment.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Amount (₹)" inputMode="decimal" required {...form.bind('amount')} error={form.errors.amount || form.errors.amount_minor} />
          <Select label="Method" required {...form.bind('method')}>
            {METHODS.map((m) => <option key={m} value={m}>{label(m)}</option>)}
          </Select>
          <Input label="Paid on" type="date" required max={todayISO()} {...form.bind('paid_on')} />
          <Input label="Reference" {...form.bind('reference')} placeholder={form.values.method === 'cash' ? 'Optional' : 'UTR / cheque no.'} />
        </div>
        <Textarea label="Notes" rows={2} {...form.bind('notes')} />
      </form>
    </Modal>
  );
}

/** Fee detail with payment history; admins get edit/cancel/record/reverse actions. */
export function FeeDetailModal({ feeId, canManage, onClose, onChanged }) {
  const toast = useToast();
  const [fee, setFee] = useState(null);
  const [mode, setMode] = useState(null); // 'edit' | 'cancel' | {reverse: payment}
  const [paying, setPaying] = useState(null);

  const load = () => feeService.get(feeId).then(setFee).catch((err) => toast.error(getErrorMessage(err)));

  useEffect(() => {
    setFee(null);
    setMode(null);
    if (feeId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feeId]);

  const changed = (message) => {
    toast.success(message);
    setMode(null);
    load();
    onChanged();
  };

  return (
    <>
      <Modal open={Boolean(feeId) && !paying} onClose={onClose} title="Fee details" size="lg">
        {!fee ? <Skeleton className="h-48 w-full" /> : (
          <div className="space-y-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-lg font-semibold text-slate-900">{fee.description || label(fee.fee_type)}</p>
                <p className="text-sm text-slate-500">
                  {fee.student?.full_name} · {fee.student?.student_code}
                </p>
              </div>
              <StatusBadge status={fee.status} />
            </div>
            <div className="grid grid-cols-3 gap-3 text-center">
              {[['Amount due', fee.amount_due_minor], ['Paid', fee.amount_paid_minor], ['Balance', fee.balance_minor]].map(([k, v]) => (
                <div key={k} className="rounded-lg bg-surface-muted p-3">
                  <p className="text-xs text-slate-500">{k}</p>
                  <p className="mt-1 font-semibold tabular-nums text-slate-900">{formatMoney(v)}</p>
                </div>
              ))}
            </div>
            <DetailList items={[
              ['Type', label(fee.fee_type)],
              ['Period', `${formatDate(fee.period_start)} – ${formatDate(fee.period_end)}`],
              ['Due date', formatDate(fee.due_date)],
              ...(fee.cancelled_at ? [['Cancelled', `${formatDate(fee.cancelled_at)} — ${fee.cancellation_reason}`]] : []),
            ]} />

            <div>
              <h3 className="mb-2 text-sm font-semibold text-slate-900">Payments</h3>
              {fee.payments.length === 0 ? <p className="text-sm text-slate-500">No payments recorded.</p> : (
                <ul className="divide-y divide-slate-100 rounded-lg border border-slate-100">
                  {fee.payments.map((p) => (
                    <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2.5">
                      <div>
                        <p className="text-sm font-medium tabular-nums text-slate-800">
                          {formatMoney(p.amount_minor)} <span className="font-normal text-slate-500">· {label(p.method)} · {formatDate(p.paid_on)}</span>
                        </p>
                        <p className="text-xs text-slate-500">
                          {p.receipt_number} · <Badge tone="neutral">{p.is_verified_online ? 'Verified online' : 'Manually recorded'}</Badge>
                          {p.reversal_reason && ` · Reversed: ${p.reversal_reason}`}
                        </p>
                      </div>
                      <div className="flex items-center gap-1">
                        <StatusBadge status={p.status} />
                        {p.status === 'completed' && (
                          <Link to={`/receipts/${p.id}`} className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-navy-700 hover:bg-navy-50">
                            <Receipt className="h-3.5 w-3.5" /> Receipt
                          </Link>
                        )}
                        {canManage && p.status === 'completed' && (
                          <Button variant="ghost" size="sm" icon={Undo2} onClick={() => setMode({ reverse: p })}>Reverse</Button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {canManage && fee.status !== 'cancelled' && !mode && (
              <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 pt-4">
                <Button variant="ghost" icon={Ban} className="text-rose-600 hover:bg-rose-50" onClick={() => setMode('cancel')}>Cancel fee</Button>
                <Button variant="secondary" icon={Pencil} onClick={() => setMode('edit')}>Edit</Button>
                {fee.balance_minor > 0 && <Button icon={Wallet} onClick={() => setPaying(fee)}>Record payment</Button>}
              </div>
            )}
            {mode === 'edit' && <EditFeeForm fee={fee} onCancel={() => setMode(null)} onDone={() => changed('Fee updated.')} />}
            {mode === 'cancel' && (
              <ReasonForm title="Cancel this fee?" action="Cancel fee" hint="Fees with recorded payments must have those payments reversed first."
                onCancel={() => setMode(null)} onSubmit={(reason) => feeService.cancel(fee.id, reason)} onDone={() => changed('Fee cancelled.')} />
            )}
            {mode?.reverse && (
              <ReasonForm title={`Reverse payment ${mode.reverse.receipt_number}?`} action="Reverse payment"
                hint="The amount is added back to the balance. The payment stays in the history as reversed."
                onCancel={() => setMode(null)} onSubmit={(reason) => paymentService.reverse(mode.reverse.id, reason)} onDone={() => changed('Payment reversed.')} />
            )}
          </div>
        )}
      </Modal>
      <RecordPaymentModal fee={paying} onClose={() => setPaying(null)}
        onSaved={(p) => { setPaying(null); changed(`Payment recorded. Receipt ${p.receipt_number}.`); }} />
    </>
  );
}

function EditFeeForm({ fee, onCancel, onDone }) {
  const form = useForm({ description: fee.description ?? '', due_date: fee.due_date, amount: fromMinor(fee.amount_due_minor) });
  const save = async (e) => {
    e.preventDefault();
    const result = await form.submit(
      (v) => feeService.update(fee.id, { description: v.description.trim() || null, due_date: v.due_date, amount_due_minor: toMinor(v.amount) }),
      { validate: (v) => ({ amount: moneyError(v.amount) }) },
    );
    if (result) onDone();
  };
  return (
    <form onSubmit={save} className="space-y-3 rounded-lg border border-slate-200 p-4" noValidate>
      <FormError message={form.formError} />
      <Input label="Description" {...form.bind('description')} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Input label="Due date" type="date" {...form.bind('due_date')} />
        <Input label="Amount due (₹)" inputMode="decimal" {...form.bind('amount')} error={form.errors.amount || form.errors.amount_due_minor} />
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel}>Back</Button>
        <Button type="submit" loading={form.submitting}>Save</Button>
      </div>
    </form>
  );
}

function ReasonForm({ title, hint, action, onSubmit, onCancel, onDone }) {
  const form = useForm({ reason: '' });
  const save = async (e) => {
    e.preventDefault();
    const result = await form.submit(async (v) => { await onSubmit(v.reason.trim()); return true; },
      { validate: (v) => ({ reason: v.reason.trim().length < 3 && 'Give a short reason (at least 3 characters).' }) });
    if (result) onDone();
  };
  return (
    <form onSubmit={save} className="space-y-3 rounded-lg border border-rose-200 bg-rose-50/40 p-4" noValidate>
      <p className="text-sm font-semibold text-slate-900">{title}</p>
      <p className="text-xs text-slate-600">{hint}</p>
      <FormError message={form.formError} />
      <Input label="Reason" required {...form.bind('reason')} />
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel}>Back</Button>
        <Button variant="danger" type="submit" loading={form.submitting}>{action}</Button>
      </div>
    </form>
  );
}
