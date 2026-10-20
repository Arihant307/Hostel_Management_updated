import { useEffect, useState } from 'react';
import Modal from './ui/Modal.jsx';
import Button from './ui/Button.jsx';
import Input from './ui/Input.jsx';
import { useToast } from '../features/toast/ToastContext.jsx';
import { getErrorMessage, getFieldErrors } from '../services/api.js';
import { PASSWORD_RULES, isStrongPassword } from '../utils/password.js';

/** Set a new temporary password for `user` via `onReset(id, password)`. */
export default function ResetPasswordModal({ user, onReset, onClose }) {
  const toast = useToast();
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setPassword('');
    setError('');
  }, [user]);

  const submit = async (e) => {
    e.preventDefault();
    if (!isStrongPassword(password)) {
      setError('Password does not meet the requirements.');
      return;
    }
    setSaving(true);
    try {
      await onReset(user.id, password);
      toast.success(`Password reset for ${user.full_name}. They have been signed out everywhere.`);
      onClose();
    } catch (err) {
      setError(getFieldErrors(err).password || getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={Boolean(user)}
      onClose={saving ? undefined : onClose}
      title="Reset password"
      description={user ? `Set a new temporary password for ${user.full_name}.` : undefined}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button type="submit" form="reset-password-form" loading={saving}>Reset password</Button>
        </>
      }
    >
      <form id="reset-password-form" onSubmit={submit} noValidate>
        <Input
          label="New password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            setError('');
          }}
          error={error}
          hint={PASSWORD_RULES.map((r) => r.label).join(' · ')}
        />
      </form>
    </Modal>
  );
}
