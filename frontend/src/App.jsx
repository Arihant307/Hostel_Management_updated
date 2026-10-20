import { Navigate, Route, Routes } from 'react-router-dom';
import { ToastProvider } from './features/toast/ToastContext.jsx';
import { AuthProvider } from './features/auth/AuthContext.jsx';
import ProtectedRoute from './components/ProtectedRoute.jsx';
import AppLayout from './layouts/AppLayout.jsx';
import LoginPage from './pages/LoginPage.jsx';
import SignupPage from './pages/SignupPage.jsx';
import {
  AccountDisabledPage, AccountPendingPage, ForgotPasswordPage, ResetPasswordPage, VerifyEmailPage,
} from './pages/AccountFlowPages.jsx';
import DashboardPage from './pages/DashboardPage.jsx';
import StudentsPage from './pages/StudentsPage.jsx';
import StudentDetailPage from './pages/StudentDetailPage.jsx';
import RoomsPage from './pages/RoomsPage.jsx';
import AllocationsPage from './pages/AllocationsPage.jsx';
import FeesPage from './pages/FeesPage.jsx';
import PaymentsPage from './pages/PaymentsPage.jsx';
import ReceiptPage from './pages/ReceiptPage.jsx';
import ComplaintsPage from './pages/ComplaintsPage.jsx';
import NoticesPage from './pages/NoticesPage.jsx';
import ReportsPage from './pages/ReportsPage.jsx';
import StaffPage from './pages/StaffPage.jsx';
import AccountPage, { ChangePasswordPage } from './pages/AccountPage.jsx';
import SystemStatusPage from './pages/SystemStatusPage.jsx';
import NotFoundPage from './pages/NotFoundPage.jsx';

// These mirror the server's permissions; the API enforces them regardless.
const ANY_STAFF = ['admin', 'warden', 'staff'];
const MANAGERS = ['admin', 'warden'];
const FINANCE = ['admin', 'warden', 'student'];

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <Routes>
          {/* Public account pages */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/account-pending" element={<AccountPendingPage />} />
          <Route path="/account-disabled" element={<AccountDisabledPage />} />
          <Route path="/status" element={<SystemStatusPage />} />

          <Route element={<ProtectedRoute />}>
            {/* Printable page without the app chrome */}
            <Route element={<ProtectedRoute roles={FINANCE} />}>
              <Route path="/receipts/:id" element={<ReceiptPage />} />
            </Route>

            <Route element={<AppLayout />}>
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/complaints" element={<ComplaintsPage />} />
              <Route path="/notices" element={<NoticesPage />} />
              <Route path="/account" element={<AccountPage />} />
              <Route path="/change-password" element={<ChangePasswordPage />} />

              <Route element={<ProtectedRoute roles={FINANCE} />}>
                <Route path="/fees" element={<FeesPage />} />
                <Route path="/payments" element={<PaymentsPage />} />
              </Route>
              <Route element={<ProtectedRoute roles={ANY_STAFF} />}>
                <Route path="/students" element={<StudentsPage />} />
                <Route path="/students/:id" element={<StudentDetailPage />} />
                <Route path="/rooms" element={<RoomsPage />} />
              </Route>
              <Route element={<ProtectedRoute roles={MANAGERS} />}>
                <Route path="/allocations" element={<AllocationsPage />} />
              </Route>
              <Route element={<ProtectedRoute roles={['admin']} />}>
                <Route path="/reports" element={<ReportsPage />} />
                <Route path="/staff" element={<StaffPage />} />
              </Route>
            </Route>
          </Route>

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AuthProvider>
    </ToastProvider>
  );
}
