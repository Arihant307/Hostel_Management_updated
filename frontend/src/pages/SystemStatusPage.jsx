import { useCallback, useEffect, useState } from 'react';
import { Building2, Database, RefreshCw, Server } from 'lucide-react';
import api, { API_BASE_URL, getErrorMessage } from '../services/api.js';
import Card from '../components/ui/Card.jsx';
import Badge from '../components/ui/Badge.jsx';
import { formatDateTime } from '../utils/format.js';

/**
 * Phase 1 landing page: verifies the frontend can reach the real Flask API
 * and that the API can reach the database. Replaced by the login screen in Phase 2.
 */
export default function SystemStatusPage() {
  const [state, setState] = useState({ loading: true, data: null, error: null });

  const check = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const res = await api.get('/health');
      setState({ loading: false, data: res.data.data, error: null });
    } catch (err) {
      setState({ loading: false, data: err.response?.data?.data ?? null, error: getErrorMessage(err) });
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  const apiOk = !state.error && state.data?.status === 'ok';
  const dbOk = state.data?.database === 'ok';

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-navy-800 text-white">
            <Building2 className="h-6 w-6" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-navy-900">Hostel Management System</h1>
            <p className="text-sm text-slate-500">System status</p>
          </div>
        </div>

        <Card className="divide-y divide-slate-100">
          <StatusRow
            icon={Server}
            label="API server"
            detail={API_BASE_URL}
            loading={state.loading}
            ok={apiOk}
          />
          <StatusRow
            icon={Database}
            label="Database"
            detail={state.data?.time ? `Checked ${formatDateTime(state.data.time)}` : 'Not checked'}
            loading={state.loading}
            ok={dbOk}
          />
          <div className="flex items-center justify-between gap-4 px-5 py-4">
            <p className="text-sm text-slate-600" role="status" aria-live="polite">
              {state.loading ? 'Checking…' : state.error ?? 'All systems operational.'}
            </p>
            <button
              type="button"
              onClick={check}
              disabled={state.loading}
              className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-navy-800 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${state.loading ? 'animate-spin' : ''}`} aria-hidden="true" />
              Recheck
            </button>
          </div>
        </Card>
      </div>
    </main>
  );
}

function StatusRow({ icon: Icon, label, detail, loading, ok }) {
  return (
    <div className="flex items-center gap-4 px-5 py-4">
      <Icon className="h-5 w-5 shrink-0 text-slate-400" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-slate-800">{label}</p>
        <p className="truncate text-xs text-slate-500">{detail}</p>
      </div>
      {loading ? (
        <span className="h-5 w-20 animate-pulse rounded-full bg-slate-100" />
      ) : (
        <Badge tone={ok ? 'success' : 'danger'}>{ok ? 'Online' : 'Unavailable'}</Badge>
      )}
    </div>
  );
}
