import { useEffect, useState } from 'react';
import {
  Check, Copy, History, KeyRound, Mail, MailPlus, Plus, Search, ShieldCheck, UserCheck, UserX, X,
} from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext.jsx';
import { useToast } from '../features/toast/ToastContext.jsx';
import { invitationService, staffService } from '../services/authService.js';
import { getErrorMessage, getFieldErrors } from '../services/api.js';
import usePaginatedList from '../hooks/usePaginatedList.js';
import useForm from '../hooks/useForm.js';
import PageHeader from '../components/PageHeader.jsx';
import ListToolbar from '../components/ListToolbar.jsx';
import Card from '../components/ui/Card.jsx';
import Badge from '../components/ui/Badge.jsx';
import Button from '../components/ui/Button.jsx';
import Input, { Select } from '../components/ui/Input.jsx';
import Modal from '../components/ui/Modal.jsx';
import ConfirmDialog from '../components/ui/ConfirmDialog.jsx';
import ResetPasswordModal from '../components/ResetPasswordModal.jsx';
import { HistoryModal, ReasonModal } from '../components/AccountWidgets.jsx';
import DataTable from '../components/ui/DataTable.jsx';
import { FormError, Tabs } from '../components/ui/Misc.jsx';
import { EmptyState, Skeleton } from '../components/ui/States.jsx';
import { ROLE_LABELS, formatDate, formatDateTime, initials } from '../utils/format.js';
import { PASSWORD_RULES, isStrongPassword } from '../utils/password.js';

const ROLE_TONE = { admin: 'navy', warden: 'neutral', staff: 'neutral' };
const APPROVAL_TONE = { approved: 'success', pending: 'warning', rejected: 'danger' };

export default function StaffPage() {
  const [tab, setTab] = useState('accounts');
  const [pendingCount, setPendingCount] = useState(null);
  const [creating, setCreating] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [version, setVersion] = useState(0);
  const toast = useToast();
  const bump = () => setVersion((v) => v + 1);

  useEffect(() => {
    staffService.list({ approval: 'pending', per_page: 1 })
      .then((d) => setPendingCount(d.counts?.pending ?? 0)).catch(() => {});
  }, [version]);

  return (
    <>
      <PageHeader
        title="Staff accounts"
        description="Administrators, wardens and staff: accounts, applications and invitations."
        actions={
          <>
            <Button variant="secondary" icon={MailPlus} onClick={() => setInviting(true)}>Invite staff</Button>
            <Button icon={Plus} onClick={() => setCreating(true)}>Add staff member</Button>
          </>
        }
      />
      <div className="mb-4">
        <Tabs active={tab} onChange={setTab} tabs={[
          { key: 'accounts', label: 'Accounts' },
          { key: 'applications', label: 'Applications', count: pendingCount || null },
          { key: 'invitations', label: 'Invitations' },
        ]} />
      </div>
      {tab === 'accounts' && <AccountsTab key={`a${version}`} onChanged={bump} />}
      {tab === 'applications' && <ApplicationsTab key={`p${version}`} onChanged={bump} />}
      {tab === 'invitations' && <InvitationsTab key={`i${version}`} onInvite={() => setInviting(true)} />}

      <CreateStaffModal open={creating} onClose={() => setCreating(false)}
        onCreated={(u) => {
          setCreating(false);
          toast.success(`${u.full_name} can now sign in as ${ROLE_LABELS[u.role].toLowerCase()}.`);
          bump();
        }} />
      <InviteModal open={inviting} onClose={() => setInviting(false)}
        onCreated={() => { if (tab === 'invitations') bump(); }} />
    </>
  );
}

// --- Accounts ---------------------------------------------------------------

function AccountsTab({ onChanged }) {
  const { user: me } = useAuth();
  const toast = useToast();
  const [resetting, setResetting] = useState(null);
  const [toggling, setToggling] = useState(null);
  const [roleChange, setRoleChange] = useState(null); // {user, role}
  const [historyOf, setHistoryOf] = useState(null);
  const [busy, setBusy] = useState(false);
  const list = usePaginatedList(staffService.list, {
    initialFilters: { role: '', status: '', approval: 'approved' },
    initialSort: { key: 'created_at', order: 'desc' },
  });

  const run = async (fn, message) => {
    setBusy(true);
    try {
      await fn();
      toast.success(message);
      list.reload();
      onChanged?.();
      return true;
    } catch (err) {
      toast.error(getErrorMessage(err));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const sendReset = (u) => run(() => staffService.sendPasswordReset(u.id), `Password reset link emailed to ${u.email}.`);

  const columns = [
    {
      key: 'name', header: 'Name', sortable: true,
      render: (u) => (
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-navy-50 text-xs font-semibold text-navy-700">{initials(u.full_name)}</span>
          <div className="min-w-0">
            <p className="truncate font-medium text-slate-900">
              {u.full_name}{u.id === me.id && <span className="ml-1.5 text-xs font-normal text-slate-400">(you)</span>}
            </p>
            <p className="truncate text-xs text-slate-500">{u.email}</p>
          </div>
        </div>
      ),
    },
    {
      key: 'role', header: 'Role',
      render: (u) => (u.id === me.id || u.approval_status !== 'approved' ? (
        <Badge tone={ROLE_TONE[u.role]}>{ROLE_LABELS[u.role]}</Badge>
      ) : (
        <Select aria-label={`Role for ${u.full_name}`} value={u.role} className="h-8 w-36 text-xs"
          onChange={(e) => setRoleChange({ user: u, role: e.target.value })}>
          <option value="admin">Administrator</option>
          <option value="warden">Warden</option>
          <option value="staff">Staff</option>
        </Select>
      )),
    },
    {
      key: 'status', header: 'Status',
      render: (u) => (
        <div className="flex flex-wrap gap-1">
          <Badge tone={u.is_active ? 'success' : 'danger'}>{u.is_active ? 'Active' : 'Inactive'}</Badge>
          {u.approval_status !== 'approved' && <Badge tone={APPROVAL_TONE[u.approval_status]}>{u.approval_status}</Badge>}
          {!u.email_verified && <Badge tone="warning">Unverified</Badge>}
        </div>
      ),
    },
    {
      key: 'last_login_at', header: 'Last sign-in', sortable: true, className: 'hidden lg:table-cell',
      render: (u) => <span className="text-slate-500">{u.last_login_at ? formatDateTime(u.last_login_at) : 'Never'}</span>,
    },
    {
      key: 'actions', header: <span className="sr-only">Actions</span>, className: 'text-right',
      render: (u) => (
        <div className="flex justify-end gap-1">
          <Button variant="ghost" size="sm" icon={History} onClick={() => setHistoryOf(u)} aria-label={`History for ${u.full_name}`} />
          {u.id !== me.id && (
            <>
              <Button variant="ghost" size="sm" icon={Mail} onClick={() => sendReset(u)} disabled={!u.is_active || busy}
                aria-label={`Email a password reset link to ${u.full_name}`} title="Email reset link" />
              <Button variant="ghost" size="sm" icon={KeyRound} onClick={() => setResetting(u)}
                aria-label={`Set a temporary password for ${u.full_name}`} title="Set temporary password" />
              <Button variant="ghost" size="sm" icon={u.is_active ? UserX : UserCheck} onClick={() => setToggling(u)}
                className={u.is_active ? 'text-rose-600 hover:bg-rose-50 hover:text-rose-700' : ''}>
                <span className="hidden xl:inline">{u.is_active ? 'Deactivate' : 'Activate'}</span>
              </Button>
            </>
          )}
        </div>
      ),
    },
  ];

  return (
    <Card>
      <ListToolbar
        list={list}
        placeholder="Search by name or email"
        filters={[
          { key: 'role', label: 'All roles', options: [{ value: 'admin', label: 'Administrators' }, { value: 'warden', label: 'Wardens' }, { value: 'staff', label: 'Staff' }] },
          { key: 'status', label: 'Any status', options: [{ value: 'active', label: 'Active' }, { value: 'inactive', label: 'Inactive' }] },
          { key: 'approval', label: 'Any approval', options: [{ value: 'approved', label: 'Approved' }, { value: 'pending', label: 'Pending' }, { value: 'rejected', label: 'Rejected' }] },
        ]}
      />
      <DataTable
        columns={columns} rows={list.items} loading={list.loading} error={list.error} onRetry={list.reload}
        sort={list.sort} onSortChange={list.setSort} pagination={list.pagination} onPageChange={list.setPage}
        empty={list.hasFilters
          ? <EmptyState icon={Search} title="No matching staff" message="Try a different search or clear the filters." />
          : <EmptyState icon={ShieldCheck} title="No staff accounts yet" message="Add or invite staff to manage the hostel." />}
      />
      <ResetPasswordModal user={resetting} onReset={staffService.resetPassword} onClose={() => setResetting(null)} />
      <HistoryModal user={historyOf} onClose={() => setHistoryOf(null)} />
      <ConfirmDialog
        open={Boolean(toggling)}
        title={toggling?.is_active ? 'Deactivate account?' : 'Reactivate account?'}
        message={toggling?.is_active
          ? `${toggling?.full_name} will be signed out immediately and cannot sign in until reactivated.`
          : `${toggling?.full_name} will be able to sign in again.`}
        confirmLabel={toggling?.is_active ? 'Deactivate' : 'Reactivate'}
        tone={toggling?.is_active ? 'danger' : 'primary'}
        loading={busy}
        onConfirm={async () => {
          const ok = await run(() => staffService.update(toggling.id, { is_active: !toggling.is_active }),
            `${toggling.full_name} has been ${toggling.is_active ? 'deactivated' : 'reactivated'}.`);
          if (ok !== undefined) setToggling(null);
        }}
        onCancel={() => setToggling(null)}
      />
      <ConfirmDialog
        open={Boolean(roleChange)}
        title="Change role?"
        message={roleChange ? `${roleChange.user.full_name} will become ${ROLE_LABELS[roleChange.role]}. They are signed out now and get the new permissions when they sign in again.` : ''}
        confirmLabel="Change role"
        loading={busy}
        onConfirm={async () => {
          await run(() => staffService.update(roleChange.user.id, { role: roleChange.role }),
            `${roleChange.user.full_name} is now ${ROLE_LABELS[roleChange.role]}.`);
          setRoleChange(null);
        }}
        onCancel={() => { setRoleChange(null); list.reload(); }}
      />
    </Card>
  );
}

// --- Applications ---------------------------------------------------------------

function ApplicationsTab({ onChanged }) {
  const toast = useToast();
  const [approving, setApproving] = useState(null);
  const [rejecting, setRejecting] = useState(null);
  const list = usePaginatedList(staffService.list, {
    initialFilters: { approval: 'pending' },
    initialSort: { key: 'created_at', order: 'desc' },
  });

  const done = (message) => {
    toast.success(message);
    setApproving(null);
    setRejecting(null);
    list.reload();
    onChanged();
  };

  return (
    <Card>
      <div className="border-b border-slate-100 px-5 py-3.5 text-sm text-slate-600">
        People who applied for a staff account without an invitation. They can't sign in until you approve them,
        and you choose the role they get.
      </div>
      {list.loading && !list.items.length ? (
        <div className="space-y-3 p-5">{[1, 2].map((i) => <Skeleton key={i} className="h-20 w-full" />)}</div>
      ) : list.items.length === 0 ? (
        <EmptyState icon={UserCheck} title="No pending applications" message="New staff applications will appear here." />
      ) : (
        <ul className="divide-y divide-slate-100">
          {list.items.map((u) => (
            <li key={u.id} className="flex flex-col gap-4 px-5 py-4 md:flex-row md:items-center md:justify-between">
              <div className="min-w-0">
                <p className="font-medium text-slate-900">{u.full_name}</p>
                <p className="text-sm text-slate-500">{u.email}{u.phone ? ` · ${u.phone}` : ''}</p>
                {u.staff_profile && (
                  <p className="mt-1 text-xs text-slate-500">
                    Employee ID <strong className="text-slate-700">{u.staff_profile.employee_id}</strong> ·{' '}
                    {u.staff_profile.department} · requested <strong className="text-slate-700">{u.staff_profile.requested_role}</strong>
                  </p>
                )}
                <div className="mt-1.5 flex flex-wrap gap-1">
                  <Badge tone={u.email_verified ? 'success' : 'warning'}>{u.email_verified ? 'Email verified' : 'Email not verified'}</Badge>
                  <Badge tone="neutral">Applied {formatDate(u.created_at)}</Badge>
                </div>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button variant="secondary" icon={X} onClick={() => setRejecting(u)}>Reject</Button>
                <Button icon={Check} onClick={() => setApproving(u)}>Approve</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <ApproveModal applicant={approving} onClose={() => setApproving(null)}
        onDone={(u) => done(`${u.full_name} approved as ${ROLE_LABELS[u.role].toLowerCase()}.`)} />
      <ReasonModal
        open={Boolean(rejecting)}
        title="Reject application"
        description={rejecting ? `${rejecting.full_name} will be told their application was not approved. The reason is included in the email.` : ''}
        action="Reject application"
        onClose={() => setRejecting(null)}
        onSubmit={(reason) => staffService.reject(rejecting.id, reason)}
        onDone={() => done('Application rejected.')}
      />
    </Card>
  );
}

function ApproveModal({ applicant, onClose, onDone }) {
  const form = useForm({ role: 'staff' });
  useEffect(() => {
    if (applicant) form.reset({ role: applicant.staff_profile?.requested_role || 'staff' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicant]);
  const save = async (e) => {
    e.preventDefault();
    const res = await form.submit((v) => staffService.approve(applicant.id, v.role));
    if (res) onDone(res);
  };
  return (
    <Modal open={Boolean(applicant)} onClose={form.submitting ? undefined : onClose} title="Approve application" size="sm"
      description={applicant ? `Choose the role ${applicant.full_name} gets.` : undefined}
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={form.submitting}>Cancel</Button>
        <Button type="submit" form="approve-form" loading={form.submitting}>Approve</Button>
      </>}>
      <form id="approve-form" onSubmit={save} className="space-y-3" noValidate>
        <FormError message={form.formError} />
        {applicant && !applicant.email_verified && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
            This person hasn't verified their email yet. They'll be able to sign in only after verifying it.
          </p>
        )}
        <Select label="Role" {...form.bind('role')}>
          <option value="staff">Staff: view students and rooms, handle complaints</option>
          <option value="warden">Warden: manage students, rooms, allocations and notices</option>
        </Select>
        <p className="text-xs text-slate-500">Administrator access can only be granted afterwards, from the Accounts tab.</p>
      </form>
    </Modal>
  );
}

// --- Invitations ---------------------------------------------------------------

function InvitationsTab({ onInvite }) {
  const toast = useToast();
  const [revoking, setRevoking] = useState(null);
  const [busy, setBusy] = useState(false);
  const list = usePaginatedList(invitationService.list, { initialFilters: { status: '' } });
  const STATUS_TONE = { active: 'success', used: 'navy', revoked: 'neutral', expired: 'warning' };

  const columns = [
    { key: 'email', header: 'Email', render: (i) => <span className="font-medium text-slate-800">{i.email}</span> },
    { key: 'role', header: 'Role', render: (i) => ROLE_LABELS[i.role] },
    { key: 'status', header: 'Status', render: (i) => <Badge tone={STATUS_TONE[i.status]}>{i.status}</Badge> },
    {
      key: 'expires', header: 'Expires / used', className: 'hidden md:table-cell',
      render: (i) => <span className="text-slate-500">{i.used_at ? `Used ${formatDate(i.used_at)}${i.used_by ? ` by ${i.used_by}` : ''}` : formatDateTime(i.expires_at)}</span>,
    },
    { key: 'by', header: 'Invited by', className: 'hidden lg:table-cell', render: (i) => <span className="text-slate-500">{i.created_by || '—'}</span> },
    {
      key: 'actions', header: <span className="sr-only">Actions</span>, className: 'text-right',
      render: (i) => i.status === 'active' && (
        <Button variant="ghost" size="sm" className="text-rose-600 hover:bg-rose-50" onClick={() => setRevoking(i)}>Revoke</Button>
      ),
    },
  ];

  return (
    <Card>
      <ListToolbar list={list} placeholder="Search by email"
        filters={[{ key: 'status', label: 'Any status', options: ['active', 'used', 'revoked', 'expired'].map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1) })) }]} />
      <DataTable columns={columns} rows={list.items} loading={list.loading} error={list.error} onRetry={list.reload}
        pagination={list.pagination} onPageChange={list.setPage}
        empty={<EmptyState icon={MailPlus} title="No invitations" message="Invite staff so they can register with the right role."
          action={<Button icon={MailPlus} onClick={onInvite}>Invite staff</Button>} />} />
      <ConfirmDialog open={Boolean(revoking)} title="Revoke invitation?"
        message={revoking ? `The invitation for ${revoking.email} will stop working immediately.` : ''}
        confirmLabel="Revoke" tone="danger" loading={busy}
        onConfirm={async () => {
          setBusy(true);
          try {
            await invitationService.revoke(revoking.id);
            toast.success('Invitation revoked.');
            setRevoking(null);
            list.reload();
          } catch (err) {
            toast.error(getErrorMessage(err));
          } finally {
            setBusy(false);
          }
        }}
        onCancel={() => setRevoking(null)} />
    </Card>
  );
}

function InviteModal({ open, onClose, onCreated }) {
  const form = useForm({ email: '', role: 'staff', note: '' });
  const [created, setCreated] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (open) {
      form.reset({ email: '', role: 'staff', note: '' });
      setCreated(null);
      setCopied(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const save = async (e) => {
    e.preventDefault();
    const res = await form.submit(
      (v) => invitationService.create({ email: v.email.trim(), role: v.role, note: v.note.trim() || null }),
      { validate: (v) => ({ email: !/^\S+@\S+\.\S+$/.test(v.email.trim()) && 'Enter a valid email address.' }) },
    );
    if (res) {
      setCreated(res);
      onCreated(res);
    }
  };

  const signupLink = created ? `${window.location.origin}/signup?type=staff&code=${created.code}` : '';
  const copy = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <Modal open={open} onClose={form.submitting ? undefined : onClose} title={created ? 'Invitation created' : 'Invite staff'}
      description={created ? undefined : 'They receive an email with a single-use link that expires automatically.'}
      footer={created
        ? <Button onClick={onClose}>Done</Button>
        : <>
          <Button variant="secondary" onClick={onClose} disabled={form.submitting}>Cancel</Button>
          <Button type="submit" form="invite-form" loading={form.submitting}>Send invitation</Button>
        </>}>
      {created ? (
        <div className="space-y-4 text-sm">
          <p className="text-slate-600">
            An invitation for <strong>{created.email}</strong> as <strong>{ROLE_LABELS[created.role]}</strong> was emailed
            and expires {formatDateTime(created.expires_at)}.
          </p>
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
            <p className="text-xs font-semibold text-amber-900">Shown only once</p>
            <p className="mt-1 text-xs text-amber-800">If email isn't set up, share this link with the invitee privately.</p>
            <div className="mt-2 flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded bg-white px-2 py-1.5 text-xs text-slate-700">{signupLink}</code>
              <Button size="sm" variant="secondary" icon={copied ? Check : Copy} onClick={() => copy(signupLink)}>
                {copied ? 'Copied' : 'Copy'}
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <form id="invite-form" onSubmit={save} className="space-y-4" noValidate>
          <FormError message={form.formError} />
          <Input label="Email" type="email" required {...form.bind('email')} />
          <Select label="Role" {...form.bind('role')}>
            <option value="staff">Staff</option>
            <option value="warden">Warden</option>
          </Select>
          <Input label="Note (optional)" {...form.bind('note')} placeholder="e.g. Night warden, Block B" />
        </form>
      )}
    </Modal>
  );
}

const EMPTY_STAFF = { full_name: '', email: '', phone: '', role: 'warden', password: '' };

function CreateStaffModal({ open, onClose, onCreated }) {
  const [form, setForm] = useState(EMPTY_STAFF);
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => {
    if (open) {
      setForm(EMPTY_STAFF);
      setErrors({});
      setFormError('');
    }
  }, [open]);

  const update = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
    setErrors((er) => ({ ...er, [field]: undefined }));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (saving) return;
    const next = {};
    if (form.full_name.trim().length < 2) next.full_name = 'Enter the full name.';
    if (!/^\S+@\S+\.\S+$/.test(form.email.trim())) next.email = 'Enter a valid email address.';
    if (!isStrongPassword(form.password)) next.password = 'Password does not meet the requirements.';
    setErrors(next);
    if (Object.keys(next).length) return;
    setSaving(true);
    setFormError('');
    try {
      const created = await staffService.create({
        ...form, full_name: form.full_name.trim(), email: form.email.trim(), phone: form.phone.trim() || null,
      });
      onCreated(created);
    } catch (err) {
      const fields = getFieldErrors(err);
      setErrors(fields);
      if (!Object.keys(fields).length) setFormError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={saving ? undefined : onClose} title="Add staff member"
      description="Creates an approved account directly. Share the temporary password securely; they should change it after first sign-in."
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
        <Button type="submit" form="create-staff-form" loading={saving}>Create account</Button>
      </>}>
      <form id="create-staff-form" onSubmit={submit} className="space-y-4" noValidate>
        <FormError message={formError} />
        <Input label="Full name" required value={form.full_name} onChange={update('full_name')} error={errors.full_name} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Email" type="email" required value={form.email} onChange={update('email')} error={errors.email} autoComplete="off" />
          <Input label="Phone" type="tel" value={form.phone} onChange={update('phone')} error={errors.phone} />
        </div>
        <Select label="Role" required value={form.role} onChange={update('role')} error={errors.role}>
          <option value="staff">Staff: view students and rooms, handle complaints</option>
          <option value="warden">Warden: hostel operations</option>
          <option value="admin">Administrator: full access</option>
        </Select>
        <Input label="Temporary password" type="password" required autoComplete="new-password" value={form.password}
          onChange={update('password')} error={errors.password} hint={PASSWORD_RULES.map((r) => r.label).join(' · ')} />
      </form>
    </Modal>
  );
}
