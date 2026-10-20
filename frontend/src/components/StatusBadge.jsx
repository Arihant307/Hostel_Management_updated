import Badge from './ui/Badge.jsx';

/** One place mapping every domain status to a label and colour. */
const MAP = {
  // rooms
  available: ['Available', 'success'],
  partially_occupied: ['Partially occupied', 'warning'],
  full: ['Full', 'danger'],
  inactive: ['Inactive', 'neutral'],
  // allocations
  active: ['Active', 'success'],
  transferred: ['Transferred', 'navy'],
  checked_out: ['Checked out', 'neutral'],
  // fees
  pending: ['Pending', 'warning'],
  partially_paid: ['Partially paid', 'navy'],
  paid: ['Paid', 'success'],
  overdue: ['Overdue', 'danger'],
  cancelled: ['Cancelled', 'neutral'],
  // payments
  completed: ['Completed', 'success'],
  failed: ['Failed', 'danger'],
  reversed: ['Reversed', 'neutral'],
  // complaints
  open: ['Open', 'warning'],
  in_progress: ['In progress', 'navy'],
  resolved: ['Resolved', 'success'],
  rejected: ['Rejected', 'neutral'],
  // payment methods (used as labels)
  upi: ['UPI', 'neutral'],
  // priorities
  low: ['Low', 'neutral'],
  medium: ['Medium', 'warning'],
  high: ['High', 'danger'],
};

export default function StatusBadge({ status }) {
  const [label, tone] = MAP[status] ?? [status, 'neutral'];
  return <Badge tone={tone}>{label}</Badge>;
}

export const label = (value) =>
  MAP[value]?.[0] ?? String(value ?? '').replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
