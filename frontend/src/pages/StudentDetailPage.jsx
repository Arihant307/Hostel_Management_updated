import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, BedDouble, Check, Clock, KeyRound, Mail, Pencil, ShieldAlert, Trash2, UserCheck, UserX, X } from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext.jsx';
import { useToast } from '../features/toast/ToastContext.jsx';
import { complaintService, feeService, studentService } from '../services/resources.js';
import { getErrorMessage } from '../services/api.js';
import Card from '../components/ui/Card.jsx';
import Badge from '../components/ui/Badge.jsx';
import Button from '../components/ui/Button.jsx';
import ConfirmDialog from '../components/ui/ConfirmDialog.jsx';
import ResetPasswordModal from '../components/ResetPasswordModal.jsx';
import StatusBadge, { label } from '../components/StatusBadge.jsx';
import { DetailList, StatCard, Tabs } from '../components/ui/Misc.jsx';
import { EmptyState, ErrorState, Skeleton } from '../components/ui/States.jsx';
import StudentFormModal from '../features/students/StudentFormModal.jsx';
import { AuditTimeline, ReasonModal } from '../components/AccountWidgets.jsx';
import { formatDate, formatDateTime, formatMoney, initials, plural } from '../utils/format.js';

export default function StudentDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [student, setStudent] = useState(null);
  const [fees, setFees] = useState([]);
  const [complaints, setComplaints] = useState([]);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('allocations');
  const [editing, setEditing] = useState(false);
  const [resetting, setResetting] = useState(null);
  const [confirm, setConfirm] = useState(null); // 'status' | 'delete'
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [history, setHistory] = useState(null);
  const canManage = user.role === 'admin' || user.role === 'warden';
  const canSeeFees = user.role !== 'staff';

  const load = useCallback(async () => {
    setError('');
    try {
      const [s, f, c] = await Promise.all([
        studentService.get(id),
        // The limited staff role has no access to finance.
        canSeeFees ? feeService.list({ student_id: id, per_page: 50 }) : Promise.resolve({ items: [] }),
        complaintService.list({ student_id: id, per_page: 50 }),
      ]);
      setStudent(s);
      setFees(f.items);
      setComplaints(c.items);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }, [id, canSeeFees]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (tab !== 'history') return;
    setHistory(null);
    studentService.history(id, { per_page: 50 }).then((d) => setHistory(d.items)).catch(() => setHistory([]));
  }, [tab, id, student?.approval_status, student?.is_active]);

  const act = async (fn, message) => {
    setBusy(true);
    try {
      const res = await fn();
      if (res && res.id) setStudent(res);
      toast.success(message || res?.message);
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const runConfirm = async () => {
    setBusy(true);
    try {
      if (confirm === 'delete') {
        await studentService.remove(student.id);
        toast.success('Student deleted.');
        navigate('/students', { replace: true });
        return;
      }
      const updated = await studentService.setStatus(student.id, !student.is_active);
      setStudent(updated);
      toast.success(updated.is_active ? 'Student reactivated.' : 'Student deactivated.');
      setConfirm(null);
    } catch (err) {
      toast.error(getErrorMessage(err));
      setConfirm(null);
    } finally {
      setBusy(false);
    }
  };

  if (error) return <Card><ErrorState message={error} onRetry={load} /></Card>;
  if (!student) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const alloc = student.current_allocation;
  const summary = student.fee_summary;

  return (
    <>
      <Link to="/students" className="mb-4 inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800">
        <ArrowLeft className="h-4 w-4" /> All students
      </Link>

      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-4">
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-navy-100 text-lg font-semibold text-navy-800">
            {initials(student.full_name)}
          </span>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-navy-900">{student.full_name}</h1>
            <p className="mt-0.5 flex flex-wrap items-center gap-2 text-sm text-slate-500">
              {student.student_code} · {student.course}, {student.department} · Year {student.academic_year}
              <Badge tone={student.is_active ? 'success' : 'neutral'}>{student.is_active ? 'Active' : 'Inactive'}</Badge>
              {student.approval_status !== 'approved' && (
                <Badge tone={student.approval_status === 'pending' ? 'warning' : 'danger'}>{label(student.approval_status)}</Badge>
              )}
              {!student.email_verified && <Badge tone="warning">Email not verified</Badge>}
            </p>
          </div>
        </div>
        {canManage && <div className="flex flex-wrap gap-2">
          {!alloc && student.is_active && student.approval_status === 'approved' && (
            <Button icon={BedDouble} onClick={() => navigate(`/allocations?student=${student.id}`)}>Allocate room</Button>
          )}
          <Button variant="secondary" icon={Pencil} onClick={() => setEditing(true)}>Edit</Button>
          <Button variant="secondary" icon={Mail} loading={busy}
            onClick={() => act(() => studentService.sendPasswordReset(student.id))} disabled={!student.is_active}>
            Email reset link
          </Button>
          <Button variant="secondary" icon={KeyRound} onClick={() => setResetting(student)}>Set password</Button>
          <Button
            variant="secondary"
            icon={student.is_active ? UserX : UserCheck}
            onClick={() => setConfirm('status')}
          >
            {student.is_active ? 'Deactivate' : 'Reactivate'}
          </Button>
          {user.role === 'admin' && (
            <Button variant="ghost" icon={Trash2} className="text-rose-600 hover:bg-rose-50" onClick={() => setConfirm('delete')}>
              Delete
            </Button>
          )}
        </div>}
      </div>

      {student.approval_status === 'pending' && (
        <div className="mb-6 flex flex-col gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex gap-3">
            <Clock className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
            <div className="text-sm text-amber-900">
              <p className="font-semibold">Registration waiting for approval</p>
              <p className="mt-0.5">
                Registered online {formatDate(student.registration_date)}.{' '}
                {student.email_verified ? 'Email address verified.' : 'The student has not verified their email yet, so it cannot be approved.'}
              </p>
            </div>
          </div>
          {canManage && (
            <div className="flex shrink-0 gap-2">
              <Button variant="secondary" icon={X} onClick={() => setRejecting(true)}>Reject</Button>
              <Button icon={Check} loading={busy} disabled={!student.email_verified}
                onClick={() => act(() => studentService.approve(student.id), 'Registration approved. The student can now sign in.')}>
                Approve
              </Button>
            </div>
          )}
        </div>
      )}
      {student.approval_status === 'rejected' && (
        <div className="mb-6 flex gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" />
          <div>
            <p className="font-semibold">Registration rejected</p>
            {student.approval_note && <p className="mt-0.5">Reason: {student.approval_note}</p>}
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={BedDouble} label="Current room" tone={alloc ? 'navy' : 'slate'}
          value={alloc ? `${alloc.room.block}-${alloc.room.room_number}` : 'None'}
          sub={alloc ? `Since ${formatDate(alloc.allocated_on)}` : 'Not allocated'} />
        {canSeeFees && <StatCard label="Outstanding" tone="amber" value={formatMoney(summary.outstanding_minor)}
          sub={summary.overdue_count ? plural(summary.overdue_count, 'overdue fee') : 'Nothing overdue'} />}
        {canSeeFees && <StatCard label="Total paid" tone="green" value={formatMoney(summary.total_paid_minor)}
          sub={`of ${formatMoney(summary.total_billed_minor)} billed`} />}
        <StatCard label="Complaints" value={student.complaint_count} sub="All time" />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card className="min-w-0 p-5 xl:col-span-1">
          <h2 className="mb-2 text-sm font-semibold text-slate-900">Profile</h2>
          <DetailList items={[
            ['Email', student.email],
            ['Phone', student.phone],
            ['Gender', student.gender ? label(student.gender) : null],
            ['Date of birth', student.date_of_birth ? formatDate(student.date_of_birth) : null],
            ['Address', student.address],
            ['Registered', formatDate(student.registration_date)],
          ]} />
          <h2 className="mb-2 mt-5 text-sm font-semibold text-slate-900">Emergency contact</h2>
          <DetailList items={[
            ['Name', student.emergency_contact.name],
            ['Phone', student.emergency_contact.phone],
            ['Relation', student.emergency_contact.relation],
          ]} />
        </Card>

        <Card className="min-w-0 xl:col-span-2">
          <div className="px-5 pt-3">
            <Tabs
              active={tab}
              onChange={setTab}
              tabs={[
                { key: 'allocations', label: 'Allocation history', count: student.allocation_history.length },
                ...(canSeeFees ? [{ key: 'fees', label: 'Fees', count: fees.length }] : []),
                { key: 'complaints', label: 'Complaints', count: complaints.length },
                { key: 'history', label: 'Account history' },
              ]}
            />
          </div>
          <div className="p-5">
            {tab === 'allocations' && <AllocationHistory items={student.allocation_history} />}
            {tab === 'fees' && <FeeList fees={fees} />}
            {tab === 'complaints' && <ComplaintList complaints={complaints} />}
            {tab === 'history' && (history === null ? <Skeleton className="h-32 w-full" />
              : history.length === 0 ? <EmptyState title="No account changes" message="Status changes and approvals appear here." />
                : <AuditTimeline items={history} />)}
          </div>
        </Card>
      </div>

      <StudentFormModal
        open={editing}
        student={student}
        onClose={() => setEditing(false)}
        onSaved={(s) => {
          setStudent(s);
          setEditing(false);
          toast.success('Student updated.');
        }}
      />
      <ResetPasswordModal user={resetting} onReset={studentService.resetPassword} onClose={() => setResetting(null)} />
      <ReasonModal
        open={rejecting}
        title="Reject registration"
        description={`${student.full_name} will be emailed that their registration was not approved, with your reason.`}
        action="Reject registration"
        onClose={() => setRejecting(false)}
        onSubmit={async (reason) => setStudent(await studentService.reject(student.id, reason))}
        onDone={() => { setRejecting(false); toast.success('Registration rejected.'); }}
      />
      <ConfirmDialog
        open={confirm === 'status'}
        title={student.is_active ? 'Deactivate student?' : 'Reactivate student?'}
        message={student.is_active
          ? `${student.full_name} will be signed out and cannot sign in. Students with a room must be checked out first.`
          : `${student.full_name} will be able to sign in again.`}
        confirmLabel={student.is_active ? 'Deactivate' : 'Reactivate'}
        tone={student.is_active ? 'danger' : 'primary'}
        loading={busy}
        onConfirm={runConfirm}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm === 'delete'}
        title="Delete student permanently?"
        message="Only students with no allocation, fee or complaint history can be deleted. This cannot be undone."
        confirmLabel="Delete"
        tone="danger"
        loading={busy}
        onConfirm={runConfirm}
        onCancel={() => setConfirm(null)}
      />
    </>
  );
}

function AllocationHistory({ items }) {
  if (!items.length) return <EmptyState icon={BedDouble} title="No allocations yet" message="This student has never been assigned a room." />;
  return (
    <ol className="space-y-3">
      {items.map((a) => (
        <li key={a.id} className="flex items-start justify-between gap-4 rounded-lg border border-slate-100 p-3">
          <div>
            <p className="text-sm font-medium text-slate-800">
              Room {a.room.block}-{a.room.room_number}
              <span className="ml-2 text-xs font-normal text-slate-500">Floor {a.room.floor} · {label(a.room.room_type)}</span>
            </p>
            <p className="mt-0.5 text-xs text-slate-500">
              {formatDate(a.allocated_on)} → {a.checked_out_on ? formatDate(a.checked_out_on) : 'present'}
              {a.expected_checkout_on && !a.checked_out_on && ` (expected ${formatDate(a.expected_checkout_on)})`}
            </p>
            {a.notes && <p className="mt-1 whitespace-pre-line text-xs text-slate-500">{a.notes}</p>}
          </div>
          <StatusBadge status={a.status} />
        </li>
      ))}
    </ol>
  );
}

function FeeList({ fees }) {
  if (!fees.length) return <EmptyState title="No fees" message="No fees have been assigned to this student." />;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="pb-2 font-semibold">Fee</th>
            <th className="pb-2 font-semibold">Due</th>
            <th className="pb-2 text-right font-semibold">Amount</th>
            <th className="pb-2 text-right font-semibold">Balance</th>
            <th className="pb-2 pl-4 font-semibold">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {fees.map((f) => (
            <tr key={f.id}>
              <td className="py-2.5 text-slate-700">{f.description || label(f.fee_type)}</td>
              <td className="py-2.5 text-slate-500">{formatDate(f.due_date)}</td>
              <td className="py-2.5 text-right tabular-nums">{formatMoney(f.amount_due_minor)}</td>
              <td className="py-2.5 text-right tabular-nums">{formatMoney(f.balance_minor)}</td>
              <td className="py-2.5 pl-4"><StatusBadge status={f.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ComplaintList({ complaints }) {
  if (!complaints.length) return <EmptyState title="No complaints" message="This student has not filed any complaints." />;
  return (
    <ul className="divide-y divide-slate-100">
      {complaints.map((c) => (
        <li key={c.id} className="flex items-center justify-between gap-4 py-2.5">
          <div>
            <Link to={`/complaints?open=${c.id}`} className="text-sm font-medium text-slate-800 hover:text-navy-700">{c.title}</Link>
            <p className="text-xs text-slate-500">{label(c.category)} · {formatDateTime(c.created_at)}</p>
          </div>
          <StatusBadge status={c.status} />
        </li>
      ))}
    </ul>
  );
}
