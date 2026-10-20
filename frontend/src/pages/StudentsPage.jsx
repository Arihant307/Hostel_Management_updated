import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Download, GraduationCap, Plus, Search } from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext.jsx';
import { useToast } from '../features/toast/ToastContext.jsx';
import { reportService, studentService } from '../services/resources.js';
import { getErrorMessage } from '../services/api.js';
import usePaginatedList from '../hooks/usePaginatedList.js';
import PageHeader from '../components/PageHeader.jsx';
import ListToolbar, { toOptions } from '../components/ListToolbar.jsx';
import Card from '../components/ui/Card.jsx';
import Badge from '../components/ui/Badge.jsx';
import Button from '../components/ui/Button.jsx';
import DataTable from '../components/ui/DataTable.jsx';
import { EmptyState } from '../components/ui/States.jsx';
import StudentFormModal from '../features/students/StudentFormModal.jsx';
import { formatDate, initials } from '../utils/format.js';

export default function StudentsPage() {
  const { user } = useAuth();
  const canManage = user.role === 'admin' || user.role === 'warden';
  const toast = useToast();
  const navigate = useNavigate();
  const [departments, setDepartments] = useState([]);
  const [creating, setCreating] = useState(false);
  const [exporting, setExporting] = useState(false);
  const list = usePaginatedList(studentService.list, {
    initialFilters: { status: '', approval: '', verified: '', department: '', academic_year: '', has_room: '' },
    initialSort: { key: 'created_at', order: 'desc' },
  });

  useEffect(() => {
    studentService.departments().then(setDepartments).catch(() => {});
  }, []);

  const exportCsv = async () => {
    setExporting(true);
    try {
      await reportService.download('students');
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setExporting(false);
    }
  };

  const columns = [
    {
      key: 'name', header: 'Student', sortable: true,
      render: (s) => (
        <Link to={`/students/${s.id}`} className="flex items-center gap-3 rounded-md focus-visible:ring-2">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-navy-50 text-xs font-semibold text-navy-700">
            {initials(s.full_name)}
          </span>
          <span className="min-w-0">
            <span className="block truncate font-medium text-slate-900 hover:text-navy-700">{s.full_name}</span>
            <span className="block truncate text-xs text-slate-500">{s.student_code} · {s.email}</span>
          </span>
        </Link>
      ),
    },
    {
      key: 'department', header: 'Course', sortable: true, className: 'hidden md:table-cell',
      render: (s) => (
        <span className="text-slate-600">
          {s.course} · {s.department}
          <span className="block text-xs text-slate-400">Year {s.academic_year}</span>
        </span>
      ),
    },
    {
      key: 'room', header: 'Room',
      render: (s) => s.current_allocation
        ? <span className="font-medium text-slate-700">{s.current_allocation.room.block}-{s.current_allocation.room.room_number}</span>
        : <span className="text-slate-400">Not allocated</span>,
    },
    {
      key: 'registration_date', header: 'Registered', sortable: true, className: 'hidden lg:table-cell',
      render: (s) => <span className="text-slate-500">{formatDate(s.registration_date)}</span>,
    },
    {
      key: 'status', header: 'Status',
      render: (s) => (
        <div className="flex flex-wrap gap-1">
          <Badge tone={s.is_active ? 'success' : 'neutral'}>{s.is_active ? 'Active' : 'Inactive'}</Badge>
          {s.approval_status === 'pending' && <Badge tone="warning">Pending approval</Badge>}
          {s.approval_status === 'rejected' && <Badge tone="danger">Rejected</Badge>}
          {!s.email_verified && <Badge tone="warning">Unverified</Badge>}
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Students"
        description="Registered residents, their courses and room assignments."
        actions={
          <>
            {user.role === 'admin' && (
              <Button variant="secondary" icon={Download} onClick={exportCsv} loading={exporting}>Export CSV</Button>
            )}
            {canManage && <Button icon={Plus} onClick={() => setCreating(true)}>Register student</Button>}
          </>
        }
      />
      <Card>
        <ListToolbar
          list={list}
          placeholder="Search name, email, phone or student ID"
          filters={[
            { key: 'status', label: 'Any status', options: [{ value: 'active', label: 'Active' }, { value: 'inactive', label: 'Inactive' }] },
            { key: 'approval', label: 'Any approval', options: [{ value: 'pending', label: 'Pending approval' }, { value: 'approved', label: 'Approved' }, { value: 'rejected', label: 'Rejected' }] },
            { key: 'verified', label: 'Any verification', options: [{ value: 'true', label: 'Email verified' }, { value: 'false', label: 'Not verified' }] },
            { key: 'has_room', label: 'Any room', options: [{ value: 'true', label: 'Has a room' }, { value: 'false', label: 'No room' }] },
            { key: 'department', label: 'All departments', options: toOptions(departments) },
            { key: 'academic_year', label: 'All years', options: [1, 2, 3, 4, 5, 6].map((y) => ({ value: String(y), label: `Year ${y}` })) },
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
            ? <EmptyState icon={Search} title="No matching students" message="Try a different search or clear the filters." />
            : <EmptyState icon={GraduationCap} title="No students yet" message="Register the first student to start allocating rooms."
                action={canManage && <Button icon={Plus} onClick={() => setCreating(true)}>Register student</Button>} />}
        />
      </Card>
      <StudentFormModal
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={(s) => {
          setCreating(false);
          toast.success(`${s.full_name} registered.`);
          navigate(`/students/${s.id}`);
        }}
      />
    </>
  );
}
