import { Link } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';

export default function ForbiddenPage() {
  return (
    <div className="flex flex-col items-center px-4 py-24 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-amber-50">
        <ShieldAlert className="h-6 w-6 text-amber-600" />
      </div>
      <h1 className="mt-4 text-xl font-semibold text-navy-900">You don't have access to this page</h1>
      <p className="mt-2 max-w-sm text-sm text-slate-500">
        Your role does not include permission for this area. If you think this is a mistake, contact an
        administrator.
      </p>
      <Link to="/dashboard" className="mt-6 text-sm font-medium text-navy-700 hover:text-navy-900">
        Back to dashboard
      </Link>
    </div>
  );
}
