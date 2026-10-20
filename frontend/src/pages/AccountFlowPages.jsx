/**
 * Public account-flow pages: verify email, forgot password, reset password,
 * pending approval and disabled account. Each one talks to the real API and
 * only shows success after the server confirms it.
 */
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Ban, Clock, KeyRound, Loader2, MailCheck, MailWarning, ShieldCheck, XCircle } from 'lucide-react';
import { authService } from '../services/authService.js';
import { useAuth } from '../features/auth/AuthContext.jsx';
import { getErrorMessage } from '../services/api.js';
import useForm from '../hooks/useForm.js';
import AuthLayout, { AuthStatus } from '../components/AuthLayout.jsx';
import PasswordFields, { validatePasswordPair } from '../components/PasswordFields.jsx';
import Input from '../components/ui/Input.jsx';
import Button from '../components/ui/Button.jsx';
import { FormError } from '../components/ui/Misc.jsx';
import { isStrongPassword } from '../utils/password.js';

const EMAIL_RE = /^\S+@\S+\.\S+$/;
const SpinningLoader = ({ className = '' }) => <Loader2 className={`${className} animate-spin`} aria-hidden="true" />;

/** Small form that asks for an email and calls `action(email)`. */
function EmailRequestForm({ initialEmail = '', action, buttonLabel, onSent }) {
  const form = useForm({ email: initialEmail });
  const submit = async (e) => {
    e.preventDefault();
    if (form.submitting) return;
    const res = await form.submit((v) => action(v.email.trim()), {
      validate: (v) => ({ email: !EMAIL_RE.test(v.email.trim()) && 'Enter a valid email address.' }),
    });
    if (res) onSent(res.message);
  };
  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <FormError message={form.formError} />
      <Input label="Email address" type="email" autoComplete="email" required {...form.bind('email')} autoFocus />
      <Button type="submit" size="lg" className="w-full" loading={form.submitting}>{buttonLabel}</Button>
    </form>
  );
}

// --- Verify email -------------------------------------------------------------

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const [state, setState] = useState(token ? { status: 'verifying' } : { status: 'waiting' });
  const [sentMessage, setSentMessage] = useState('');
  const ran = useRef(false);

  useEffect(() => {
    if (!token || ran.current) return; // StrictMode double-run guard: tokens are single-use
    ran.current = true;
    authService.verifyEmail(token)
      .then((res) => setState({ status: 'verified', message: res.message, pending: res.data.approval_required }))
      .catch((err) => setState({ status: 'failed', message: getErrorMessage(err) }));
  }, [token]);

  if (state.status === 'verifying') {
    return (
      <AuthLayout>
        <AuthStatus icon={SpinningLoader} title="Verifying your email…">
          <p>This only takes a moment.</p>
        </AuthStatus>
      </AuthLayout>
    );
  }
  if (state.status === 'verified') {
    return (
      <AuthLayout>
        <AuthStatus icon={ShieldCheck} tone="green" title="Email verified"
          actions={<Link to="/login"><Button className="w-full">{state.pending ? 'Back to sign in' : 'Sign in'}</Button></Link>}>
          <p>{state.message}</p>
          {state.pending && <p>We'll email you as soon as the hostel office approves your account.</p>}
        </AuthStatus>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      {state.status === 'failed' ? (
        <AuthStatus icon={XCircle} tone="rose" title="Link not valid">
          <p>{state.message}</p>
          <p>Enter your email below and we'll send you a fresh verification link.</p>
        </AuthStatus>
      ) : (
        <AuthStatus icon={MailCheck} title="Verify your email">
          <p>
            We sent a verification link to {params.get('email') ? <strong>{params.get('email')}</strong> : 'your email address'}.
            Open it to activate your account.
          </p>
          <p>Didn't get it? Check your spam folder, or request a new link.</p>
        </AuthStatus>
      )}
      <div className="mt-8">
        {sentMessage ? (
          <div role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-3 text-sm text-emerald-800">{sentMessage}</div>
        ) : (
          <EmailRequestForm initialEmail={params.get('email') || ''} action={authService.resendVerification}
            buttonLabel="Send a new verification link" onSent={setSentMessage} />
        )}
        <p className="mt-6 text-center text-sm"><Link to="/login" className="font-medium text-navy-700 hover:text-navy-900">Back to sign in</Link></p>
      </div>
    </AuthLayout>
  );
}

// --- Forgot password ----------------------------------------------------------

export function ForgotPasswordPage() {
  const [sent, setSent] = useState('');
  return (
    <AuthLayout
      title={sent ? null : 'Forgot your password?'}
      subtitle={sent ? null : "Enter your account's email address and we'll send you a link to choose a new password."}
      footer={<Link to="/login" className="font-medium text-navy-700 hover:text-navy-900">Back to sign in</Link>}
    >
      {sent ? (
        <AuthStatus icon={MailCheck} tone="green" title="Check your email">
          <p>{sent}</p>
          <p>The link works once and expires soon. If it doesn't arrive, you can request another in a few minutes.</p>
        </AuthStatus>
      ) : (
        <EmailRequestForm action={authService.forgotPassword} buttonLabel="Send reset link" onSent={setSent} />
      )}
    </AuthLayout>
  );
}

// --- Reset password -----------------------------------------------------------

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { status, logout } = useAuth();
  const token = params.get('token');
  const form = useForm({ password: '', confirm_password: '' });

  if (!token) {
    return (
      <AuthLayout>
        <AuthStatus icon={MailWarning} tone="amber" title="Reset link missing"
          actions={<Link to="/forgot-password"><Button className="w-full">Request a new link</Button></Link>}>
          <p>Open the link from your password reset email, or request a new one.</p>
        </AuthStatus>
      </AuthLayout>
    );
  }

  const submit = async (e) => {
    e.preventDefault();
    if (form.submitting) return;
    const res = await form.submit(
      (v) => authService.resetPassword(token, v.password, v.confirm_password),
      { validate: (v) => validatePasswordPair(v, isStrongPassword) },
    );
    if (res) {
      // If this browser tab is signed in (possibly as someone else), end that
      // session so the user signs in fresh with the new password.
      if (status === 'authenticated') await logout();
      navigate('/login', { replace: true, state: { notice: res.message } });
    }
  };

  const tokenProblem = /link/i.test(form.formError || '') || form.errors.token;

  return (
    <AuthLayout title="Choose a new password" subtitle="You'll be signed out on all devices after the change."
      footer={<Link to="/login" className="font-medium text-navy-700 hover:text-navy-900">Back to sign in</Link>}>
      <form onSubmit={submit} className="space-y-5" noValidate>
        <FormError message={form.formError || form.errors.token} />
        {tokenProblem && (
          <p className="text-sm"><Link to="/forgot-password" className="font-medium text-navy-700 hover:text-navy-900">Request a new reset link</Link></p>
        )}
        <PasswordFields form={form} label="New password" />
        <Button type="submit" size="lg" className="w-full" loading={form.submitting}>
          <KeyRound className="h-4 w-4" /> Reset password
        </Button>
      </form>
    </AuthLayout>
  );
}

// --- Pending approval / disabled ------------------------------------------------

export function AccountPendingPage() {
  return (
    <AuthLayout>
      <AuthStatus icon={Clock} tone="amber" title="Waiting for approval"
        actions={<Link to="/login"><Button variant="secondary" className="w-full">Back to sign in</Button></Link>}>
        <p>Your email is verified and your account is waiting to be approved by the hostel office.</p>
        <p>You'll get an email as soon as it is approved. Until then you can't sign in.</p>
      </AuthStatus>
    </AuthLayout>
  );
}

export function AccountDisabledPage() {
  const [params] = useSearchParams();
  const rejected = params.get('reason') === 'rejected';
  return (
    <AuthLayout>
      <AuthStatus icon={Ban} tone="rose" title={rejected ? 'Registration not approved' : 'Account deactivated'}
        actions={<Link to="/login"><Button variant="secondary" className="w-full">Back to sign in</Button></Link>}>
        <p>
          {rejected
            ? 'Your registration was reviewed and not approved. The email we sent explains why.'
            : 'This account has been deactivated, so it can no longer sign in.'}
        </p>
        <p>If you think this is a mistake, please contact the hostel office.</p>
      </AuthStatus>
    </AuthLayout>
  );
}
