import { Link } from 'react-router-dom';
import { BedDouble, Building2, ReceiptText, Wrench } from 'lucide-react';

const HIGHLIGHTS = [
  { icon: BedDouble, text: 'Room allocation with live bed availability' },
  { icon: ReceiptText, text: 'Fee tracking, payments and receipts' },
  { icon: Wrench, text: 'Complaint and maintenance workflows' },
];

/** Two-column layout shared by every public authentication page. */
export default function AuthLayout({ title, subtitle, children, wide = false, footer }) {
  return (
    <div className="flex min-h-screen bg-white">
      <aside className="relative hidden w-[40%] max-w-xl flex-col justify-between overflow-hidden bg-navy-900 p-12 text-white lg:flex">
        <Link to="/login" className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/20">
            <Building2 className="h-5 w-5" />
          </span>
          <span className="text-lg font-semibold">HostelHub</span>
        </Link>
        <div>
          <h2 className="max-w-md text-3xl font-semibold leading-tight">
            Run your hostel from one calm, organised workspace.
          </h2>
          <ul className="mt-8 space-y-4">
            {HIGHLIGHTS.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-sm text-navy-100">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10">
                  <Icon className="h-4 w-4" />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-navy-300">Secure accounts for students and hostel staff.</p>
        <div className="pointer-events-none absolute -bottom-32 -right-32 h-96 w-96 rounded-full border border-white/5" />
        <div className="pointer-events-none absolute -bottom-16 -right-16 h-64 w-64 rounded-full border border-white/5" />
      </aside>

      <main className="flex flex-1 justify-center overflow-y-auto px-4 py-10 sm:px-8 lg:items-center">
        <div className={`w-full ${wide ? 'max-w-2xl' : 'max-w-sm'}`}>
          <Link to="/login" className="mb-8 flex items-center gap-2.5 lg:hidden">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-navy-800 text-white">
              <Building2 className="h-5 w-5" />
            </span>
            <span className="text-base font-semibold text-navy-900">HostelHub</span>
          </Link>
          {title && <h1 className="text-2xl font-semibold tracking-tight text-navy-900">{title}</h1>}
          {subtitle && <p className="mt-1.5 text-sm text-slate-500">{subtitle}</p>}
          <div className={title ? 'mt-6' : ''}>{children}</div>
          {footer && <div className="mt-8 text-center text-sm text-slate-500">{footer}</div>}
        </div>
      </main>
    </div>
  );
}

/** Centered status card for verify / pending / disabled / success screens. */
export function AuthStatus({ icon: Icon, tone = 'navy', title, children, actions }) {
  const tones = {
    navy: 'bg-navy-50 text-navy-700',
    green: 'bg-emerald-50 text-emerald-600',
    amber: 'bg-amber-50 text-amber-600',
    rose: 'bg-rose-50 text-rose-600',
  };
  return (
    <div className="text-center">
      <span className={`mx-auto flex h-14 w-14 items-center justify-center rounded-full ${tones[tone]}`}>
        <Icon className="h-7 w-7" aria-hidden="true" />
      </span>
      <h1 className="mt-5 text-2xl font-semibold tracking-tight text-navy-900">{title}</h1>
      <div className="mt-3 space-y-3 text-sm leading-relaxed text-slate-600">{children}</div>
      {actions && <div className="mt-8 flex flex-col gap-2">{actions}</div>}
    </div>
  );
}
