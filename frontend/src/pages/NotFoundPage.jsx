import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4 text-center">
      <p className="text-sm font-semibold text-navy-600">404</p>
      <h1 className="mt-2 text-2xl font-semibold text-navy-900">Page not found</h1>
      <p className="mt-2 text-sm text-slate-500">The page you are looking for does not exist.</p>
      <Link to="/" className="mt-6 text-sm font-medium text-navy-700 hover:text-navy-900">
        Go back home
      </Link>
    </main>
  );
}
