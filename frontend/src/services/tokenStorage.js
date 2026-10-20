/**
 * Access-token storage.
 *
 * sessionStorage is used (not localStorage) so the token is scoped to one
 * browser tab and disappears when the tab closes. Tokens are short-lived and
 * revoked server-side on logout. Never log or render the token.
 */
const KEY = 'hms.access_token';

export const tokenStorage = {
  get() {
    try {
      return window.sessionStorage.getItem(KEY);
    } catch {
      return null;
    }
  },
  set(token) {
    try {
      window.sessionStorage.setItem(KEY, token);
    } catch {
      /* storage unavailable (private mode) — session lasts for this page only */
    }
  },
  clear() {
    try {
      window.sessionStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
  },
};
