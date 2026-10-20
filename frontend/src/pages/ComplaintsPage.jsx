import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Lock, MessageSquare, Plus, Search, Wrench } from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext.jsx';
import { useToast } from '../features/toast/ToastContext.jsx';
import { complaintService } from '../services/resources.js';
import { getErrorMessage } from '../services/api.js';
import usePaginatedList from '../hooks/usePaginatedList.js';
import useForm from '../hooks/useForm.js';
import PageHeader from '../components/PageHeader.jsx';
import ListToolbar, { toOptions } from '../components/ListToolbar.jsx';
import StatusBadge, { label } from '../components/StatusBadge.jsx';
import Card from '../components/ui/Card.jsx';
import Button from '../components/ui/Button.jsx';
import Input, { Select } from '../components/ui/Input.jsx';
import Textarea from '../components/ui/Textarea.jsx';
import Modal from '../components/ui/Modal.jsx';
import DataTable from '../components/ui/DataTable.jsx';
import { FormError } from '../components/ui/Misc.jsx';
import { EmptyState, Skeleton } from '../components/ui/States.jsx';
import { formatDateTime } from '../utils/format.js';

const CATEGORIES = ['plumbing', 'electrical', 'cleanliness', 'furniture', 'internet', 'other'];
const STATUSES = ['open', 'in_progress', 'resolved', 'rejected'];

export default function ComplaintsPage() {
  const { user } = useAuth();
  const isStudent = user.role === 'student';
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const openId = params.get('open');
  const list = usePaginatedList(complaintService.list, {
    initialFilters: { status: isStudent ? '' : 'active', category: '', priority: '', from: '', to: '' },
    initialSort: { key: 'created_at', order: 'desc' },
    perPage: 15,
  });

  const columns = [
    {
      key: 'title', header: 'Complaint',
      render: (c) => (
        <button type="button" onClick={() => setParams({ open: c.id })} className="text-left">
          <span className="block font-medium text-slate-900 hover:text-navy-700">{c.title}</span>
          <span className="block text-xs text-slate-500">
            {label(c.category)}{c.room ? ` · Room ${c.room.block}-${c.room.room_number}` : ''}
            {c.comments.length > 0 && <span className="ml-1 inline-flex items-center gap-0.5"><MessageSquare className="h-3 w-3" /> {c.comments.length}</span>}
          </span>
        </button>
      ),
    },
    ...(isStudent ? [] : [{
      key: 'student', header: 'Student',
      render: (c) => <span><span className="block text-slate-800">{c.student.full_name}</span><span className="block text-xs text-slate-500">{c.student.student_code}</span></span>,
    }]),
    { key: 'priority', header: 'Priority', sortable: true, className: 'hidden md:table-cell', render: (c) => <StatusBadge status={c.priority} /> },
    { key: 'assigned', header: 'Assigned to', className: 'hidden lg:table-cell', render: (c) => <span className="text-slate-600">{c.assigned_to || '—'}</span> },
    { key: 'created_at', header: 'Filed', sortable: true, className: 'hidden sm:table-cell', render: (c) => <span className="text-slate-500">{formatDateTime(c.created_at)}</span> },
    { key: 'status', header: 'Status', sortable: true, render: (c) => <StatusBadge status={c.status} /> },
  ];

  return (
    <>
      <PageHeader
        title={isStudent ? 'My complaints' : 'Complaints'}
        description={isStudent ? 'Report maintenance problems and follow their progress.' : 'Maintenance requests from residents.'}
        actions={isStudent && <Button icon={Plus} onClick={() => setCreating(true)}>New complaint</Button>}
      />
      <Card>
        <ListToolbar
          list={list}
          placeholder={isStudent ? 'Search' : 'Search title, student or ID'}
          filters={[
            { key: 'status', label: 'Any status', options: [{ value: 'active', label: 'Open & in progress' }, ...toOptions(STATUSES, label)] },
            { key: 'category', label: 'All categories', options: toOptions(CATEGORIES, label) },
            ...(isStudent ? [] : [{ key: 'priority', label: 'Any priority', options: toOptions(['high', 'medium', 'low'], label) }]),
          ]}
        >
          {!isStudent && (
            <div className="grid grid-cols-2 gap-3">
              <Input type="date" aria-label="Filed from" value={list.filters.from} onChange={(e) => list.setFilter('from', e.target.value)} />
              <Input type="date" aria-label="Filed until" value={list.filters.to} onChange={(e) => list.setFilter('to', e.target.value)} />
            </div>
          )}
        </ListToolbar>
        <DataTable
          columns={columns}
          rows={list.items}
          loading={list.loading}
          error={list.error}
          onRetry={list.reload}
          sort={list.sort}
          onSortChange={list.setSort}
          pagination={list.pagination}
          onPageChange={list.setPage}
          empty={list.hasFilters
            ? <EmptyState icon={Search} title="No matching complaints" message="Try different filters." />
            : <EmptyState icon={Wrench}
                title={isStudent ? 'No complaints' : 'No open complaints'}
                message={isStudent ? 'Something broken? File a complaint and follow its progress here.' : 'Everything reported has been handled. Change the status filter to see closed complaints.'}
                action={isStudent && <Button icon={Plus} onClick={() => setCreating(true)}>New complaint</Button>} />}
        />
      </Card>

      <NewComplaintModal open={creating} onClose={() => setCreating(false)}
        onCreated={(c) => { setCreating(false); toast.success('Complaint submitted.'); list.reload(); setParams({ open: c.id }); }} />
      <ComplaintDetailModal id={openId} isStudent={isStudent} onClose={() => setParams({})} onChanged={list.reload} />
    </>
  );
}

function NewComplaintModal({ open, onClose, onCreated }) {
  const initial = { category: 'plumbing', priority: 'medium', title: '', description: '' };
  const form = useForm(initial);
  useEffect(() => {
    if (open) form.reset(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const save = async (e) => {
    e.preventDefault();
    const result = await form.submit((v) => complaintService.create({ ...v, title: v.title.trim(), description: v.description.trim() }), {
      validate: (v) => ({
        title: v.title.trim().length < 4 && 'Give a short title (at least 4 characters).',
        description: v.description.trim().length < 10 && 'Describe the problem (at least 10 characters).',
      }),
    });
    if (result) onCreated(result);
  };

  return (
    <Modal open={open} onClose={form.submitting ? undefined : onClose} title="New complaint"
      description="Your current room is attached automatically."
      footer={<>
        <Button variant="secondary" onClick={onClose} disabled={form.submitting}>Cancel</Button>
        <Button type="submit" form="complaint-form" loading={form.submitting}>Submit</Button>
      </>}>
      <form id="complaint-form" onSubmit={save} className="space-y-4" noValidate>
        <FormError message={form.formError} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Category" required {...form.bind('category')}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{label(c)}</option>)}
          </Select>
          <Select label="Priority" {...form.bind('priority')}>
            {['low', 'medium', 'high'].map((p) => <option key={p} value={p}>{label(p)}</option>)}
          </Select>
        </div>
        <Input label="Title" required {...form.bind('title')} placeholder="e.g. Bathroom tap leaking" />
        <Textarea label="Description" required rows={5} {...form.bind('description')} placeholder="What is wrong, where, and since when?" />
      </form>
    </Modal>
  );
}

function ComplaintDetailModal({ id, isStudent, onClose, onChanged }) {
  const toast = useToast();
  const [complaint, setComplaint] = useState(null);
  const [error, setError] = useState('');
  const manage = useForm({ status: '', priority: '', assigned_to: '', resolution: '' });
  const reply = useForm({ body: '', is_internal: false });

  const apply = (c) => {
    setComplaint(c);
    manage.reset({ status: c.status, priority: c.priority, assigned_to: c.assigned_to ?? '', resolution: c.resolution ?? '' });
  };

  useEffect(() => {
    setComplaint(null);
    setError('');
    reply.reset({ body: '', is_internal: false });
    if (id) complaintService.get(id).then(apply).catch((err) => setError(getErrorMessage(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const saveManage = async (e) => {
    e.preventDefault();
    const result = await manage.submit(
      (v) => complaintService.update(complaint.id, {
        status: v.status, priority: v.priority, assigned_to: v.assigned_to.trim() || null, resolution: v.resolution.trim() || null,
      }),
      { validate: (v) => ({ resolution: ['resolved', 'rejected'].includes(v.status) && !v.resolution.trim() && 'Explain the outcome to the student.' }) },
    );
    if (result) { apply(result); toast.success('Complaint updated.'); onChanged(); }
  };

  const sendReply = async (e) => {
    e.preventDefault();
    const result = await reply.submit((v) => complaintService.comment(complaint.id, { body: v.body.trim(), is_internal: Boolean(v.is_internal) }),
      { validate: (v) => ({ body: !v.body.trim() && 'Write a message.' }) });
    if (result) { setComplaint(result); reply.reset({ body: '', is_internal: false }); onChanged(); }
  };

  return (
    <Modal open={Boolean(id)} onClose={onClose} title={complaint?.title ?? 'Complaint'} size="lg"
      description={complaint ? `${label(complaint.category)} · filed ${formatDateTime(complaint.created_at)}${complaint.student && !isStudent ? ` by ${complaint.student.full_name}` : ''}` : undefined}>
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {!complaint && !error && <Skeleton className="h-48 w-full" />}
      {complaint && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={complaint.status} />
            <StatusBadge status={complaint.priority} />
            {complaint.room && <span className="text-xs text-slate-500">Room {complaint.room.block}-{complaint.room.room_number}</span>}
            {complaint.assigned_to && <span className="text-xs text-slate-500">· Assigned to {complaint.assigned_to}</span>}
          </div>
          <p className="whitespace-pre-line text-sm text-slate-700">{complaint.description}</p>
          {complaint.resolution && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
              <p className="text-xs font-semibold uppercase tracking-wide">Resolution</p>
              <p className="mt-1 whitespace-pre-line">{complaint.resolution}</p>
            </div>
          )}

          {!isStudent && (
            <form onSubmit={saveManage} className="space-y-3 rounded-lg border border-slate-200 p-4" noValidate>
              <p className="text-sm font-semibold text-slate-900">Manage</p>
              <FormError message={manage.formError} />
              <div className="grid gap-3 sm:grid-cols-3">
                <Select label="Status" {...manage.bind('status')}>
                  {STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
                </Select>
                <Select label="Priority" {...manage.bind('priority')}>
                  {['low', 'medium', 'high'].map((p) => <option key={p} value={p}>{label(p)}</option>)}
                </Select>
                <Input label="Assigned to" {...manage.bind('assigned_to')} placeholder="Staff name" />
              </div>
              <Textarea label="Resolution (visible to student)" rows={2} {...manage.bind('resolution')}
                hint="Required when resolving or rejecting." />
              <div className="flex justify-end"><Button type="submit" loading={manage.submitting}>Save changes</Button></div>
            </form>
          )}

          <div>
            <h3 className="mb-3 text-sm font-semibold text-slate-900">Conversation</h3>
            {complaint.comments.length === 0 && <p className="text-sm text-slate-500">No replies yet.</p>}
            <ul className="space-y-3">
              {complaint.comments.map((c) => (
                <li key={c.id} className={`rounded-lg p-3 text-sm ${c.is_internal ? 'border border-dashed border-amber-300 bg-amber-50' : c.author?.role === 'student' ? 'bg-slate-50' : 'bg-navy-50/60'}`}>
                  <p className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span className="font-semibold text-slate-700">{c.author?.full_name ?? 'Removed user'}</span>
                    {c.author && <span>{label(c.author.role)}</span>}
                    <span>· {formatDateTime(c.created_at)}</span>
                    {c.is_internal && <span className="inline-flex items-center gap-1 font-medium text-amber-800"><Lock className="h-3 w-3" /> Internal note</span>}
                  </p>
                  <p className="mt-1 whitespace-pre-line text-slate-700">{c.body}</p>
                </li>
              ))}
            </ul>
            <form onSubmit={sendReply} className="mt-4 space-y-2" noValidate>
              <FormError message={reply.formError} />
              <Textarea aria-label="Reply" rows={3} {...reply.bind('body')} placeholder={isStudent ? 'Add a reply for the warden' : 'Reply to the student, or add an internal note'} />
              <div className="flex items-center justify-between gap-3">
                {!isStudent ? (
                  <label className="flex items-center gap-2 text-sm text-slate-600">
                    <input type="checkbox" className="h-4 w-4 rounded border-slate-300 text-navy-700 focus:ring-navy-500" {...reply.bind('is_internal', { type: 'checkbox' })} />
                    Internal note (hidden from student)
                  </label>
                ) : <span />}
                <Button type="submit" size="sm" loading={reply.submitting}>{reply.values.is_internal ? 'Add note' : 'Send reply'}</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </Modal>
  );
}
