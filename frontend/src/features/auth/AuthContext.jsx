import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { AUTH_EXPIRED_EVENT } from '../../services/api.js';
import { authService } from '../../services/authService.js';
import { tokenStorage } from '../../services/tokenStorage.js';
import { useToast } from '../toast/ToastContext.jsx';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const toast = useToast();
  const [state, setState] = useState({
    status: tokenStorage.get() ? 'loading' : 'anonymous',
    user: null,
    studentProfile: null,
    // 'logout' after an explicit sign-out, so the next sign-in starts fresh
    // instead of returning to the previous user's page.
    endedBy: null,
  });

  const applySession = useCallback((data) => {
    setState({
      status: 'authenticated',
      user: data.user,
      studentProfile: data.student_profile ?? null,
      endedBy: null,
    });
  }, []);

  const clearSession = useCallback((endedBy = null) => {
    tokenStorage.clear();
    setState({ status: 'anonymous', user: null, studentProfile: null, endedBy });
  }, []);

  // Restore the session on page load by validating the stored token.
  useEffect(() => {
    if (!tokenStorage.get()) return;
    let cancelled = false;
    authService
      .me()
      .then((data) => !cancelled && applySession(data))
      .catch(() => !cancelled && clearSession('expired'));
    return () => {
      cancelled = true;
    };
  }, [applySession, clearSession]);

  // The API interceptor reports rejected tokens (expired, revoked, deactivated).
  useEffect(() => {
    const onExpired = (event) => {
      setState({ status: 'anonymous', user: null, studentProfile: null, endedBy: 'expired' });
      toast.error(event.detail || 'Your session has ended. Please sign in again.');
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, [toast]);

  const login = useCallback(
    async (email, password) => {
      const data = await authService.login(email, password);
      tokenStorage.set(data.access_token);
      applySession(data);
      return data.user;
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    try {
      await authService.logout();
    } catch {
      /* token may already be invalid; sign out locally regardless */
    }
    clearSession('logout');
  }, [clearSession]);

  const logoutAll = useCallback(async () => {
    await authService.logoutAll(); // surface errors: the caller shows them
    clearSession('logout');
  }, [clearSession]);

  const replaceToken = useCallback((token) => tokenStorage.set(token), []);

  /** Apply a fresh {user, student_profile} payload returned by the API. */
  const refreshSession = useCallback((data) => applySession(data), [applySession]);

  const value = useMemo(
    () => ({ ...state, login, logout, logoutAll, replaceToken, refreshSession }),
    [state, login, logout, logoutAll, replaceToken, refreshSession],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
