import {
  BarChart3, BedDouble, DoorOpen, GraduationCap, LayoutDashboard, Megaphone, ReceiptText,
  ShieldCheck, UserCircle, Wallet, Wrench,
} from 'lucide-react';

/**
 * Sidebar entries, grouped. `roles` limits who sees an entry (omit = everyone).
 * Hiding an entry is UX only — the API enforces the same permissions.
 */
export const NAV_SECTIONS = [
  {
    items: [{ to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard }],
  },
  {
    title: 'Residents',
    items: [
      { to: '/students', label: 'Students', icon: GraduationCap, roles: ['admin', 'warden', 'staff'] },
      { to: '/rooms', label: 'Rooms', icon: DoorOpen, roles: ['admin', 'warden', 'staff'] },
      { to: '/allocations', label: 'Allocations', icon: BedDouble, roles: ['admin', 'warden'] },
    ],
  },
  {
    title: 'Finance',
    items: [
      { to: '/fees', label: 'Fees', studentLabel: 'My fees', icon: ReceiptText, roles: ['admin', 'warden', 'student'] },
      { to: '/payments', label: 'Payments', studentLabel: 'My payments', icon: Wallet, roles: ['admin', 'warden', 'student'] },
    ],
  },
  {
    title: 'Hostel life',
    items: [
      { to: '/complaints', label: 'Complaints', studentLabel: 'My complaints', icon: Wrench },
      { to: '/notices', label: 'Notice board', icon: Megaphone },
    ],
  },
  {
    title: 'Administration',
    items: [
      { to: '/reports', label: 'Reports', icon: BarChart3, roles: ['admin'] },
      { to: '/staff', label: 'Staff accounts', icon: ShieldCheck, roles: ['admin'] },
    ],
  },
  {
    title: 'Account',
    items: [{ to: '/account', label: 'My account', icon: UserCircle }],
  },
];

export function navSectionsFor(role) {
  return NAV_SECTIONS
    .map((section) => ({
      ...section,
      items: section.items
        .filter((item) => !item.roles || item.roles.includes(role))
        .map((item) => ({ ...item, label: role === 'student' && item.studentLabel ? item.studentLabel : item.label })),
    }))
    .filter((section) => section.items.length > 0);
}
