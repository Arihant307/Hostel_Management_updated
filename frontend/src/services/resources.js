import api from './api.js';

const data = (r) => r.data.data;

/** Remove empty values so they are not sent as query parameters. */
export function cleanParams(params = {}) {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined),
  );
}

const crud = (base) => ({
  list: (params) => api.get(base, { params: cleanParams(params) }).then(data),
  get: (id) => api.get(`${base}/${id}`).then(data),
  create: (payload) => api.post(base, payload).then(data),
  update: (id, payload) => api.patch(`${base}/${id}`, payload).then(data),
});

export const studentService = {
  ...crud('/students'),
  me: () => api.get('/students/me').then(data),
  departments: () => api.get('/students/departments').then(data),
  setStatus: (id, isActive) => api.patch(`/students/${id}/status`, { is_active: isActive }).then(data),
  resetPassword: (id, password) => api.post(`/students/${id}/reset-password`, { password }),
  remove: (id) => api.delete(`/students/${id}`),
  approve: (id) => api.post(`/students/${id}/approve`).then(data),
  reject: (id, reason) => api.post(`/students/${id}/reject`, { reason }).then(data),
  sendPasswordReset: (id) => api.post(`/students/${id}/send-password-reset`).then((r) => r.data),
  history: (id, params) => api.get(`/students/${id}/history`, { params: cleanParams(params) }).then(data),
};

export const roomService = {
  ...crud('/rooms'),
  blocks: () => api.get('/rooms/blocks').then(data),
  setStatus: (id, isActive) => api.patch(`/rooms/${id}/status`, { is_active: isActive }).then(data),
};

export const allocationService = {
  list: (params) => api.get('/allocations', { params: cleanParams(params) }).then(data),
  eligibleRooms: (params) => api.get('/allocations/eligible-rooms', { params: cleanParams(params) }).then(data),
  allocate: (payload) => api.post('/allocations', payload).then(data),
  transfer: (id, payload) => api.post(`/allocations/${id}/transfer`, payload).then(data),
  checkout: (id, payload) => api.post(`/allocations/${id}/checkout`, payload).then(data),
};

export const feeService = {
  ...crud('/fees'),
  cancel: (id, reason) => api.post(`/fees/${id}/cancel`, { reason }).then(data),
  generateRent: (payload) => api.post('/fees/generate-rent', payload).then((r) => r.data),
};

export const paymentService = {
  list: (params) => api.get('/payments', { params: cleanParams(params) }).then(data),
  record: (payload) => api.post('/payments', payload).then(data),
  reverse: (id, reason) => api.post(`/payments/${id}/reverse`, { reason }).then(data),
  receipt: (id) => api.get(`/payments/${id}/receipt`).then(data),
};

export const complaintService = {
  ...crud('/complaints'),
  comment: (id, payload) => api.post(`/complaints/${id}/comments`, payload).then(data),
};

export const noticeService = {
  ...crud('/notices'),
  remove: (id) => api.delete(`/notices/${id}`),
};

export const dashboardService = {
  staff: () => api.get('/dashboard/summary').then(data),
  student: () => api.get('/dashboard/student').then(data),
};

export const reportService = {
  summary: (params) => api.get('/reports/summary', { params: cleanParams(params) }).then(data),
  auditLogs: (params) => api.get('/reports/audit-logs', { params: cleanParams(params) }).then(data),
  /** Download a CSV export with the auth header, then hand it to the browser. */
  async download(kind, params) {
    const res = await api.get(`/reports/export/${kind}.csv`, {
      params: cleanParams(params),
      responseType: 'blob',
    });
    const disposition = res.headers['content-disposition'] || '';
    const filename = /filename="([^"]+)"/.exec(disposition)?.[1] || `${kind}.csv`;
    const url = URL.createObjectURL(res.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
};
