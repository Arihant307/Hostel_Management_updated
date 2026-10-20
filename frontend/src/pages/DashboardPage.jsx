import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle, BedDouble, Building2, GraduationCap, IndianRupee, Megaphone, Pin, RefreshCw, Wallet, Wrench,
} from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext.jsx';
import { dashboardService } from '../services/resources.js';
import { getErrorMessage } from '../services/api.js';
import PageHeader from '../components/PageHeader.jsx';
import Card from '../components/ui/Card.jsx';
import Button from '../components/ui/Button.jsx';
import StatusBadge, { label } from '../components/StatusBadge.jsx';
import { OccupancyBar, StatCard } from '../components/ui/Misc.jsx';
import { EmptyState, ErrorState, Skeleton } from '../components/ui/States.jsx';
import { HorizontalBarChart, OccupancyChart, PaymentTrendChart } from '../components/charts.jsx';
import { formatDate, formatDateTime, formatMoney, plural } from '../utils/format.js';

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

function useLoader(loader) {
  const [state, setState] = useState({ data: null, error: '' });
  const load = useCallback(() => {
    setState((s) => ({ ...s, error: '' }));
    loader().then((data) => setState({ data, error: '' })).catch((err) => setState({ data: null, error: getErrorMessage(err) }));
  }, [loader]);
  useEffect(() => { load(); }, [load]);
  return { ...state, reload: load };
}

export default function DashboardPage() {
  const { user } = useAuth();
  return user.role === 'student' ? <StudentDashboard /> : <StaffDashboard />;
}

function Panel({ title, action, children, className = '' }) {
  return (
    <Card className={className}>
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </Card>
  );
}

function StaffDashboard() {
  const { user } = useAuth();
  const showFinance = user.role !== 'staff';
  const { data: d, error, reload } = useLoader(dashboardService.staff);
  const loading = !d && !error;

  if (error) return <Card><ErrorState message={error} onRetry={reload} /></Card>;

  return (
    <>
      <PageHeader
        title={`${greeting()}, ${user.full_name.split(' ')[0]}`}
        description={d ? `Live figures from the database · updated ${formatDateTime(d.as_of)}` : 'Loading live figures…'}
        actions={<Button variant="secondary" icon={RefreshCw} onClick={reload}>Refresh</Button>}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={GraduationCap} label="Registered students" loading={loading}
          value={d?.students.active} sub={d && `${d.students.with_room} housed · ${d.students.new_this_month} new this month`} />
        <StatCard icon={BedDouble} label="Bed occupancy" loading={loading}
          value={d && `${d.rooms.occupancy_percent}%`} sub={d && `${d.rooms.beds_occupied} of ${d.rooms.beds_total} beds · ${d.rooms.beds_available} free`} />
        {showFinance && <StatCard icon={Wallet} tone="amber" label="Pending fees" loading={loading}
          value={d && formatMoney(d.fees.outstanding_minor)} sub={d && `${d.fees.unpaid_count} unpaid · ${d.fees.overdue_count} overdue`} />}
        <StatCard icon={Wrench} tone="rose" label="Active complaints" loading={loading}
          value={d?.complaints.active} sub={d && `${d.complaints.open} open · ${d.complaints.in_progress} in progress`} />
      </div>

      {showFinance && <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Building2} tone="slate" label="Rooms" loading={loading} value={d?.rooms.rooms} sub={d && `${d.rooms.beds_total} beds in active rooms`} />
        <StatCard icon={IndianRupee} tone="green" label="Collected this month" loading={loading}
          value={d && formatMoney(d.payments.this_month_minor)} sub={d && plural(d.payments.this_month_count, 'payment')} />
        <StatCard icon={IndianRupee} tone="green" label="Total collected" loading={loading}
          value={d && formatMoney(d.payments.total_minor)} sub={d && `${plural(d.payments.total_count, 'payment')} recorded`} />
        <StatCard icon={AlertTriangle} tone="rose" label="Overdue amount" loading={loading}
          value={d && formatMoney(d.fees.overdue_minor)} sub={d && `${plural(d.fees.overdue_count, 'overdue fee')}`} />
      </div>}

      <div className="mt-6 grid gap-6 xl:grid-cols-5">
        {showFinance && <Panel title="Monthly payments collected" className="xl:col-span-3">
          {loading ? <Skeleton className="h-[260px] w-full" /> : <PaymentTrendChart data={d.payment_trend} />}
        </Panel>}
        <Panel title="Room occupancy by block" className={showFinance ? 'xl:col-span-2' : 'xl:col-span-5'}>
          {loading ? <Skeleton className="h-[260px] w-full" />
            : d.occupancy_by_block.length ? <OccupancyChart data={d.occupancy_by_block} />
              : <EmptyState icon={Building2} title="No rooms yet" message="Add rooms to see occupancy." />}
        </Panel>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Panel title="Recent registrations" action={<Link to="/students" className="text-xs font-medium text-navy-700 hover:text-navy-900">View all</Link>}>
          {loading ? <Skeleton className="h-40 w-full" /> : d.recent_students.length === 0
            ? <p className="text-sm text-slate-500">No students registered yet.</p> : (
              <ul className="divide-y divide-slate-100">
                {d.recent_students.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-3 py-2.5">
                    <Link to={`/students/${s.id}`} className="min-w-0">
                      <span className="block truncate text-sm font-medium text-slate-800 hover:text-navy-700">{s.full_name}</span>
                      <span className="block text-xs text-slate-500">{s.student_code} · {s.department}</span>
                    </Link>
                    <span className="shrink-0 text-xs text-slate-400">{formatDate(s.registration_date)}</span>
                  </li>
                ))}
              </ul>
            )}
        </Panel>
        <Panel title="Recent allocations" action={<Link to="/allocations" className="text-xs font-medium text-navy-700 hover:text-navy-900">View all</Link>}>
          {loading ? <Skeleton className="h-40 w-full" /> : d.recent_allocations.length === 0
            ? <p className="text-sm text-slate-500">No allocations yet.</p> : (
              <ul className="divide-y divide-slate-100">
                {d.recent_allocations.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-3 py-2.5">
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-slate-800">{a.student.full_name}</span>
                      <span className="block text-xs text-slate-500">Room {a.room.block}-{a.room.room_number} · {formatDate(a.allocated_on)}</span>
                    </span>
                    <StatusBadge status={a.status} />
                  </li>
                ))}
              </ul>
            )}
        </Panel>
        <Panel title="Complaints by category" action={<Link to="/complaints" className="text-xs font-medium text-navy-700 hover:text-navy-900">View all</Link>}>
          {loading ? <Skeleton className="h-40 w-full" /> : d.complaints_by_category.length === 0
            ? <p className="text-sm text-slate-500">No complaints filed.</p>
            : <HorizontalBarChart data={d.complaints_by_category.map((c) => ({ ...c, name: label(c.category) }))}
                dataKey="total" nameKey="name" name="Complaints" height={200} />}
        </Panel>
      </div>
    </>
  );
}

function StudentDashboard() {
  const { user } = useAuth();
  const { data: d, error, reload } = useLoader(dashboardService.student);
  if (error) return <Card><ErrorState message={error} onRetry={reload} /></Card>;
  const loading = !d;

  return (
    <>
      <PageHeader title={`${greeting()}, ${user.full_name.split(' ')[0]}`} description="Your room, fees, complaints and the latest notices." />

      <div className="grid gap-4 md:grid-cols-3">
        <StatCard icon={BedDouble} label="My room" loading={loading}
          value={d && (d.room ? `${d.room.block}-${d.room.room_number}` : 'Not allocated')}
          sub={d && (d.room ? `${label(d.room.room_type)} · Floor ${d.room.floor}` : 'Contact the warden for a room')} />
        <StatCard icon={Wallet} tone={d?.fees.overdue_count ? 'rose' : 'amber'} label="Amount due" loading={loading}
          value={d && formatMoney(d.fees.outstanding_minor)}
          sub={d && (d.fees.next_due ? `Next due ${formatDate(d.fees.next_due.due_date)}${d.fees.overdue_count ? ` · ${d.fees.overdue_count} overdue` : ''}` : 'Nothing due')} />
        <StatCard icon={Wrench} tone="slate" label="Open complaints" loading={loading}
          value={d?.complaints.filter((c) => ['open', 'in_progress'].includes(c.status)).length}
          sub="Of your recent complaints" />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Panel title="Room details">
          {loading ? <Skeleton className="h-32 w-full" /> : !d.room ? (
            <p className="text-sm text-slate-500">You have not been allocated a room yet.</p>
          ) : (
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Occupancy</span>
                <OccupancyBar occupied={d.room.occupied_beds} capacity={d.room.capacity} />
              </div>
              <div className="flex justify-between"><span className="text-slate-500">Monthly fee</span><span className="font-medium tabular-nums">{formatMoney(d.room.monthly_fee_minor)}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Since</span><span className="font-medium">{formatDate(d.room.allocation.allocated_on)}</span></div>
              {d.room.allocation.expected_checkout_on && (
                <div className="flex justify-between"><span className="text-slate-500">Expected checkout</span><span className="font-medium">{formatDate(d.room.allocation.expected_checkout_on)}</span></div>
              )}
              <div>
                <span className="text-slate-500">Roommates</span>
                <p className="mt-1 font-medium text-slate-800">{d.room.roommates.length ? d.room.roommates.join(', ') : 'None'}</p>
              </div>
              {d.room.amenities && <p className="text-xs text-slate-500">{d.room.amenities}</p>}
            </div>
          )}
        </Panel>
        <Panel title="Recent fees" action={<Link to="/fees" className="text-xs font-medium text-navy-700 hover:text-navy-900">All fees</Link>}>
          {loading ? <Skeleton className="h-32 w-full" /> : d.fees.recent.length === 0 ? <p className="text-sm text-slate-500">No fees yet.</p> : (
            <ul className="divide-y divide-slate-100">
              {d.fees.recent.map((f) => (
                <li key={f.id} className="flex items-center justify-between gap-3 py-2.5">
                  <span>
                    <span className="block text-sm font-medium text-slate-800">{f.description || label(f.fee_type)}</span>
                    <span className="block text-xs text-slate-500">Due {formatDate(f.due_date)} · {formatMoney(f.balance_minor)} left</span>
                  </span>
                  <StatusBadge status={f.status} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="My complaints" action={<Link to="/complaints" className="text-xs font-medium text-navy-700 hover:text-navy-900">New complaint</Link>}>
          {loading ? <Skeleton className="h-32 w-full" /> : d.complaints.length === 0 ? <p className="text-sm text-slate-500">No complaints filed.</p> : (
            <ul className="divide-y divide-slate-100">
              {d.complaints.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3 py-2.5">
                  <span>
                    <span className="block text-sm font-medium text-slate-800">{c.title}</span>
                    <span className="block text-xs text-slate-500">{label(c.category)} · {formatDate(c.created_at)}</span>
                  </span>
                  <StatusBadge status={c.status} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title="Latest notices" className="mt-6" action={<Link to="/notices" className="text-xs font-medium text-navy-700 hover:text-navy-900">Notice board</Link>}>
        {loading ? <Skeleton className="h-24 w-full" /> : d.notices.length === 0
          ? <EmptyState icon={Megaphone} title="No notices" message="Announcements from the hostel office will appear here." /> : (
            <ul className="space-y-3">
              {d.notices.map((n) => (
                <li key={n.id} className="rounded-lg border border-slate-100 p-4">
                  <p className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                    {n.is_pinned && <Pin className="h-3.5 w-3.5 text-navy-600" aria-label="Pinned" />}
                    {n.title}
                    <span className="text-xs font-normal text-slate-400">· {label(n.category)} · {formatDate(n.publish_at)}</span>
                  </p>
                  <p className="mt-1 line-clamp-2 whitespace-pre-line text-sm text-slate-600">{n.body}</p>
                </li>
              ))}
            </ul>
          )}
      </Panel>
    </>
  );
}
