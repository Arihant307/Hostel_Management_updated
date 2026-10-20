import axios from 'axios';
import { tokenStorage } from './tokenStorage.js';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000/api';

/** Fired when the server rejects our token; AuthProvider listens and signs out. */
export const AUTH_EXPIRED_EVENT = 'hms:auth-expired';

const api = axios.create({
  baseURL: API_BASE_URL,
  // A free Render API sleeps after 15 idle minutes and needs up to about a
  // minute to wake, so the first request after a pause can be slow.
  timeout: 70000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = tokenStorage.get();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const isLogin = error?.config?.url?.includes('/auth/login');
    if (status === 401 && !isLogin && tokenStorage.get()) {
      tokenStorage.clear();
      window.dispatchEvent(
        new CustomEvent(AUTH_EXPIRED_EVENT, { detail: error.response.data?.error?.message }),
      );
    }
    return Promise.reject(error);
  },
);

/** Turn any Axios error into a user-facing message from the API's error envelope. */
export function getErrorMessage(error) {
  if (error?.response?.data?.error?.message) return error.response.data.error.message;
  if (error?.code === 'ECONNABORTED') {
    return 'The server took too long to respond. It may be waking up; please try again in a minute.';
  }
  if (error?.request && !error.response) return 'Cannot reach the server. Is the backend running?';
  if (error?.response?.status) {
    return `The server responded with an unexpected error (HTTP ${error.response.status}). Check VITE_API_BASE_URL.`;
  }
  return 'Something went wrong. Please try again.';
}

/** Field-level validation errors ({field: message}) from a 409/422 response. */
export function getFieldErrors(error) {
  return error?.response?.data?.error?.details?.fields ?? {};
}

export default api;
