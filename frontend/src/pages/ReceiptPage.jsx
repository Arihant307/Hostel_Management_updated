import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Building2, Printer } from 'lucide-react';
import { paymentService } from '../services/resources.js';
import { getErrorMessage } from '../services/api.js';
import Button from '../components/ui/Button.jsx';
import Spinner from '../components/ui/Spinner.jsx';
import { label } from '../components/StatusBadge.jsx';
import { formatDate, formatDateTime, formatMoney } from '../utils/format.js';

/** Printable payment receipt (standalone page, no app chrome). */
export default function ReceiptPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    paymentService.receipt(id).then(setData).catch((err) => setError(getErrorMessage(err)));
  }, [id]);

  if (error) return <p className="p-10 text-center text-sm text-rose-600">{error}</p>;
  if (!data) return <div className="flex min-h-screen items-center justify-center text-navy-700"><Spinner className="h-8 w-8" label="Loading receipt" /></div>;

  const { payment, fee, student, room } = data;
  const reversed = payment.status !== 'completed';

  return (
    <div className="min-h-screen bg-surface-muted px-4 py-10 print:bg-white print:p-0">
      <div className="mx-auto mb-4 flex max-w-2xl justify-between print:hidden">
        <Button variant="secondary" icon={ArrowLeft} onClick={() => navigate(-1)}>Back</Button>
        <Button icon={Printer} onClick={() => window.print()}>Print / Save as PDF</Button>
      </div>
      <article className="relative mx-auto max-w-2xl overflow-hidden rounded-xl border border-slate-200 bg-white p-8 shadow-card print:border-0 print:shadow-none">
        {reversed && (
          <div className="absolute right-6 top-6 rotate-6 rounded border-2 border-rose-500 px-3 py-1 text-sm font-bold uppercase tracking-wider text-rose-600">
            {label(payment.status)}
          </div>
        )}
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 pb-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-navy-800 text-white">
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <p className="text-lg font-semibold text-navy-900">{data.hostel_name}</p>
              <p className="text-xs text-slate-500">Payment receipt</p>
            </div>
          </div>
          <div className="text-right">
            <p className="font-mono text-sm font-semibold text-slate-900">{payment.receipt_number}</p>
            <p className="text-xs text-slate-500">Paid on {formatDate(payment.paid_on)}</p>
          </div>
        </header>

        <section className="grid gap-6 py-6 sm:grid-cols-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Received from</p>
            <p className="mt-1 font-medium text-slate-900">{student.full_name}</p>
            <p className="text-sm text-slate-600">{student.student_code}</p>
            <p className="text-sm text-slate-600">{student.course}, {student.department}</p>
            {room && <p className="text-sm text-slate-600">Room {room.block}-{room.room_number}</p>}
          </div>
          <div className="sm:text-right">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Payment</p>
            <p className="mt-1 text-sm text-slate-700">{label(payment.method)}{payment.reference ? ` · Ref ${payment.reference}` : ''}</p>
            <p className="text-sm text-slate-700">{payment.is_verified_online ? 'Verified online payment' : 'Recorded by hostel office'}</p>
            {payment.recorded_by && <p className="text-sm text-slate-500">by {payment.recorded_by}</p>}
          </div>
        </section>

        <table className="w-full text-sm">
          <thead>
            <tr className="border-y border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="py-2 font-semibold">Description</th>
              <th className="py-2 font-semibold">Period</th>
              <th className="py-2 text-right font-semibold">Amount</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-slate-100">
              <td className="py-3 text-slate-800">{fee.description || label(fee.fee_type)}</td>
              <td className="py-3 text-slate-600">{formatDate(fee.period_start)} – {formatDate(fee.period_end)}</td>
              <td className="py-3 text-right font-semibold tabular-nums">{formatMoney(payment.amount_minor)}</td>
            </tr>
          </tbody>
        </table>

        <dl className="ml-auto mt-4 w-full max-w-xs space-y-1.5 text-sm">
          <div className="flex justify-between"><dt className="text-slate-500">Fee amount</dt><dd className="tabular-nums">{formatMoney(fee.amount_due_minor)}</dd></div>
          <div className="flex justify-between"><dt className="text-slate-500">Total paid to date</dt><dd className="tabular-nums">{formatMoney(fee.amount_paid_minor)}</dd></div>
          <div className="flex justify-between border-t border-slate-200 pt-1.5 font-semibold"><dt>Balance remaining</dt><dd className="tabular-nums">{formatMoney(fee.balance_minor)}</dd></div>
        </dl>

        <footer className="mt-8 border-t border-slate-200 pt-4 text-xs text-slate-400">
          Generated {formatDateTime(data.generated_at)}. This receipt is computer generated and valid without a signature.
        </footer>
      </article>
    </div>
  );
}
