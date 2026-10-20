import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext.jsx';
import Spinner from './ui/Spinner.jsx';
import ForbiddenPage from '../pages/ForbiddenPage.jsx';

/**
 * Guards nested routes. This is a UX convenience only — every API endpoint
 * enforces the same rules on the server.
 */
export default function ProtectedRoute({ roles }) {
  const { status, user, endedBy } = useAuth();
  const location = useLocation();

  if (status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center text-navy-700">
        <Spinner className="h-8 w-8" label="Loading your session" />
      </div>
    );
  }
  if (status !== 'authenticated') {
    // Remember the page only when the session ended involuntarily (expiry, first visit).
    return <Navigate to="/login" replace state={endedBy === 'logout' ? undefined : { from: location }} />;
  }
  if (roles && !roles.includes(user.role)) {
    return <ForbiddenPage />;
  }
  return <Outlet />;
}
