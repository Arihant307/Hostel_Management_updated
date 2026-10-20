import { useEffect, useState } from 'react';
import Modal from './ui/Modal.jsx';
import Button from './ui/Button.jsx';
import Input from './ui/Input.jsx';
import { FormError } from './ui/Misc.jsx';
import { Skeleton } from './ui/States.jsx';
import useForm from '../hooks/useForm.js';
import { staffService } from '../services/authService.js';
import { ROLE_LABELS, formatDateTime } from '../utils/format.js';

/** Account-management building blocks shared by the staff and student pages. */

export function HistoryModal({ user, onClose, loader = staffService.history }) {
  const [items, setItems] = useState(null);
  useEffect(() => {
    if (!user) return;
    setItems(null);
    loader(user.id, { per_page: 50 }).then((d) => setItems(d.items)).catch(() => setItems([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);
  return (
    <Modal open={Boolean(user)} onClose={onClose} title="Account history" size="lg"
      description={user ? `${user.full_name}: account changes, newest first.` : undefined}>
      {items === null ? <Skeleton className="h-32 w-full" /> : items.length === 0 ? (
        <p className="text-sm text-slate-500">No recorded changes.</p>
      ) : <AuditTimeline items={items} />}
    </Modal>
  );
}

export function AuditTimeline({ items }) {
  return (
    <ol className="space-y-3">
      {items.map((a) => (
        <li key={a.id} className="rounded-lg border border-slate-100 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">{a.action}</code>
            <span className="text-xs text-slate-500">{formatDateTime(a.created_at)}</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">by {a.actor ? `${a.actor.full_name} (${ROLE_LABELS[a.actor.role]})` : 'system'}</p>
          {Object.keys(a.details).length > 0 && (
            <p className="mt-1 break-all font-mono text-xs text-slate-500">{JSON.stringify(a.details)}</p>
          )}
        </li>
      ))}
    </ol>
  );
}

export function ReasonModal({ open, title, description, action, onClose, onSubmit, onDone }) {
  const form = useForm({ reason: '' });
  useEffect(() => {
    if (open) form.reset({ reason: '' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  const save = async (e) => {
    e.preventDefault();
    const res = await form.submit(async (v) => { await onSubmit(v.reason.trim()); return true; },
      { validate: (v) => ({ reason: v.reason.trim().length < 3 && 'Give a short reason (at least 3 characters).' }) });
    if (res) onDone();
  };
  return (
    <Modal open={open} onClose={form.submitting ? undefined : onClose} title={title} description={description} size="sm"
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={form.submitting}>Cancel</Button>
        <Button variant="danger" type="submit" form="reason-form" loading={form.submitting}>{action}</Button>
      </>}>
      <form id="reason-form" onSubmit={save} noValidate className="space-y-3">
        <FormError message={form.formError} />
        <Input label="Reason" required {...form.bind('reason')} />
      </form>
    </Modal>
  );
}
