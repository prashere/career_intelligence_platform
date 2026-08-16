import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  adminApi,
  type IngestionFetchResult,
  type IngestionRun,
  type SourceHealth,
} from '../api/auth';
import { RunDetailPanel } from '../components/ingestion/TraceTimeline';
import { Button, PageHeader, Skeleton } from '../components/ui/Primitives';
import { useToast } from '../components/ui/Toast';

type Phase = 'hub' | 'running' | 'complete';

type StepId = 'envelope' | 'sources' | 'finalize';

interface StepState {
  id: StepId;
  label: string;
  status: 'pending' | 'running' | 'done' | 'error';
  detail?: string;
}

interface SourceRunState {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'done' | 'skipped' | 'error';
  result?: IngestionFetchResult;
  runId?: string;
}

interface PipelineSummary {
  created: number;
  updated: number;
  discovered: number;
  errors: number;
  skipped: number;
}

const REDIRECT_SECONDS = 8;

function formatTime(iso: string | null | undefined): string {
  if (!iso) return 'n/a';
  return new Date(iso).toLocaleString();
}

export default function AdminIngestion() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();

  const [phase, setPhase] = useState<Phase>('hub');
  const [steps, setSteps] = useState<StepState[]>([
    { id: 'envelope', label: 'Sync interest envelope', status: 'pending' },
    { id: 'sources', label: 'Fetch all active sources', status: 'pending' },
    { id: 'finalize', label: 'Refresh catalog', status: 'pending' },
  ]);
  const [sourceRuns, setSourceRuns] = useState<SourceRunState[]>([]);
  const [summary, setSummary] = useState<PipelineSummary | null>(null);
  const [redirectIn, setRedirectIn] = useState(REDIRECT_SECONDS);
  const [showMonitoring, setShowMonitoring] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const overview = useQuery({
    queryKey: ['admin-ingestion-overview'],
    queryFn: adminApi.ingestionOverview,
    enabled: phase === 'hub' || phase === 'complete',
  });
  const sources = useQuery({
    queryKey: ['admin-ingestion-sources'],
    queryFn: adminApi.ingestionSources,
    enabled: phase !== 'running',
  });
  const runs = useQuery({
    queryKey: ['admin-ingestion-runs'],
    queryFn: () => adminApi.ingestionRuns(10),
    enabled: showMonitoring && phase === 'hub',
  });
  const rejected = useQuery({
    queryKey: ['admin-ingestion-rejected'],
    queryFn: () => adminApi.ingestionRejected(15),
    enabled: showMonitoring && phase === 'hub',
  });
  const runDetail = useQuery({
    queryKey: ['admin-ingestion-run', selectedRunId],
    queryFn: () => adminApi.ingestionRunDetail(selectedRunId!),
    enabled: Boolean(selectedRunId),
  });

  const patchStep = useCallback((id: StepId, patch: Partial<StepState>) => {
    setSteps((prev) => prev.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  }, []);

  const runPipeline = useCallback(async () => {
    const sourceList = (sources.data ?? []).filter((s) => s.is_active);
    if (!sourceList.length) {
      toast.push('No active sources to fetch', 'error');
      return;
    }

    setPhase('running');
    setSummary(null);
    setSteps([
      { id: 'envelope', label: 'Sync interest envelope', status: 'pending' },
      { id: 'sources', label: 'Fetch all active sources', status: 'pending' },
      { id: 'finalize', label: 'Refresh catalog', status: 'pending' },
    ]);
    setSourceRuns(
      sourceList.map((s) => ({ id: s.id, name: s.name, status: 'pending' as const })),
    );

    const totals: PipelineSummary = {
      created: 0,
      updated: 0,
      discovered: 0,
      errors: 0,
      skipped: 0,
    };

    try {
      patchStep('envelope', { status: 'running' });
      await adminApi.syncIngestionEnvelope();
      patchStep('envelope', { status: 'done', detail: 'Profile filter rules loaded' });

      patchStep('sources', { status: 'running' });
      for (let i = 0; i < sourceList.length; i++) {
        const src = sourceList[i];
        setSourceRuns((prev) =>
          prev.map((r) => (r.id === src.id ? { ...r, status: 'running' } : r)),
        );

        try {
          const result = await adminApi.triggerSourceFetch(src.id);
          if (result.skipped) {
            totals.skipped += 1;
            setSourceRuns((prev) =>
              prev.map((r) =>
                r.id === src.id
                  ? { ...r, status: 'skipped', result, runId: result.run_id }
                  : r,
              ),
            );
          } else if (result.ok) {
            totals.created += result.created ?? 0;
            totals.updated += result.updated ?? 0;
            totals.discovered += result.discovered ?? 0;
            setSourceRuns((prev) =>
              prev.map((r) =>
                r.id === src.id ? { ...r, status: 'done', result, runId: result.run_id } : r,
              ),
            );
          } else {
            totals.errors += 1;
            setSourceRuns((prev) =>
              prev.map((r) =>
                r.id === src.id ? { ...r, status: 'error', result, runId: result.run_id } : r,
              ),
            );
          }
        } catch (err) {
          totals.errors += 1;
          setSourceRuns((prev) =>
            prev.map((r) =>
              r.id === src.id
                ? { ...r, status: 'error', result: { ok: false, error: (err as Error).message } }
                : r,
            ),
          );
        }
      }
      patchStep('sources', {
        status: totals.errors ? 'error' : 'done',
        detail: `${totals.created} new · ${totals.updated} updated · ${totals.errors} errors`,
      });

      patchStep('finalize', { status: 'running' });
      await queryClient.invalidateQueries({ queryKey: ['admin-ingestion'] });
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      await queryClient.invalidateQueries({ queryKey: ['feed'] });
      patchStep('finalize', { status: 'done', detail: 'Dashboard feed ready' });

      setSummary(totals);
      setPhase('complete');
      setRedirectIn(REDIRECT_SECONDS);
      toast.push('Ingestion complete, redirecting to dashboard', 'success');
    } catch (err) {
      patchStep('envelope', { status: 'error', detail: (err as Error).message });
      toast.push((err as Error).message, 'error');
      setPhase('hub');
    }
  }, [sources.data, patchStep, queryClient, toast]);

  useEffect(() => {
    if (phase !== 'complete') return;
    if (redirectIn <= 0) {
      navigate('/');
      return;
    }
    const t = window.setTimeout(() => setRedirectIn((n) => n - 1), 1000);
    return () => window.clearTimeout(t);
  }, [phase, redirectIn, navigate]);

  const progressPct =
    sourceRuns.length === 0
      ? 0
      : Math.round(
          (sourceRuns.filter((r) => r.status !== 'pending' && r.status !== 'running').length /
            sourceRuns.length) *
            100,
        );

  if (phase === 'running') {
    return (
      <div className="ingestion-wizard">
        <PageHeader
          title="Running ingestion"
          lead="Fetching opportunities from all active sources. This may take a few minutes."
        />
        <div className="ingestion-progress-card card">
          <div className="ingestion-progress-bar-wrap">
            <div className="ingestion-progress-bar" style={{ width: `${progressPct}%` }} />
          </div>
          <p className="ingestion-progress-label">{progressPct}% complete, processing sources</p>
        </div>

        <ol className="ingestion-steps">
          {steps.map((step) => (
            <li key={step.id} className={`ingestion-step ingestion-step-${step.status}`}>
              <span className="ingestion-step-icon" aria-hidden>
                {step.status === 'running' && <span className="spinner" />}
                {step.status === 'done' && '✓'}
                {step.status === 'error' && '!'}
                {step.status === 'pending' && '○'}
              </span>
              <div>
                <strong>{step.label}</strong>
                {step.detail && <p className="muted-text">{step.detail}</p>}
              </div>
            </li>
          ))}
        </ol>

        <ul className="ingestion-source-progress">
          {sourceRuns.map((run) => (
            <li key={run.id} className={`source-run source-run-${run.status}`}>
              <span className="source-run-status">
                {run.status === 'running' && <span className="spinner spinner-sm" />}
                {run.status === 'done' && '✓'}
                {run.status === 'error' && '✗'}
                {run.status === 'skipped' && 'n/a'}
                {run.status === 'pending' && '·'}
              </span>
              <span className="source-run-name">{run.name}</span>
              {run.result?.ok && (
                <span className="muted-text source-run-meta">
                  +{run.result.created ?? 0} new
                </span>
              )}
              {run.result?.error && (
                <span className="form-error source-run-meta">{run.result.error.slice(0, 60)}</span>
              )}
              {run.runId && (
                <button
                  type="button"
                  className="source-run-trace-link"
                  onClick={() => setSelectedRunId(run.runId!)}
                >
                  View trace
                </button>
              )}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (phase === 'complete' && summary) {
    return (
      <div className="ingestion-wizard ingestion-complete">
        <div className="ingestion-complete-card card">
          <div className="ingestion-complete-icon" aria-hidden>
            ✓
          </div>
          <h2>Ingestion complete</h2>
          <p className="muted-text">
            New opportunities are in the catalog and your dashboard feed is updating.
          </p>
          <dl className="ingestion-summary-stats">
            <div>
              <dt>New</dt>
              <dd>{summary.created}</dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd>{summary.updated}</dd>
            </div>
            <div>
              <dt>Discovered</dt>
              <dd>{summary.discovered}</dd>
            </div>
            <div>
              <dt>Errors</dt>
              <dd>{summary.errors}</dd>
            </div>
          </dl>
          <div className="ingestion-complete-actions">
            <Button variant="primary" onClick={() => navigate('/')}>
              View dashboard
            </Button>
            <Button variant="ghost" onClick={() => setPhase('hub')}>
              Run again
            </Button>
          </div>
          <p className="muted-text ingestion-redirect-hint">
            Redirecting to dashboard in {redirectIn}s…
          </p>
        </div>
      </div>
    );
  }

  if (overview.isLoading || sources.isLoading) {
    return (
      <>
        <PageHeader title="Ingestion" />
        <Skeleton className="skeleton-block" />
      </>
    );
  }

  const stats = overview.data;

  return (
    <div className="ingestion-hub">
      <PageHeader
        title="Ingestion"
        lead="Pull fresh opportunities from configured sources into the shared catalog."
        actions={
          <Link to="/admin/ingestion/playground">
            <Button variant="ghost">Ingestion lab</Button>
          </Link>
        }
      />

      {stats && (
        <div className="kpi-strip ingestion-kpi">
          <div className="kpi">
            <span className="kpi-value">{stats.total_opportunities}</span>
            <span className="kpi-label">Opportunities</span>
          </div>
          <div className="kpi">
            <span className="kpi-value">
              {stats.active_sources}/{stats.total_sources}
            </span>
            <span className="kpi-label">Active sources</span>
          </div>
          <div className="kpi">
            <span className="kpi-value">{stats.sources_with_errors}</span>
            <span className="kpi-label">Sources with errors</span>
          </div>
          <div className="kpi">
            <span className="kpi-value">{formatTime(stats.last_run_at)}</span>
            <span className="kpi-label">Last run</span>
          </div>
        </div>
      )}

      <section className="card ingestion-launch-card">
        <h3 className="panel-title">Run full pipeline</h3>
        <p className="muted-text">
          Syncs your profile filter envelope, fetches every active source sequentially, then
          refreshes the dashboard feed.
        </p>
        <ol className="ingestion-launch-steps">
          <li>Sync interest envelope from compiled profile</li>
          <li>Discover → prefilter → extract → store for each source</li>
          <li>Redirect to dashboard with updated matches</li>
        </ol>
        <Button
          variant="primary"
          className="ingestion-launch-btn"
          onClick={() => void runPipeline()}
          disabled={!sources.data?.some((s) => s.is_active)}
        >
          Start ingestion
        </Button>
        {!sources.data?.some((s) => s.is_active) && (
          <p className="form-error">No active sources. Seed from profile or registry first.</p>
        )}
      </section>

      <button
        type="button"
        className="ingestion-monitor-toggle"
        onClick={() => setShowMonitoring((v) => !v)}
      >
        {showMonitoring ? 'Hide' : 'Show'} monitoring details
      </button>

      {showMonitoring && (
        <>
          <SourceHealthTable sources={sources.data ?? []} />
          <div className="dashboard-grid">
            <RecentRunsPanel
              runs={runs.data ?? []}
              loading={runs.isLoading}
              onSelectRun={setSelectedRunId}
            />
            <RejectedPanel items={rejected.data ?? []} loading={rejected.isLoading} />
          </div>
        </>
      )}

      {selectedRunId && runDetail.data && (
        <div className="card run-detail-overlay">
          <div className="run-detail-overlay-head">
            <h3 className="panel-title">Run trace</h3>
            <Button variant="ghost" onClick={() => setSelectedRunId(null)}>
              Close
            </Button>
          </div>
          <RunDetailPanel
            sourceName={runDetail.data.source_name}
            run={runDetail.data.run}
            traceEvents={runDetail.data.trace_events}
            rejectedItems={runDetail.data.rejected_items}
          />
        </div>
      )}
    </div>
  );
}

function SourceHealthTable({ sources }: { sources: SourceHealth[] }) {
  return (
    <section className="card dashboard-panel">
      <h3 className="panel-title">Source health</h3>
      <div className="ingestion-table-wrap">
        <table className="ingestion-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Mode</th>
              <th>Last fetch</th>
              <th>Opps</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((src) => (
              <tr key={src.id}>
                <td>
                  <strong>{src.name}</strong>
                  {src.registry_id && <span className="muted-text block">{src.registry_id}</span>}
                </td>
                <td>{src.fetch_mode}</td>
                <td>{formatTime(src.last_fetched_at)}</td>
                <td>{src.opportunity_count}</td>
                <td>
                  {src.last_error ? (
                    <span className="badge badge-error" title={src.last_error}>
                      Error
                    </span>
                  ) : src.is_active ? (
                    <span className="badge">OK</span>
                  ) : (
                    <span className="badge">Inactive</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RecentRunsPanel({
  runs,
  loading,
  onSelectRun,
}: {
  runs: IngestionRun[];
  loading: boolean;
  onSelectRun?: (runId: string) => void;
}) {
  if (loading) return <Skeleton className="skeleton-block" />;
  return (
    <section className="card dashboard-panel">
      <h3 className="panel-title">Recent runs</h3>
      {runs.length === 0 ? (
        <p className="muted-text">No ingestion runs yet.</p>
      ) : (
        <ul className="ingestion-run-list">
          {runs.map((run) => (
            <li key={run.id}>
              <button
                type="button"
                className="run-list-btn"
                onClick={() => onSelectRun?.(run.id)}
              >
                <div className="run-head">
                  <strong>{run.status}</strong>
                  <span className="muted-text">{formatTime(run.started_at)}</span>
                </div>
                <p className="muted-text">
                  discovered {run.discovered} · +{run.created} new · {run.prefilter_drop} filtered ·{' '}
                  {run.errors} errors
                </p>
                {(run.meta?.mode as string) && (
                  <span className="badge badge-muted">{String(run.meta.mode)}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function RejectedPanel({
  items,
  loading,
}: {
  items: Awaited<ReturnType<typeof adminApi.ingestionRejected>>;
  loading: boolean;
}) {
  if (loading) return <Skeleton className="skeleton-block" />;
  return (
    <section className="card dashboard-panel">
      <h3 className="panel-title">Recent rejections</h3>
      {items.length === 0 ? (
        <p className="muted-text">No rejected items.</p>
      ) : (
        <ul className="ingestion-run-list compact">
          {items.map((item) => (
            <li key={item.id}>
              <span className="badge badge-muted">{item.stage}</span>
              <strong>{item.reason}</strong>
              <p className="muted-text">{item.title || item.url}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
