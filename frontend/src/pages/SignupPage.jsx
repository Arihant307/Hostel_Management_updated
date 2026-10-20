import { useEffect, useState } from 'react';
import { Link, Navigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, BadgeCheck, Briefcase, CheckCircle2, GraduationCap, KeyRound, MailCheck } from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext.jsx';
import { authService } from '../services/authService.js';
import { getErrorMessage } from '../services/api.js';
import useForm from '../hooks/useForm.js';
import AuthLayout, { AuthStatus } from '../components/AuthLayout.jsx';
import PasswordFields, { validatePasswordPair } from '../components/PasswordFields.jsx';
import Input, { Select } from '../components/ui/Input.jsx';
import Button from '../components/ui/Button.jsx';
import { FormError } from '../components/ui/Misc.jsx';
import { isStrongPassword } from '../utils/password.js';

const PHONE_RE = /^\+?[0-9][0-9\s-]{6,18}[0-9]$/;
const EMAIL_RE = /^\S+@\S+\.\S+$/;

export default function SignupPage() {
  const { status } = useAuth();
  const [params, setParams] = useSearchParams();
  const [policy, setPolicy] = useState(null);
  const [result, setResult] = useState(null);
  const type = params.get('type'); // 'student' | 'staff' | null

  useEffect(() => {
    authService.signupPolicy().then(setPolicy).catch(() => setPolicy({}));
  }, []);

  if (status === 'authenticated') return <Navigate to="/dashboard" replace />;

  const choose = (t) => setParams(t ? { type: t, ...(params.get('code') ? { code: params.get('code') } : {}) } : {});

  if (result) {
    return (
      <AuthLayout>
        <SignupSuccess result={result} />
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      wide
      title={type ? (type === 'student' ? 'Student registration' : 'Staff registration') : 'Create an account'}
      subtitle={type ? null : 'What type of account do you want to create?'}
      footer={<>Already have an account? <Link to="/login" className="font-medium text-navy-700 hover:text-navy-900">Sign in</Link></>}
    >
      {!type && <AccountTypePicker onChoose={choose} policy={policy} />}
      {type && (
        <button type="button" onClick={() => choose(null)} className="mb-5 inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800">
          <ArrowLeft className="h-4 w-4" /> Change account type
        </button>
      )}
      {type === 'student' && (policy?.student_signup_enabled === false
        ? <FormError message="Student self-registration is currently closed. Please contact the hostel office." />
        : <StudentSignupForm policy={policy} onDone={setResult} />)}
      {type === 'staff' && <StaffSignupForm policy={policy} initialCode={params.get('code') || ''} onDone={setResult} />}
    </AuthLayout>
  );
}

function AccountTypePicker({ onChoose, policy }) {
  const cards = [
    {
      key: 'student', icon: GraduationCap, title: 'Student Account',
      text: 'For students who want to register for hostel accommodation and access the student portal.',
      disabled: policy?.student_signup_enabled === false,
    },
    {
      key: 'staff', icon: Briefcase, title: 'Staff Account',
      text: 'For authorized hostel staff, wardens and administrative employees. Requires an invitation or administrator approval.',
    },
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-2" role="radiogroup" aria-label="Account type">
      {cards.map(({ key, icon: Icon, title, text, disabled }) => (
        <button
          key={key}
          type="button"
          role="radio"
          aria-checked="false"
          disabled={disabled}
          onClick={() => onChoose(key)}
          className="group rounded-xl border border-slate-200 bg-white p-5 text-left shadow-card transition-all hover:border-navy-300 hover:shadow-raised focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-navy-50 text-navy-700 transition-colors group-hover:bg-navy-800 group-hover:text-white">
            <Icon className="h-5 w-5" />
          </span>
          <span className="mt-4 block text-base font-semibold text-slate-900">{title}</span>
          <span className="mt-1 block text-sm leading-relaxed text-slate-500">{text}</span>
          {disabled && <span className="mt-2 block text-xs font-medium text-rose-600">Registration is currently closed.</span>}
        </button>
      ))}
    </div>
  );
}

function TermsCheckbox({ form }) {
  const binding = form.bind('accept_terms', { type: 'checkbox' });
  return (
    <div>
      <label className="flex items-start gap-2.5 text-sm text-slate-600">
        <input type="checkbox" {...binding} error={undefined}
          className="mt-0.5 h-4 w-4 rounded border-slate-300 text-navy-700 focus:ring-navy-500" />
        <span>
          I agree to the hostel <span className="font-medium text-slate-800">terms of residence</span> and the{' '}
          <span className="font-medium text-slate-800">privacy policy</span>, and confirm the details I entered are accurate.
        </span>
      </label>
      {form.errors.accept_terms && <p className="mt-1.5 text-xs text-rose-600">{form.errors.accept_terms}</p>}
    </div>
  );
}

const STUDENT_EMPTY = {
  full_name: '', student_code: '', email: '', phone: '', course: '', department: '', academic_year: '1',
  emergency_contact_name: '', emergency_contact_phone: '', emergency_contact_relation: '',
  password: '', confirm_password: '', accept_terms: false,
};

function StudentSignupForm({ policy, onDone }) {
  const form = useForm(STUDENT_EMPTY);

  const submit = async (e) => {
    e.preventDefault();
    if (form.submitting) return;
    const res = await form.submit(
      (v) => authService.signupStudent({
        ...v,
        full_name: v.full_name.trim(), student_code: v.student_code.trim(), email: v.email.trim(),
        phone: v.phone.trim(), course: v.course.trim(), department: v.department.trim(),
        academic_year: Number(v.academic_year), emergency_contact_name: v.emergency_contact_name.trim(),
        emergency_contact_phone: v.emergency_contact_phone.trim(),
        emergency_contact_relation: v.emergency_contact_relation.trim() || null,
      }),
      {
        validate: (v) => ({
          full_name: v.full_name.trim().length < 2 && 'Enter your full name.',
          student_code: v.student_code.trim().length < 2 && 'Enter your student ID.',
          email: !EMAIL_RE.test(v.email.trim()) && 'Enter a valid email address.',
          phone: !PHONE_RE.test(v.phone.trim()) && 'Enter a valid phone number.',
          course: !v.course.trim() && 'Enter your course.',
          department: !v.department.trim() && 'Enter your department.',
          emergency_contact_name: v.emergency_contact_name.trim().length < 2 && 'Enter a contact name.',
          emergency_contact_phone: !PHONE_RE.test(v.emergency_contact_phone.trim()) && 'Enter a valid phone number.',
          ...validatePasswordPair(v, isStrongPassword),
          accept_terms: !v.accept_terms && 'You must accept the terms to continue.',
        }),
      },
    );
    if (res) onDone({ ...res.data, message: res.message, policy });
  };

  return (
    <form onSubmit={submit} className="space-y-6" noValidate>
      <FormError message={form.formError} />
      <Section title="Your details">
        <Input label="Full name" required autoComplete="name" {...form.bind('full_name')} />
        <Input label="Student ID / registration number" required {...form.bind('student_code')} placeholder="e.g. CS2026-014" />
        <Input label="College email" type="email" required autoComplete="email" {...form.bind('email')} placeholder="you@college.edu"
          hint="We will send a verification link to this address." />
        <Input label="Phone number" type="tel" required autoComplete="tel" {...form.bind('phone')} />
      </Section>
      <Section title="Academic">
        <Input label="Course" required {...form.bind('course')} placeholder="B.Tech" />
        <Input label="Department" required {...form.bind('department')} placeholder="Computer Science" />
        <Select label="Academic year" required {...form.bind('academic_year')}>
          {[1, 2, 3, 4, 5, 6].map((y) => <option key={y} value={y}>Year {y}</option>)}
        </Select>
      </Section>
      <Section title="Emergency contact">
        <Input label="Contact name" required {...form.bind('emergency_contact_name')} />
        <Input label="Contact phone" type="tel" required {...form.bind('emergency_contact_phone')} />
        <Input label="Relation" {...form.bind('emergency_contact_relation')} placeholder="Parent" />
      </Section>
      <Section title="Password" single>
        <PasswordFields form={form} />
      </Section>
      <TermsCheckbox form={form} />
      <Button type="submit" size="lg" className="w-full" loading={form.submitting}>Create student account</Button>
      <p className="text-center text-xs text-slate-500">
        {policy?.student_approval_required !== false
          ? 'After you verify your email, the hostel office reviews your registration before you can sign in.'
          : 'After you verify your email you can sign in straight away.'}
        {' '}Rooms are allocated separately by the hostel office.
      </p>
    </form>
  );
}

const STAFF_EMPTY = {
  full_name: '', email: '', phone: '', employee_id: '', department: '', requested_role: 'staff',
  invitation_code: '', password: '', confirm_password: '', accept_terms: false,
};

function StaffSignupForm({ policy, initialCode, onDone }) {
  const form = useForm({ ...STAFF_EMPTY, invitation_code: initialCode });
  const [invite, setInvite] = useState(null); // validated invitation {email, role}
  const [checking, setChecking] = useState(false);
  const [inviteError, setInviteError] = useState('');

  const checkCode = async (code) => {
    const trimmed = (code ?? form.values.invitation_code).trim();
    if (!trimmed) return;
    setChecking(true);
    setInviteError('');
    try {
      const inv = await authService.validateInvitation(trimmed);
      setInvite(inv);
      form.setValues((v) => ({ ...v, invitation_code: trimmed, email: inv.email, requested_role: inv.role }));
    } catch (err) {
      setInvite(null);
      setInviteError(getErrorMessage(err));
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    if (initialCode) checkCode(initialCode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openSignupClosed = policy?.staff_signup_enabled === false;

  const submit = async (e) => {
    e.preventDefault();
    if (form.submitting) return;
    const res = await form.submit(
      (v) => authService.signupStaff({
        full_name: v.full_name.trim(), email: v.email.trim(), phone: v.phone.trim(),
        employee_id: v.employee_id.trim(), department: v.department.trim(),
        requested_role: v.requested_role, invitation_code: v.invitation_code.trim() || null,
        password: v.password, confirm_password: v.confirm_password, accept_terms: v.accept_terms,
      }),
      {
        validate: (v) => ({
          full_name: v.full_name.trim().length < 2 && 'Enter your full name.',
          email: !EMAIL_RE.test(v.email.trim()) && 'Enter your official email.',
          phone: !PHONE_RE.test(v.phone.trim()) && 'Enter a valid phone number.',
          employee_id: v.employee_id.trim().length < 2 && 'Enter your employee ID.',
          department: !v.department.trim() && 'Enter your department.',
          invitation_code: openSignupClosed && !v.invitation_code.trim() && 'An invitation code is required.',
          ...validatePasswordPair(v, isStrongPassword),
          accept_terms: !v.accept_terms && 'You must accept the terms to continue.',
        }),
      },
    );
    if (res) onDone({ ...res.data, message: res.message, invited: Boolean(invite) });
  };

  return (
    <form onSubmit={submit} className="space-y-6" noValidate>
      <FormError message={form.formError} />
      <div className="rounded-xl border border-slate-200 bg-surface-muted p-4">
        <div className="flex items-start gap-3">
          <KeyRound className="mt-0.5 h-5 w-5 shrink-0 text-navy-600" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-slate-900">Invitation code {openSignupClosed ? '' : '(optional)'}</p>
            <p className="mt-0.5 text-xs text-slate-500">
              {openSignupClosed
                ? 'Staff accounts can only be created with an invitation from an administrator.'
                : 'With an invitation your account is ready as soon as you verify your email. Without one, an administrator reviews your application.'}
            </p>
            {invite ? (
              <p className="mt-3 flex items-center gap-2 text-sm text-emerald-700">
                <BadgeCheck className="h-4 w-4" /> Valid invitation for <strong>{invite.email}</strong> as <strong>{invite.role}</strong>.
                <button type="button" className="ml-auto text-xs font-medium text-slate-500 hover:text-slate-800"
                  onClick={() => { setInvite(null); form.setValues((v) => ({ ...v, invitation_code: '' })); }}>
                  Remove
                </button>
              </p>
            ) : (
              <div className="mt-3 flex gap-2">
                <div className="flex-1">
                  <Input aria-label="Invitation code" {...form.bind('invitation_code')} placeholder="Paste your invitation code"
                    error={inviteError || form.errors.invitation_code} />
                </div>
                <Button variant="secondary" onClick={() => checkCode()} loading={checking} disabled={!form.values.invitation_code.trim()}>
                  Check
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>

      <Section title="Your details">
        <Input label="Full name" required autoComplete="name" {...form.bind('full_name')} />
        <Input label="Official email" type="email" required autoComplete="email" {...form.bind('email')}
          disabled={Boolean(invite)} hint={invite ? 'Fixed by your invitation.' : undefined} />
        <Input label="Phone number" type="tel" required autoComplete="tel" {...form.bind('phone')} />
        <Input label="Employee ID" required {...form.bind('employee_id')} />
        <Input label="Department" required {...form.bind('department')} placeholder="Hostel administration" />
        <Select label="Requested position" required {...form.bind('requested_role')} disabled={Boolean(invite)}
          hint={invite ? 'Set by your invitation.' : 'An administrator confirms your role when approving.'}>
          <option value="staff">Staff</option>
          <option value="warden">Warden</option>
        </Select>
      </Section>
      <Section title="Password" single>
        <PasswordFields form={form} />
      </Section>
      <TermsCheckbox form={form} />
      <Button type="submit" size="lg" className="w-full" loading={form.submitting}>
        {invite ? 'Create staff account' : 'Submit staff application'}
      </Button>
    </form>
  );
}

function Section({ title, single, children }) {
  return (
    <fieldset>
      <legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</legend>
      <div className={single ? '' : 'grid gap-4 sm:grid-cols-2'}>{children}</div>
    </fieldset>
  );
}

function SignupSuccess({ result }) {
  const steps = [];
  if (result.verification_required) steps.push(`Open the verification link we sent to ${result.email}. The link works once and expires after a limited time.`);
  if (result.approval_required) {
    steps.push(result.account_type === 'staff'
      ? 'An administrator will review your application and assign your role.'
      : 'The hostel office will review your registration.');
    steps.push('You will receive an email when your account is approved.');
  }
  steps.push(result.account_type === 'student'
    ? 'Once you can sign in, your room and fees will appear on your dashboard after the office allocates them.'
    : 'Then sign in to reach your staff dashboard.');

  return (
    <AuthStatus
      icon={result.verification_required ? MailCheck : CheckCircle2}
      tone="green"
      title={result.verification_required ? 'Check your email' : 'Account created'}
      actions={
        <>
          {result.verification_required && (
            <Link to={`/verify-email?email=${encodeURIComponent(result.email)}`}>
              <Button variant="secondary" className="w-full">I didn't get the email</Button>
            </Link>
          )}
          <Link to="/login"><Button className="w-full">Go to sign in</Button></Link>
        </>
      }
    >
      <p>{result.message}</p>
      <ol className="mx-auto max-w-sm space-y-2 text-left">
        {steps.map((s, i) => (
          <li key={s} className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-navy-50 text-xs font-semibold text-navy-700">{i + 1}</span>
            <span>{s}</span>
          </li>
        ))}
      </ol>
    </AuthStatus>
  );
}
