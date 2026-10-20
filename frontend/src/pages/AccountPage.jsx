import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BadgeCheck, Clock, LogOut, MonitorSmartphone, ShieldAlert } from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext.jsx';
import { useToast } from '../features/toast/ToastContext.jsx';
import { authService } from '../services/authService.js';
import { getErrorMessage } from '../services/api.js';
import useForm from '../hooks/useForm.js';
import PageHeader from '../components/PageHeader.jsx';
import PasswordFields, { validatePasswordPair } from '../components/PasswordFields.jsx';
import Card from '../components/ui/Card.jsx';
import Badge from '../components/ui/Badge.jsx';
import Input from '../components/ui/Input.jsx';
import Button from '../components/ui/Button.jsx';
import ConfirmDialog from '../components/ui/ConfirmDialog.jsx';
import { DetailList, FormError } from '../components/ui/Misc.jsx';
import { isStrongPassword } from '../utils/password.js';
import { ROLE_LABELS, formatDateTime } from '../utils/format.js';

const PHONE_RE = /^\+?[0-9][0-9\s-]{6,18}[0-9]$/;

export default function AccountPage() {
  const { user, studentProfile, logout, logoutAll } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [confirmAll, setConfirmAll] = useState(false);
  const [busy, setBusy] = useState(false);

  const signOutEverywhere = async () => {
    setBusy(true);
    try {
      await logoutAll();
      toast.success('Signed out of all sessions.');
      navigate('/login', { replace: true });
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBusy(false);
      setConfirmAll(false);
    }
  };

  const signOut = async () => {
    await logout();
    toast.success('You have been signed out.');
    navigate('/login', { replace: true });
  };

  return (
    <>
      <PageHeader title="My account" description="Your profile, account status and sign-in security." />
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-2">
          <Card className="p-5">
            <h2 className="text-sm font-semibold text-slate-900">Account status</h2>
            <DetailList items={[
              ['Role', ROLE_LABELS[user.role]],
              ['Email', user.email],
              ['Email verification', user.email_verified
                ? <Badge key="v" tone="success"><BadgeCheck className="h-3 w-3" /> Verified</Badge>
                : <Badge key="v" tone="warning"><ShieldAlert className="h-3 w-3" /> Not verified</Badge>],
              ['Account', user.approval_status === 'approved'
                ? <Badge key="a" tone="success">Approved</Badge>
                : <Badge key="a" tone="warning"><Clock className="h-3 w-3" /> {user.approval_status}</Badge>],
              ['Last sign-in', formatDateTime(user.last_login_at)],
              ['Member since', formatDateTime(user.created_at)],
              ...(studentProfile ? [['Student ID', studentProfile.student_code],
                ['Course', `${studentProfile.course} (${studentProfile.department}), year ${studentProfile.academic_year}`]] : []),
              ...(user.staff_profile ? [['Employee ID', user.staff_profile.employee_id],
                ['Department', user.staff_profile.department]] : []),
            ]} />
            <p className="mt-3 text-xs text-slate-500">
              Email, role and ID changes are made by the hostel office.
            </p>
          </Card>
          <Card className="p-5">
            <h2 className="text-sm font-semibold text-slate-900">Sessions</h2>
            <p className="mt-1 text-sm text-slate-500">Sign out here, or everywhere you're signed in, for example after using a shared computer.</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="secondary" icon={LogOut} onClick={signOut}>Sign out</Button>
              <Button variant="danger" icon={MonitorSmartphone} onClick={() => setConfirmAll(true)}>Sign out of all sessions</Button>
            </div>
          </Card>
        </div>
        <div className="space-y-6 lg:col-span-3">
          <Card><ProfileForm /></Card>
          <Card id="password"><ChangePasswordForm /></Card>
        </div>
      </div>
      <ConfirmDialog
        open={confirmAll}
        title="Sign out of all sessions?"
        message="Every device signed in to your account, including this one, will be signed out immediately."
        confirmLabel="Sign out everywhere"
        tone="danger"
        loading={busy}
        onConfirm={signOutEverywhere}
        onCancel={() => setConfirmAll(false)}
      />
    </>
  );
}

function ProfileForm() {
  const { user, studentProfile, refreshSession } = useAuth();
  const toast = useToast();
  const isStudent = user.role === 'student';
  const initial = () => ({
    full_name: user.full_name,
    phone: user.phone ?? '',
    ...(isStudent && studentProfile ? {
      address: studentProfile.address ?? '',
      emergency_contact_name: studentProfile.emergency_contact.name,
      emergency_contact_phone: studentProfile.emergency_contact.phone,
      emergency_contact_relation: studentProfile.emergency_contact.relation ?? '',
    } : {}),
  });
  const form = useForm(initial());

  useEffect(() => {
    form.reset(initial());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, studentProfile]);

  const save = async (e) => {
    e.preventDefault();
    if (form.submitting) return;
    const res = await form.submit(
      (v) => {
        const payload = { full_name: v.full_name.trim(), phone: v.phone.trim() || null };
        if (isStudent) {
          Object.assign(payload, {
            address: v.address.trim() || null,
            emergency_contact_name: v.emergency_contact_name.trim(),
            emergency_contact_phone: v.emergency_contact_phone.trim(),
            emergency_contact_relation: v.emergency_contact_relation.trim() || null,
          });
        }
        return authService.updateMe(payload);
      },
      {
        validate: (v) => ({
          full_name: v.full_name.trim().length < 2 && 'Enter your full name.',
          phone: v.phone.trim() && !PHONE_RE.test(v.phone.trim()) && 'Enter a valid phone number.',
          ...(isStudent ? {
            emergency_contact_name: v.emergency_contact_name.trim().length < 2 && 'Enter a contact name.',
            emergency_contact_phone: !PHONE_RE.test(v.emergency_contact_phone.trim()) && 'Enter a valid phone number.',
          } : {}),
        }),
      },
    );
    if (res) {
      refreshSession(res);
      toast.success('Profile updated.');
    }
  };

  return (
    <form onSubmit={save} noValidate>
      <div className="border-b border-slate-100 px-5 py-4">
        <h2 className="text-sm font-semibold text-slate-900">Profile</h2>
        <p className="mt-0.5 text-xs text-slate-500">Details you can update yourself.</p>
      </div>
      <div className="space-y-4 px-5 py-5">
        <FormError message={form.formError} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Full name" required {...form.bind('full_name')} />
          <Input label="Phone" type="tel" {...form.bind('phone')} />
        </div>
        {isStudent && (
          <>
            <Input label="Address" {...form.bind('address')} />
            <div className="grid gap-4 sm:grid-cols-3">
              <Input label="Emergency contact" required {...form.bind('emergency_contact_name')} />
              <Input label="Contact phone" type="tel" required {...form.bind('emergency_contact_phone')} />
              <Input label="Relation" {...form.bind('emergency_contact_relation')} />
            </div>
          </>
        )}
      </div>
      <div className="flex justify-end border-t border-slate-100 bg-surface-muted px-5 py-4">
        <Button type="submit" loading={form.submitting}>Save profile</Button>
      </div>
    </form>
  );
}

export function ChangePasswordForm() {
  const { replaceToken } = useAuth();
  const toast = useToast();
  const empty = { current_password: '', new_password: '', confirm_password: '' };
  const form = useForm(empty);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (form.submitting) return;
    const res = await form.submit(
      (v) => authService.changePassword(v.current_password, v.new_password, v.confirm_password),
      {
        validate: (v) => ({
          current_password: !v.current_password && 'Enter your current password.',
          ...validatePasswordPair(v, isStrongPassword, 'new_password', 'confirm_password'),
        }),
      },
    );
    if (res) {
      replaceToken(res.access_token);
      form.reset(empty);
      toast.success('Password updated. Other sessions have been signed out.');
    }
  };

  return (
    <form onSubmit={handleSubmit} noValidate>
      <div className="border-b border-slate-100 px-5 py-4">
        <h2 className="text-sm font-semibold text-slate-900">Change password</h2>
        <p className="mt-0.5 text-xs text-slate-500">You stay signed in here; other devices are signed out.</p>
      </div>
      <div className="space-y-4 px-5 py-5">
        <FormError message={form.formError} />
        <Input label="Current password" type="password" required autoComplete="current-password" {...form.bind('current_password')} />
        <PasswordFields form={form} field="new_password" confirm="confirm_password" label="New password" />
      </div>
      <div className="flex justify-end border-t border-slate-100 bg-surface-muted px-5 py-4">
        <Button type="submit" loading={form.submitting}>Update password</Button>
      </div>
    </form>
  );
}

/** Standalone /change-password page (also used when linked from emails/menus). */
export function ChangePasswordPage() {
  return (
    <>
      <PageHeader title="Change password" description="Choose a strong password you don't use anywhere else." />
      <div className="max-w-2xl"><Card><ChangePasswordForm /></Card></div>
    </>
  );
}

