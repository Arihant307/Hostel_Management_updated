import api from './api.js';

const data = (r) => r.data.data;
const full = (r) => r.data; // { success, data, message }

export const authService = {
  login: (email, password) => api.post('/auth/login', { email, password }).then(data),
  me: () => api.get('/auth/me').then(data),
  updateMe: (payload) => api.patch('/auth/me', payload).then(data),
  logout: () => api.post('/auth/logout'),
  logoutAll: () => api.post('/auth/logout-all'),
  changePassword: (currentPassword, newPassword, confirmPassword) =>
    api
      .post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword ?? newPassword,
      })
      .then(data),

  // Public account flows
  signupPolicy: () => api.get('/auth/signup-policy').then(data),
  signupStudent: (payload) => api.post('/auth/signup/student', payload).then(full),
  signupStaff: (payload) => api.post('/auth/signup/staff', payload).then(full),
  validateInvitation: (code) => api.post('/auth/invitations/validate', { code }).then(data),
  verifyEmail: (token) => api.post('/auth/verify-email', { token }).then(full),
  resendVerification: (email) => api.post('/auth/resend-verification', { email }).then(full),
  forgotPassword: (email) => api.post('/auth/forgot-password', { email }).then(full),
  resetPassword: (token, password, confirmPassword) =>
    api.post('/auth/reset-password', { token, password, confirm_password: confirmPassword }).then(full),
};

export const staffService = {
  list: (params) => api.get('/auth/staff', { params }).then(data),
  get: (id) => api.get(`/auth/staff/${id}`).then(data),
  create: (payload) => api.post('/auth/staff', payload).then(data),
  update: (id, payload) => api.patch(`/auth/staff/${id}`, payload).then(data),
  approve: (id, role) => api.post(`/auth/staff/${id}/approve`, { role }).then(data),
  reject: (id, reason) => api.post(`/auth/staff/${id}/reject`, { reason }).then(data),
  resetPassword: (id, password) => api.post(`/auth/staff/${id}/reset-password`, { password }),
  sendPasswordReset: (id) => api.post(`/auth/staff/${id}/send-password-reset`).then(full),
  history: (id, params) => api.get(`/auth/staff/${id}/history`, { params }).then(data),
};

export const invitationService = {
  list: (params) => api.get('/auth/invitations', { params }).then(data),
  create: (payload) => api.post('/auth/invitations', payload).then(data),
  revoke: (id) => api.post(`/auth/invitations/${id}/revoke`).then(data),
};
