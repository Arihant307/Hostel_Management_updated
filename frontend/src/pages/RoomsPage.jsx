import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { BedDouble, Download, DoorOpen, Pencil, Plus, Power, Search } from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext.jsx';
import { useToast } from '../features/toast/ToastContext.jsx';
import { reportService, roomService } from '../services/resources.js';
import { getErrorMessage } from '../services/api.js';
import usePaginatedList from '../hooks/usePaginatedList.js';
import PageHeader from '../components/PageHeader.jsx';
import ListToolbar, { toOptions } from '../components/ListToolbar.jsx';
import StatusBadge, { label } from '../components/StatusBadge.jsx';
import Card from '../components/ui/Card.jsx';
import Button from '../components/ui/Button.jsx';
import Modal from '../components/ui/Modal.jsx';
import ConfirmDialog from '../components/ui/ConfirmDialog.jsx';
import DataTable from '../components/ui/DataTable.jsx';
import { DetailList, OccupancyBar } from '../components/ui/Misc.jsx';
import { EmptyState, Skeleton } from '../components/ui/States.jsx';
import RoomFormModal from '../features/rooms/RoomFormModal.jsx';
import { formatDate, formatMoney } from '../utils/format.js';

export default function RoomsPage() {
  const { user } = useAuth();
  const isAdmin = user.role === 'admin';
  const toast = useToast();
  const [blocks, setBlocks] = useState([]);
  const [editing, setEditing] = useState(null); // null | 'new' | room
  const [viewing, setViewing] = useState(null);
  const [toggling, setToggling] = useState(null);
  const [busy, setBusy] = useState(false);
  const list = usePaginatedList(roomService.list, {
    initialFilters: { block: '', room_type: '', availability: '', is_active: 'true' },
    initialSort: { key: 'block', order: 'asc' },
    perPage: 15,
  });

  const loadBlocks = useCallback(() => roomService.blocks().then(setBlocks).catch(() => {}), []);
  useEffect(() => {
    loadBlocks();
  }, [loadBlocks]);

  const toggle = async () => {
    setBusy(true);
    try {
      const updated = await roomService.setStatus(toggling.id, !toggling.is_active);
      toast.success(`Room ${updated.block}-${updated.room_number} ${updated.is_active ? 'activated' : 'deactivated'}.`);
      setToggling(null);
      list.reload();
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const columns = [
    {
      key: 'room', header: 'Room', sortable: true,
      render: (r) => (
        <button type="button" onClick={() => setViewing(r)} className="text-left">
          <span className="block font-medium text-slate-900 hover:text-navy-700">{r.block}-{r.room_number}</span>
          <span className="block text-xs text-slate-500">Block {r.block} · Floor {r.floor}</span>
        </button>
      ),
    },
    { key: 'type', header: 'Type', render: (r) => label(r.room_type) },
    {
      key: 'occupied', header: 'Occupancy', sortable: true,
      render: (r) => <OccupancyBar occupied={r.occupied_beds} capacity={r.capacity} />,
    },
    {
      key: 'monthly_fee', header: 'Monthly fee', sortable: true, className: 'text-right',
      render: (r) => <span className="tabular-nums">{formatMoney(r.monthly_fee_minor)}</span>,
    },
    { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.occupancy_status} /> },
    ...(isAdmin ? [{
      key: 'actions', header: <span className="sr-only">Actions</span>, className: 'text-right',
      render: (r) => (
        <div className="flex justify-end gap-1">
          <Button variant="ghost" size="sm" icon={Pencil} onClick={() => setEditing(r)} aria-label={`Edit room ${r.block}-${r.room_number}`} />
          <Button variant="ghost" size="sm" icon={Power} onClick={() => setToggling(r)}
            aria-label={`${r.is_active ? 'Deactivate' : 'Activate'} room ${r.block}-${r.room_number}`} />
        </div>
      ),
    }] : []),
  ];

  const exportCsv = () => reportService.download('rooms', list.filters).catch((err) => toast.error(getErrorMessage(err)));

  return (
    <>
      <PageHeader
        title="Rooms"
        description="Room inventory with live bed occupancy."
        actions={isAdmin && (
          <>
            <Button variant="secondary" icon={Download} onClick={exportCsv}>Export CSV</Button>
            <Button icon={Plus} onClick={() => setEditing('new')}>Add room</Button>
          </>
        )}
      />
      <Card>
        <ListToolbar
          list={list}
          placeholder="Search room number, block or amenities"
          filters={[
            { key: 'block', label: 'All blocks', options: toOptions(blocks, (b) => `Block ${b}`) },
            { key: 'room_type', label: 'All types', options: toOptions(['single', 'double', 'triple', 'dormitory'], label) },
            {
              key: 'availability', label: 'Any availability', options: [
                { value: 'has_space', label: 'Has free beds' }, { value: 'available', label: 'Empty' },
                { value: 'partially_occupied', label: 'Partially occupied' }, { value: 'full', label: 'Full' },
              ],
            },
            { key: 'is_active', label: 'Active & inactive', options: [{ value: 'true', label: 'Active rooms' }, { value: 'false', label: 'Inactive rooms' }] },
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
          empty={list.hasFilters
            ? <EmptyState icon={Search} title="No rooms match" message="Try a different search or clear the filters." />
            : <EmptyState icon={DoorOpen} title="No rooms yet" message={isAdmin ? 'Add rooms to start allocating beds.' : 'An administrator has not added rooms yet.'}
                action={isAdmin && <Button icon={Plus} onClick={() => setEditing('new')}>Add room</Button>} />}
        />
      </Card>

      <RoomFormModal
        open={Boolean(editing)}
        room={editing === 'new' ? null : editing}
        onClose={() => setEditing(null)}
        onSaved={(r) => {
          toast.success(editing === 'new' ? `Room ${r.block}-${r.room_number} added.` : 'Room updated.');
          setEditing(null);
          list.reload();
          loadBlocks();
        }}
      />
      <RoomDetailModal room={viewing} onClose={() => setViewing(null)} />
      <ConfirmDialog
        open={Boolean(toggling)}
        title={toggling?.is_active ? 'Deactivate room?' : 'Activate room?'}
        message={toggling?.is_active
          ? 'Inactive rooms cannot receive new allocations. Rooms with occupants cannot be deactivated.'
          : 'The room will be available for allocation again.'}
        confirmLabel={toggling?.is_active ? 'Deactivate' : 'Activate'}
        tone={toggling?.is_active ? 'danger' : 'primary'}
        loading={busy}
        onConfirm={toggle}
        onCancel={() => setToggling(null)}
      />
    </>
  );
}

function RoomDetailModal({ room, onClose }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!room) return;
    setDetail(null);
    setError('');
    roomService.get(room.id).then(setDetail).catch((err) => setError(getErrorMessage(err)));
  }, [room]);

  return (
    <Modal open={Boolean(room)} onClose={onClose} title={room ? `Room ${room.block}-${room.room_number}` : ''} size="lg">
      {error && <p className="text-sm text-rose-600">{error}</p>}
      {!detail && !error && <Skeleton className="h-40 w-full" />}
      {detail && (
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <DetailList items={[
              ['Type', label(detail.room_type)],
              ['Floor', detail.floor],
              ['Capacity', `${detail.capacity} beds`],
              ['Available', `${detail.available_beds} beds`],
              ['Monthly fee', formatMoney(detail.monthly_fee_minor)],
              ['Amenities', detail.amenities],
              ['Status', <StatusBadge key="s" status={detail.occupancy_status} />],
            ]} />
          </div>
          <div>
            <h3 className="mb-2 text-sm font-semibold text-slate-900">Current occupants</h3>
            {detail.occupants.length === 0 ? (
              <p className="text-sm text-slate-500">No one is staying here.</p>
            ) : (
              <ul className="space-y-2">
                {detail.occupants.map((a) => (
                  <li key={a.id} className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2">
                    <Link to={`/students/${a.student.id}`} className="text-sm font-medium text-slate-800 hover:text-navy-700">
                      {a.student.full_name}
                      <span className="block text-xs font-normal text-slate-500">{a.student.student_code}</span>
                    </Link>
                    <span className="text-xs text-slate-500">since {formatDate(a.allocated_on)}</span>
                  </li>
                ))}
              </ul>
            )}
            <h3 className="mb-2 mt-5 text-sm font-semibold text-slate-900">Past residents</h3>
            {detail.history.length === 0 ? (
              <p className="text-sm text-slate-500">No history yet.</p>
            ) : (
              <ul className="space-y-1.5 text-sm">
                {detail.history.slice(0, 8).map((a) => (
                  <li key={a.id} className="flex justify-between gap-3 text-slate-600">
                    <span>{a.student.full_name}</span>
                    <span className="text-xs text-slate-400">{formatDate(a.allocated_on)} – {formatDate(a.checked_out_on)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
      {detail && (
        <p className="mt-4 flex items-center gap-1.5 text-xs text-slate-400">
          <BedDouble className="h-3.5 w-3.5" /> Occupancy is calculated from active allocations.
        </p>
      )}
    </Modal>
  );
}
