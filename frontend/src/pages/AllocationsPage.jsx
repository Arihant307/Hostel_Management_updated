import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRightLeft, BedDouble, Check, LogOut, Plus, Search, UserRound } from 'lucide-react';
import { useToast } from '../features/toast/ToastContext.jsx';
import { allocationService, roomService, studentService } from '../services/resources.js';
import usePaginatedList from '../hooks/usePaginatedList.js';
import useDebounce from '../hooks/useDebounce.js';
import useForm from '../hooks/useForm.js';
import PageHeader from '../components/PageHeader.jsx';
import ListToolbar, { toOptions } from '../components/ListToolbar.jsx';
import StatusBadge, { label } from '../components/StatusBadge.jsx';
import Card from '../components/ui/Card.jsx';
import Button from '../components/ui/Button.jsx';
import Input, { Select } from '../components/ui/Input.jsx';
import Textarea from '../components/ui/Textarea.jsx';
import DataTable from '../components/ui/DataTable.jsx';
import { FormError, OccupancyBar, Tabs } from '../components/ui/Misc.jsx';
import { EmptyState, Skeleton } from '../components/ui/States.jsx';
import { CheckoutModal, TransferModal } from '../features/allocations/AllocationModals.jsx';
import { formatDate, formatMoney, todayISO } from '../utils/format.js';

export default function AllocationsPage() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const preselected = params.get('student');
  const [tab, setTab] = useState(preselected ? 'new' : 'current');
  const [blocks, setBlocks] = useState([]);

  useEffect(() => {
    roomService.blocks().then(setBlocks).catch(() => {});
  }, []);

  const switchTab = (key) => {
    setTab(key);
    if (key !== 'new' && preselected) setParams({});
  };

  return (
    <>
      <PageHeader
        title="Room allocation"
        description="Allocate beds, transfer students between rooms and check them out."
        actions={tab !== 'new' && <Button icon={Plus} onClick={() => switchTab('new')}>New allocation</Button>}
      />
      <div className="mb-4">
        <Tabs active={tab} onChange={switchTab} tabs={[
          { key: 'current', label: 'Current residents' },
          { key: 'new', label: 'New allocation' },
          { key: 'history', label: 'All history' },
        ]} />
      </div>

      {tab === 'new' ? (
        <NewAllocation
          blocks={blocks}
          preselectedId={preselected}
          onDone={(a) => {
            toast.success(`${a.student.full_name} allocated to room ${a.room.block}-${a.room.room_number}.`);
            setParams({});
            setTab('current');
          }}
        />
      ) : (
        <AllocationList key={tab} history={tab === 'history'} blocks={blocks} />
      )}
    </>
  );
}

function AllocationList({ history, blocks }) {
  const toast = useToast();
  const [transferring, setTransferring] = useState(null);
  const [checkingOut, setCheckingOut] = useState(null);
  const list = usePaginatedList(allocationService.list, {
    initialFilters: history ? { status: '', block: '' } : { status: 'active', block: '' },
    initialSort: { key: 'allocated_on', order: 'desc' },
    perPage: 15,
  });

  const columns = [
    {
      key: 'student', header: 'Student', sortable: true,
      render: (a) => (
        <Link to={`/students/${a.student.id}`} className="block">
          <span className="block font-medium text-slate-900 hover:text-navy-700">{a.student.full_name}</span>
          <span className="block text-xs text-slate-500">{a.student.student_code}</span>
        </Link>
      ),
    },
    {
      key: 'room', header: 'Room', sortable: true,
      render: (a) => <span className="font-medium text-slate-700">{a.room.block}-{a.room.room_number}</span>,
    },
    { key: 'allocated_on', header: 'From', sortable: true, render: (a) => formatDate(a.allocated_on) },
    {
      key: history ? 'checked_out_on' : 'expected_checkout_on',
      header: history ? 'Until' : 'Expected checkout', sortable: true, className: 'hidden md:table-cell',
      render: (a) => <span className="text-slate-500">{formatDate(history ? a.checked_out_on : a.expected_checkout_on)}</span>,
    },
    { key: 'status', header: 'Status', render: (a) => <StatusBadge status={a.status} /> },
    {
      key: 'actions', header: <span className="sr-only">Actions</span>, className: 'text-right',
      render: (a) => a.status === 'active' && (
        <div className="flex justify-end gap-1">
          <Button variant="ghost" size="sm" icon={ArrowRightLeft} onClick={() => setTransferring(a)}>Transfer</Button>
          <Button variant="ghost" size="sm" icon={LogOut} className="text-rose-600 hover:bg-rose-50" onClick={() => setCheckingOut(a)}>
            Check out
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <Card>
        <ListToolbar
          list={list}
          placeholder="Search student name, ID or room number"
          filters={[
            { key: 'block', label: 'All blocks', options: toOptions(blocks, (b) => `Block ${b}`) },
            ...(history ? [{ key: 'status', label: 'Any status', options: toOptions(['active', 'transferred', 'checked_out'], label) }] : []),
          ]}
        />
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
          empty={<EmptyState icon={BedDouble} title={list.hasFilters ? 'No matching allocations' : 'No allocations yet'}
            message={list.hasFilters ? 'Try a different search.' : 'Allocate a room to a student to see them here.'} />}
        />
      </Card>
      <TransferModal
        allocation={transferring}
        onClose={() => setTransferring(null)}
        onDone={(a) => {
          toast.success(`${a.student.full_name} moved to room ${a.room.block}-${a.room.room_number}.`);
          setTransferring(null);
          list.reload();
        }}
      />
      <CheckoutModal
        allocation={checkingOut}
        onClose={() => setCheckingOut(null)}
        onDone={(a) => {
          toast.success(`${a.student.full_name} checked out.`);
          setCheckingOut(null);
          list.reload();
        }}
      />
    </>
  );
}

/** Three-step workflow: student → room with a free bed → dates. */
function NewAllocation({ blocks, preselectedId, onDone }) {
  const toast = useToast();
  const [student, setStudent] = useState(null);
  const [room, setRoom] = useState(null);
  const [roomsVersion, setRoomsVersion] = useState(0);
  const onRoomTaken = () => {
    setRoom(null);
    setRoomsVersion((v) => v + 1);
    toast.error('That room just filled up. Please choose another room.');
  };

  useEffect(() => {
    if (preselectedId) studentService.get(preselectedId).then(setStudent).catch(() => {});
  }, [preselectedId]);

  return (
    <div className="grid gap-6 xl:grid-cols-3">
      <Step number={1} title="Student" done={Boolean(student)}>
        <StudentPicker selected={student} onSelect={(s) => { setStudent(s); setRoom(null); }} />
      </Step>
      <Step number={2} title="Room" done={Boolean(room)} disabled={!student}>
        <RoomPicker blocks={blocks} selected={room} onSelect={setRoom} version={roomsVersion} />
      </Step>
      <Step number={3} title="Confirm" disabled={!student || !room}>
        <ConfirmAllocation student={student} room={room} onDone={onDone} onRoomTaken={onRoomTaken} />
      </Step>
    </div>
  );
}

function Step({ number, title, done, disabled, children }) {
  return (
    <Card className={`flex flex-col ${disabled ? 'opacity-50' : ''}`} aria-disabled={disabled || undefined}>
      <div className="flex items-center gap-3 border-b border-slate-100 px-5 py-3.5">
        <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${done ? 'bg-emerald-600 text-white' : 'bg-navy-100 text-navy-800'}`}>
          {done ? <Check className="h-3.5 w-3.5" /> : number}
        </span>
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
      </div>
      <div className={`flex-1 p-5 ${disabled ? 'pointer-events-none' : ''}`}>{children}</div>
    </Card>
  );
}

function StudentPicker({ selected, onSelect }) {
  const [search, setSearch] = useState('');
  const debounced = useDebounce(search);
  const [results, setResults] = useState(null);

  useEffect(() => {
    let cancelled = false;
    studentService.list({ search: debounced, has_room: 'false', status: 'active', per_page: 8, sort: 'name' })
      .then((d) => !cancelled && setResults(d.items))
      .catch(() => !cancelled && setResults([]));
    return () => { cancelled = true; };
  }, [debounced]);

  if (selected) {
    return (
      <div className="rounded-lg border border-navy-200 bg-navy-50/50 p-4">
        <p className="font-medium text-slate-900">{selected.full_name}</p>
        <p className="text-sm text-slate-500">{selected.student_code} · {selected.course}, Year {selected.academic_year}</p>
        {selected.current_allocation && (
          <p className="mt-2 text-sm text-rose-600">Already in room {selected.current_allocation.room.block}-{selected.current_allocation.room.room_number}. Use transfer instead.</p>
        )}
        <button type="button" onClick={() => onSelect(null)} className="mt-3 text-sm font-medium text-navy-700 hover:text-navy-900">
          Change student
        </button>
      </div>
    );
  }
  return (
    <>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search students without a room"
          aria-label="Search students without a room"
          className="h-10 w-full rounded-lg border border-slate-200 pl-9 pr-3 text-sm focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-100" />
      </div>
      <ul className="mt-3 space-y-1.5">
        {results === null && [1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
        {results?.length === 0 && <p className="py-6 text-center text-sm text-slate-500">No active students without a room.</p>}
        {results?.map((s) => (
          <li key={s.id}>
            <button type="button" onClick={() => onSelect(s)}
              className="flex w-full items-center gap-3 rounded-lg border border-slate-100 px-3 py-2 text-left transition-colors hover:border-navy-200 hover:bg-navy-50/40">
              <UserRound className="h-4 w-4 text-slate-400" />
              <span>
                <span className="block text-sm font-medium text-slate-800">{s.full_name}</span>
                <span className="block text-xs text-slate-500">{s.student_code} · {s.department}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}

function RoomPicker({ blocks, selected, onSelect, version }) {
  const [filters, setFilters] = useState({ block: '', room_type: '' });
  const [rooms, setRooms] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setRooms(null);
    allocationService.eligibleRooms({ ...filters, per_page: 50 })
      .then((d) => !cancelled && setRooms(d.items))
      .catch(() => !cancelled && setRooms([]));
    return () => { cancelled = true; };
  }, [filters, version]);

  return (
    <>
      <div className="grid grid-cols-2 gap-2">
        <Select aria-label="Block" value={filters.block} onChange={(e) => setFilters((f) => ({ ...f, block: e.target.value }))}>
          <option value="">All blocks</option>
          {blocks.map((b) => <option key={b} value={b}>Block {b}</option>)}
        </Select>
        <Select aria-label="Room type" value={filters.room_type} onChange={(e) => setFilters((f) => ({ ...f, room_type: e.target.value }))}>
          <option value="">All types</option>
          {['single', 'double', 'triple', 'dormitory'].map((t) => <option key={t} value={t}>{label(t)}</option>)}
        </Select>
      </div>
      <ul className="mt-3 max-h-96 space-y-1.5 overflow-y-auto pr-1">
        {rooms === null && [1, 2, 3].map((i) => <Skeleton key={i} className="h-14 w-full" />)}
        {rooms?.length === 0 && <p className="py-6 text-center text-sm text-slate-500">No rooms with free beds match.</p>}
        {rooms?.map((r) => {
          const active = selected?.id === r.id;
          return (
            <li key={r.id}>
              <button type="button" onClick={() => onSelect(r)} aria-pressed={active}
                className={`w-full rounded-lg border px-3 py-2.5 text-left transition-colors ${active ? 'border-navy-500 bg-navy-50 ring-1 ring-navy-500' : 'border-slate-100 hover:border-navy-200 hover:bg-navy-50/40'}`}>
                <span className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-slate-800">{r.block}-{r.room_number} <span className="font-normal text-slate-500">· {label(r.room_type)}</span></span>
                  <span className="text-sm tabular-nums text-slate-700">{formatMoney(r.monthly_fee_minor)}/mo</span>
                </span>
                <span className="mt-1.5 flex items-center justify-between">
                  <OccupancyBar occupied={r.occupied_beds} capacity={r.capacity} />
                  <span className="text-xs text-emerald-700">{r.available_beds} bed{r.available_beds === 1 ? '' : 's'} free</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function ConfirmAllocation({ student, room, onDone, onRoomTaken }) {
  const form = useForm({ allocated_on: todayISO(), expected_checkout_on: '', notes: '' });

  const save = async (e) => {
    e.preventDefault();
    const result = await form.submit(
      async (v) => {
        try {
          return await allocationService.allocate({
            student_id: student.id, room_id: room.id, allocated_on: v.allocated_on,
            expected_checkout_on: v.expected_checkout_on || null, notes: v.notes.trim() || null,
          });
        } catch (err) {
          // The room filled up since it was listed: send the user back to pick another.
          if (err?.response?.data?.error?.code === 'room_full') onRoomTaken();
          throw err;
        }
      },
      { validate: (v) => ({
        expected_checkout_on: v.expected_checkout_on && v.expected_checkout_on < v.allocated_on && 'Must be after the allocation date.',
      }) },
    );
    if (result) onDone(result);
  };

  useEffect(() => {
    form.setFormError('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room?.id]);

  if (!student || !room) return <p className="text-sm text-slate-500">Choose a student and a room first.</p>;
  return (
    <form onSubmit={save} className="space-y-4" noValidate>
      <div className="rounded-lg bg-surface-muted p-3 text-sm">
        <p><span className="text-slate-500">Student:</span> <span className="font-medium">{student.full_name}</span></p>
        <p className="mt-1"><span className="text-slate-500">Room:</span> <span className="font-medium">{room.block}-{room.room_number}</span> · {formatMoney(room.monthly_fee_minor)}/month</p>
      </div>
      <FormError message={form.formError} />
      <Input label="Allocation date" type="date" required {...form.bind('allocated_on')} />
      <Input label="Expected checkout" type="date" {...form.bind('expected_checkout_on')} min={form.values.allocated_on} />
      <Textarea label="Notes" rows={2} {...form.bind('notes')} />
      <Button type="submit" className="w-full" loading={form.submitting} disabled={Boolean(student.current_allocation)}>
        Allocate room
      </Button>
    </form>
  );
}
