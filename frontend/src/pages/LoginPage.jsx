import { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext.jsx';
import { getErrorMessage, getFieldErrors } from '../services/api.js';
import AuthLayout from '../components/AuthLayout.jsx';
import Input from '../components/ui/Input.jsx';
import Button from '../components/ui/Button.jsx';
import { FormError } from '../components/ui/Misc.jsx';

// Only the email address is remembered (never a token or password).
const REMEMBER_KEY = 'hms.remembered_email';
const readRemembered = () => {
  try {
    return window.localStorage.getItem(REMEMBER_KEY) || '';
  } catch {
    return '';
  }
};
const writeRemembered = (email) => {
  try {
    if (email) window.localStorage.setItem(REMEMBER_KEY, email);
    else window.localStorage.removeItem(REMEMBER_KEY);
  } catch {
    /* storage unavailable: nothing to remember */
  }
};

export default function LoginPage() {
  const { status, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const remembered = readRemembered();
  const [form, setForm] = useState({ email: remembered, password: '' });
  const [remember, setRemember] = useState(Boolean(remembered));
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const notice = location.state?.notice;

  if (status === 'authenticated') {
    return <Navigate to={location.state?.from?.pathname || '/dashboard'} replace />;
  }

  const update = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
    setFieldErrors((fe) => ({ ...fe, [field]: undefined }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (submitting) return;
    const errors = {};
    if (!form.email.trim()) errors.email = 'Enter your email address.';
    if (!form.password) errors.password = 'Enter your password.';
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;

    setSubmitting(true);
    setError('');
    const email = form.email.trim();
    try {
      await login(email, form.password);
      writeRemembered(remember ? email : '');
      // Every role lands on /dashboard, which renders the right dashboard
      // for the role the *server* returned.
      navigate(location.state?.from?.pathname || '/dashboard', { replace: true });
    } catch (err) {
      const code = err?.response?.data?.error?.code;
      if (code === 'email_unverified') {
        navigate(`/verify-email?email=${encodeURIComponent(email)}`, { replace: true });
        return;
      }
      if (code === 'account_pending') {
        navigate('/account-pending', { replace: true });
        return;
      }
      if (code === 'account_disabled' || code === 'account_rejected') {
        navigate(`/account-disabled?reason=${code === 'account_rejected' ? 'rejected' : 'disabled'}`, { replace: true });
        return;
      }
      setFieldErrors(getFieldErrors(err));
      setError(getErrorMessage(err));
      setForm((f) => ({ ...f, password: '' }));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Students and hostel staff sign in with the same form."
      footer={
        <>
          New here?{' '}
          <Link to="/signup" className="font-medium text-navy-700 hover:text-navy-900">
            Create an account
          </Link>
        </>
      }
    >
      {notice && (
        <div role="status" className="mb-5 rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-3 text-sm text-emerald-800">
          {notice}
        </div>
      )}
      <FormError message={error} />
      <form onSubmit={handleSubmit} className="mt-5 space-y-5" noValidate>
        <Input
          label="Email address"
          type="email"
          autoComplete="email"
          placeholder="you@college.edu"
          value={form.email}
          onChange={update('email')}
          error={fieldErrors.email}
          autoFocus={!remembered}
        />
        <div>
          <Input
            label="Password"
            type="password"
            autoComplete="current-password"
            value={form.password}
            onChange={update('password')}
            error={fieldErrors.password}
            autoFocus={Boolean(remembered)}
          />
          <div className="mt-2 flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-navy-700 focus:ring-navy-500"
              />
              Remember my email
            </label>
            <Link to="/forgot-password" className="text-sm font-medium text-navy-700 hover:text-navy-900">
              Forgot password?
            </Link>
          </div>
        </div>
        <Button type="submit" size="lg" className="w-full" loading={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </AuthLayout>
  );
}
