import { useEffect, useState } from 'react';
import { CalendarClock, Megaphone, Pencil, Pin, Plus, Search, Trash2 } from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext.jsx';
import { useToast } from '../features/toast/ToastContext.jsx';
import { noticeService } from '../services/resources.js';
import { getErrorMessage } from '../services/api.js';
import usePaginatedList from '../hooks/usePaginatedList.js';
import useForm from '../hooks/useForm.js';
import PageHeader from '../components/PageHeader.jsx';
import ListToolbar, { toOptions } from '../components/ListToolbar.jsx';
import { label } from '../components/StatusBadge.jsx';
import Card from '../components/ui/Card.jsx';
import Badge from '../components/ui/Badge.jsx';
import Button from '../components/ui/Button.jsx';
import Input, { Select } from '../components/ui/Input.jsx';
import Textarea from '../components/ui/Textarea.jsx';
import Modal from '../components/ui/Modal.jsx';
import ConfirmDialog from '../components/ui/ConfirmDialog.jsx';
import { Pagination } from '../components/ui/DataTable.jsx';
import { FormError } from '../components/ui/Misc.jsx';
import { EmptyState, ErrorState, Skeleton } from '../components/ui/States.jsx';
import { formatDateTime } from '../utils/format.js';

const CATEGORIES = ['general', 'maintenance', 'fees', 'event', 'emergency'];
const CATEGORY_TONE = { emergency: 'danger', fees: 'warning', maintenance: 'navy', event: 'success', general: 'neutral' };

/** ISO (UTC) -> value for <input type="datetime-local"> in local time. */
function toLocalInput(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
/** datetime-local value (local time) -> ISO UTC string for the API. */
const toUtc = (local) => (local ? new Date(local).toISOString() : null);

function noticeState(n) {
  const now = Date.now();
  if (new Date(n.publish_at).getTime() > now) return ['Scheduled', 'warning'];
  if (n.expires_at && new Date(n.expires_at).getTime() <= now) return ['Expired', 'neutral'];
  return ['Live', 'success'];
}

export default function NoticesPage() {
  const { user } = useAuth();
  const isStaff = user.role !== 'student';
  const canPublish = user.role === 'admin' || user.role === 'warden';
  const toast = useToast();
  const [editing, setEditing] = useState(null); // null | 'new' | notice
  const [deleting, setDeleting] = useState(null);
  const [busy, setBusy] = useState(false);
  const list = usePaginatedList(noticeService.list, { initialFilters: { category: '', state: '', audience: '' }, perPage: 10 });

  const remove = async () => {
    setBusy(true);
    try {
      await noticeService.remove(deleting.id);
      toast.success('Notice deleted.');
      setDeleting(null);
      list.reload();
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Notice board"
        description={canPublish ? 'Publish announcements to residents and staff.' : 'Announcements from the hostel office.'}
        actions={canPublish && <Button icon={Plus} onClick={() => setEditing('new')}>New notice</Button>}
      />
      <Card>
        <ListToolbar
          list={list}
          placeholder="Search notices"
          filters={[
            { key: 'category', label: 'All categories', options: toOptions(CATEGORIES, label) },
            ...(isStaff ? [
              { key: 'state', label: 'Any state', options: [{ value: 'active', label: 'Live' }, { value: 'scheduled', label: 'Scheduled' }, { value: 'expired', label: 'Expired' }] },
              { key: 'audience', label: 'Any audience', options: [{ value: 'all', label: 'Everyone' }, { value: 'students', label: 'Students' }, { value: 'staff', label: 'Staff only' }] },
            ] : []),
          ]}
        />
        <div className="divide-y divide-slate-100">
          {list.error && <ErrorState message={list.error} onRetry={list.reload} />}
          {!list.error && list.loading && !list.items.length && [1, 2, 3].map((i) => <div key={i} className="p-5"><Skeleton className="h-16 w-full" /></div>)}
          {!list.error && !list.loading && !list.items.length && (
            list.hasFilters
              ? <EmptyState icon={Search} title="No matching notices" message="Try different filters." />
              : <EmptyState icon={Megaphone} title="No notices" message={canPublish ? 'Publish the first announcement.' : 'There are no announcements right now.'} />
          )}
          {list.items.map((n) => {
            const [stateLabel, stateTone] = noticeState(n);
            return (
              <article key={n.id} className={`p-5 ${n.is_pinned ? 'bg-navy-50/30' : ''}`}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900">
                      {n.is_pinned && <Pin className="h-4 w-4 text-navy-600" aria-label="Pinned" />}
                      {n.title}
                    </h2>
                    <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      <Badge tone={CATEGORY_TONE[n.category]}>{label(n.category)}</Badge>
                      {isStaff && <Badge tone={stateTone}>{stateLabel}</Badge>}
                      {isStaff && n.audience !== 'all' && <Badge tone="neutral">{n.audience === 'staff' ? 'Staff only' : 'Students only'}</Badge>}
                      <span>{formatDateTime(n.publish_at)}{n.created_by ? ` · ${n.created_by}` : ''}</span>
                      {n.expires_at && <span className="inline-flex items-center gap-1"><CalendarClock className="h-3 w-3" /> until {formatDateTime(n.expires_at)}</span>}
                    </p>
                  </div>
                  {canPublish && (
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" icon={Pencil} onClick={() => setEditing(n)} aria-label={`Edit ${n.title}`} />
                      <Button variant="ghost" size="sm" icon={Trash2} className="text-rose-600 hover:bg-rose-50" onClick={() => setDeleting(n)} aria-label={`Delete ${n.title}`} />
                    </div>
                  )}
                </div>
                <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-slate-700">{n.body}</p>
              </article>
            );
          })}
        </div>
        {list.pagination && list.pagination.total > 0 && <Pagination pagination={list.pagination} onPageChange={list.setPage} />}
      </Card>

      <NoticeFormModal notice={editing === 'new' ? null : editing} open={Boolean(editing)} onClose={() => setEditing(null)}
        onSaved={() => { toast.success(editing === 'new' ? 'Notice published.' : 'Notice updated.'); setEditing(null); list.reload(); }} />
      <ConfirmDialog open={Boolean(deleting)} title="Delete notice?" message={`"${deleting?.title}" will be removed for everyone.`}
        confirmLabel="Delete" tone="danger" loading={busy} onConfirm={remove} onCancel={() => setDeleting(null)} />
    </>
  );
}

function NoticeFormModal({ open, notice, onClose, onSaved }) {
  const empty = { title: '', body: '', category: 'general', audience: 'all', is_pinned: false, publish_at: '', expires_at: '' };
  const form = useForm(empty);

  useEffect(() => {
    if (!open) return;
    form.reset(notice ? {
      title: notice.title, body: notice.body, category: notice.category, audience: notice.audience, is_pinned: notice.is_pinned,
      publish_at: toLocalInput(notice.publish_at), expires_at: toLocalInput(notice.expires_at),
    } : empty);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, notice]);

  const save = async (e) => {
    e.preventDefault();
    const result = await form.submit(
      (v) => {
        const payload = {
          title: v.title.trim(), body: v.body.trim(), category: v.category, audience: v.audience, is_pinned: Boolean(v.is_pinned),
          expires_at: toUtc(v.expires_at),
          ...(v.publish_at ? { publish_at: toUtc(v.publish_at) } : {}),
        };
        return notice ? noticeService.update(notice.id, payload) : noticeService.create(payload);
      },
      { validate: (v) => ({
        title: v.title.trim().length < 3 && 'Enter a title.',
        body: v.body.trim().length < 3 && 'Write the notice.',
        expires_at: v.expires_at && new Date(v.expires_at) <= (v.publish_at ? new Date(v.publish_at) : new Date()) && 'Must be after the publish time.',
      }) },
    );
    if (result) onSaved(result);
  };

  return (
    <Modal open={open} onClose={form.submitting ? undefined : onClose} title={notice ? 'Edit notice' : 'New notice'} size="lg"
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={form.submitting}>Cancel</Button>
        <Button type="submit" form="notice-form" loading={form.submitting}>{notice ? 'Save' : 'Publish'}</Button>
      </>}>
      <form id="notice-form" onSubmit={save} className="space-y-4" noValidate>
        <FormError message={form.formError} />
        <Input label="Title" required {...form.bind('title')} />
        <Textarea label="Message" required rows={6} {...form.bind('body')} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Category" {...form.bind('category')}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{label(c)}</option>)}
          </Select>
          <Select label="Audience" {...form.bind('audience')}>
            <option value="all">Everyone</option>
            <option value="students">Students only</option>
            <option value="staff">Staff only</option>
          </Select>
          <Input label="Publish at" type="datetime-local" {...form.bind('publish_at')} hint="Leave empty to publish now." />
          <Input label="Expires at" type="datetime-local" {...form.bind('expires_at')} hint="Optional. Hidden from students after this." />
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" className="h-4 w-4 rounded border-slate-300 text-navy-700 focus:ring-navy-500" {...form.bind('is_pinned', { type: 'checkbox' })} />
          Pin to the top of the notice board
        </label>
      </form>
    </Modal>
  );
}
