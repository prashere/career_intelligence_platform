import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  adminApi,
  type IngestionRun,
  type PlaygroundMode,
  type PlaygroundResult,
  type PreviewItem,
  type RelevanceVerdict,
  type StrategyProbe,
} from '../api/auth';
import { ApiError } from '../api/http';
import { useAuth } from '../auth/AuthContext';
import { PreviewItemsTable, type PreviewFilter } from '../components/ingestion/PreviewItemsTable';
import { StrategyProbesTable } from '../components/ingestion/StrategyProbesTable';
import { TraceTimeline } from '../components/ingestion/TraceTimeline';
import { Button, PageHeader, Skeleton } from '../components/ui/Primitives';
import { useToast } from '../components/ui/Toast';

type TargetKind = 'registry' | 'source';
type MonitorTab = 'overview' | 'probes' | 'items' | 'trace' | 'rejections' | 'meta';

const MODES: { value: PlaygroundMode; label: string; hint: string }[] = [
  {
    value: 'discover',
    label: 'Discover only',
    hint: 'Run discover strategies and relevance triage. No extract or persist.',
  },
  {
    value: 'dry_run',
    label: 'Full pipeline, dry run',
    hint: 'Requires a seeded DB source. Full pipeline without writing opportunities.',
  },
  {
    value: 'persist',
    label: 'Full pipeline, persist',
    hint: 'Requires a seeded DB source. Writes opportunities like production.',
  },
];

function formatTime(iso: string | null | undefined): string {
  if (!iso) return 'n/a';
  return new Date(iso).toLocaleString();
}

function runDuration(run: IngestionRun): string {
  const fromMeta = run.meta?.duration_s;
  if (typeof fromMeta === 'number') return `${fromMeta.toFixed(1)}s`;
  if (!run.finished_at) return 'running';
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
  return `${(ms / 1000).toFixed(1)}s`;
}

function isPlaygroundRun(run: IngestionRun): boolean {
  const mode = String(run.meta?.mode ?? '');
  return mode.startsWith('playground');
}

function runTitle(run: IngestionRun): string {
  const registryId = run.meta?.registry_id as string | undefined;
  if (registryId) return registryId;
  if (run.source_id) return `source ${run.source_id.slice(0, 8)}`;
  return 'unknown';
}

function probesFromRun(run: IngestionRun | undefined, fallback: PlaygroundResult | null): StrategyProbe[] {
  const fromRun = run?.meta?.strategy_probes;
  if (Array.isArray(fromRun) && fromRun.length) return fromRun as StrategyProbe[];
  return (fallback?.strategy_probes as StrategyProbe[] | undefined) ?? [];
}

function previewFromRun(run: IngestionRun | undefined, fallback: PlaygroundResult | null): PreviewItem[] {
  const fromRun = run?.meta?.preview_items;
  if (Array.isArray(fromRun) && fromRun.length) return fromRun as PreviewItem[];
  return fallback?.preview_items ?? [];
}

function verdictOf(item: PreviewItem): RelevanceVerdict {
  if (item.verdict) return item.verdict;
  return item.prefilter_pass === false ? 'reject' : 'admit';
}

function countVerdicts(items: PreviewItem[]): Record<RelevanceVerdict, number> {
  return items.reduce(
    (acc, item) => {
      acc[verdictOf(item)] += 1;
      return acc;
    },
    { admit: 0, investigate: 0, reject: 0 } as Record<RelevanceVerdict, number>,
  );
}

function apiLoadError(error: unknown, resource: string): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return `Your session expired or is no longer valid. Sign in again to load ${resource}.`;
    }
    if (error.status === 403) {
      return `Administrator access is required to load ${resource}.`;
    }
  }
  return `Could not load ${resource}. Check API logs and refresh the page.`;
}

export default function AdminIngestionPlayground() {
  const toast = useToast();
  const navigate = useNavigate();
  const { logout } = useAuth();
  const queryClient = useQueryClient();

  const [targetKind, setTargetKind] = useState<TargetKind>('registry');
  const [registryId, setRegistryId] = useState('');
  const [sourceId, setSourceId] = useState('');
  const [mode, setMode] = useState<PlaygroundMode>('discover');
  const [maxItems, setMaxItems] = useState(25);
  const [includeBrowser, setIncludeBrowser] = useState(false);
  const [resolveInvestigate, setResolveInvestigate] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<PlaygroundResult | null>(null);
  const [activeTab, setActiveTab] = useState<MonitorTab>('overview');
  const [itemFilter, setItemFilter] = useState<PreviewFilter>('all');
  const [runHistoryFilter, setRunHistoryFilter] = useState<'lab' | 'all'>('lab');

  const registry = useQuery({
    queryKey: ['admin-ingestion-registry'],
    queryFn: adminApi.ingestionRegistry,
  });
  const dbSources = useQuery({
    queryKey: ['admin-ingestion-sources'],
    queryFn: adminApi.ingestionSources,
  });
  const runs = useQuery({
    queryKey: ['admin-ingestion-runs-lab'],
    queryFn: () => adminApi.ingestionRuns(50),
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasRunning = data?.some((r) => r.status === 'running');
      return hasRunning ? 2000 : false;
    },
  });

  const runDetail = useQuery({
    queryKey: ['admin-ingestion-run', selectedRunId],
    queryFn: () => adminApi.ingestionRunDetail(selectedRunId!),
    enabled: Boolean(selectedRunId),
    refetchInterval: (query) => {
      const status = query.state.data?.run.status;
      return status === 'running' ? 2000 : false;
    },
  });

  const registryAggregators = useMemo(() => {
    return [...(registry.data ?? [])].sort((a, b) => a.name.localeCompare(b.name));
  }, [registry.data]);

  const selectedRegistry = useMemo(
    () => registry.data?.find((e) => e.id === registryId),
    [registry.data, registryId],
  );
  const selectedSource = useMemo(
    () => dbSources.data?.find((s) => s.id === sourceId),
    [dbSources.data, sourceId],
  );

  const runHistory = useMemo(() => {
    const list = runs.data ?? [];
    if (runHistoryFilter === 'lab') return list.filter(isPlaygroundRun);
    return list;
  }, [runs.data, runHistoryFilter]);

  const activeRun = runDetail.data?.run;
  const probes = probesFromRun(activeRun, lastResult);
  const previewItems = previewFromRun(activeRun, lastResult);
  const verdictCounts = useMemo(() => countVerdicts(previewItems), [previewItems]);
  const winningStrategy =
    (activeRun?.meta?.winning_strategy as string | undefined) ?? lastResult?.winning_strategy;

  const runPlayground = useMutation({
    mutationFn: () => {
      const matchedSource = dbSources.data?.find((s) => s.registry_id === registryId);
      const effectiveSourceId =
        targetKind === 'source' ? sourceId : mode !== 'discover' ? matchedSource?.id : undefined;

      if (mode !== 'discover') {
        if (!effectiveSourceId) {
          throw new Error('Select a seeded DB source for dry run or persist.');
        }
        return adminApi.runPlayground({
          source_id: effectiveSourceId,
          mode,
          max_items: maxItems,
          include_browser: includeBrowser,
        });
      }

      return adminApi.runPlayground({
        registry_id: registryId,
        mode,
        max_items: maxItems,
        include_browser: includeBrowser,
        resolve_investigate: resolveInvestigate,
      });
    },
    onSuccess: (result) => {
      setLastResult(result);
      if (result.run_id) {
        setSelectedRunId(result.run_id);
        void queryClient.invalidateQueries({ queryKey: ['admin-ingestion-run', result.run_id] });
      }
      void queryClient.invalidateQueries({ queryKey: ['admin-ingestion-runs-lab'] });
      setActiveTab(result.ok ? 'overview' : 'trace');
      if (result.ok) {
        toast.push(
          `Run complete: ${result.discovered ?? 0} discovered, ${result.admit ?? 0} admit, ` +
            `${result.investigate ?? 0} investigate, ${result.reject ?? 0} reject`,
          'success',
        );
      } else {
        toast.push(result.error ?? 'Run failed', 'error');
      }
    },
    onError: (err: Error) => toast.push(err.message, 'error'),
  });

  const canRun =
    !runPlayground.isPending &&
    ((targetKind === 'registry' && Boolean(registryId)) ||
      (targetKind === 'source' && Boolean(sourceId)));

  const needsBrowserWarning =
    selectedRegistry?.fetch_mode === 'browser' && !includeBrowser && targetKind === 'registry';

  useEffect(() => {
    if (targetKind === 'registry') setMode('discover');
  }, [targetKind]);

  function exportRunJson() {
    if (!runDetail.data) return;
    const blob = new Blob([JSON.stringify(runDetail.data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ingestion-run-${selectedRunId?.slice(0, 8) ?? 'export'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const tabs: { id: MonitorTab; label: string; count?: number }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'probes', label: 'Strategies', count: probes.length },
    { id: 'items', label: 'Discovered', count: previewItems.length },
    { id: 'trace', label: 'Trace', count: runDetail.data?.trace_events.length },
    { id: 'rejections', label: 'Rejections', count: runDetail.data?.rejected_items.length },
    { id: 'meta', label: 'Raw meta' },
  ];

  return (
    <div className="ingestion-playground">
      <PageHeader
        title="Ingestion lab"
        lead="Test sources end to end, compare strategy attempts, inspect traces, and review prefilter drops before production runs."
        actions={
          <Link to="/admin/ingestion">
            <Button variant="ghost">Back to ingestion</Button>
          </Link>
        }
      />

      <div className="playground-layout">
        <aside className="playground-sidebar">
          <section className="card playground-controls">
            <h3 className="playground-section-title">Run configuration</h3>

            <div className="playground-target-toggle">
              <button
                type="button"
                className={targetKind === 'registry' ? 'active' : undefined}
                onClick={() => setTargetKind('registry')}
              >
                Registry
              </button>
              <button
                type="button"
                className={targetKind === 'source' ? 'active' : undefined}
                onClick={() => setTargetKind('source')}
              >
                DB source
              </button>
            </div>

            {targetKind === 'registry' ? (
              <label className="playground-field">
                <span>Aggregator</span>
                {registry.isError && (
                  <div className="form-error">
                    <p>{apiLoadError(registry.error, 'the source registry')}</p>
                    {registry.error instanceof ApiError && registry.error.status === 401 && (
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => {
                          logout();
                          navigate('/login', { state: { from: '/admin/ingestion/playground' } });
                        }}
                      >
                        Sign in again
                      </Button>
                    )}
                  </div>
                )}
                {registry.isLoading && <Skeleton className="skeleton-inline" />}
                <select
                  value={registryId}
                  onChange={(e) => setRegistryId(e.target.value)}
                  disabled={registry.isLoading || registry.isError}
                >
                  <option value="">
                    {registry.isLoading
                      ? 'Loading aggregators…'
                      : `Select aggregator (${registryAggregators.length})`}
                  </option>
                  {registryAggregators.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      {entry.name}
                    </option>
                  ))}
                </select>
                {selectedRegistry && (
                  <p className="muted-text playground-aggregator-hint">
                    {selectedRegistry.discover_kind ?? selectedRegistry.type ?? 'unknown strategy'}
                    {selectedRegistry.fetch_mode && selectedRegistry.fetch_mode !== 'http'
                      ? ` · ${selectedRegistry.fetch_mode}`
                      : ''}
                  </p>
                )}
              </label>
            ) : (
              <label className="playground-field">
                <span>Seeded source</span>
                <select value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
                  <option value="">Choose DB source</option>
                  {(dbSources.data ?? []).map((source) => (
                    <option key={source.id} value={source.id}>
                      {source.name} ({source.registry_id ?? 'no registry'})
                      {!source.is_active ? ', inactive' : ''}
                    </option>
                  ))}
                </select>
              </label>
            )}

            {selectedSource && targetKind === 'source' && (
              <dl className="playground-source-meta">
                <div>
                  <dt>Registry id</dt>
                  <dd>{selectedSource.registry_id ?? 'n/a'}</dd>
                </div>
                <div>
                  <dt>Fetch</dt>
                  <dd>{selectedSource.fetch_mode}</dd>
                </div>
                <div>
                  <dt>Failures</dt>
                  <dd>{selectedSource.consecutive_failures}</dd>
                </div>
              </dl>
            )}

            {targetKind === 'source' && (
              <fieldset className="playground-mode">
                <legend>Pipeline mode</legend>
                {MODES.map((m) => (
                  <label key={m.value}>
                    <input
                      type="radio"
                      name="playground-mode"
                      value={m.value}
                      checked={mode === m.value}
                      onChange={() => setMode(m.value)}
                    />
                    <span>
                      <strong>{m.label}</strong>
                      <span className="muted-text playground-mode-hint">{m.hint}</span>
                    </span>
                  </label>
                ))}
              </fieldset>
            )}

            <div className="playground-options-grid">
              <label className="playground-field">
                <span>Max preview items</span>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={maxItems}
                  onChange={(e) => setMaxItems(Number(e.target.value))}
                />
              </label>
              <label className="playground-check playground-check-inline">
                <input
                  type="checkbox"
                  checked={includeBrowser}
                  onChange={(e) => setIncludeBrowser(e.target.checked)}
                />
                Playwright browser
              </label>
            </div>

            {mode === 'discover' && (
              <label className="playground-check playground-check-block">
                <input
                  type="checkbox"
                  checked={resolveInvestigate}
                  onChange={(e) => setResolveInvestigate(e.target.checked)}
                />
                <span>
                  Resolve uncertain items
                  <span className="muted-text playground-mode-hint">
                    Fetches detail pages for items scored as investigate and re-scores them, so the
                    preview matches what production would decide. Slower.
                  </span>
                </span>
              </label>
            )}

            {needsBrowserWarning && (
              <p className="form-error">Browser fallback may be needed for this aggregator.</p>
            )}
            {mode !== 'discover' && targetKind === 'source' && !sourceId && (
              <p className="form-error">Select a DB source for dry run or persist.</p>
            )}

            <Button
              variant="primary"
              className="playground-run-btn"
              disabled={
                !canRun ||
                (mode !== 'discover' && targetKind === 'source' && !sourceId)
              }
              onClick={() => void runPlayground.mutate()}
            >
              {runPlayground.isPending
                ? 'Running…'
                : targetKind === 'registry'
                  ? 'Run discover'
                  : 'Run test'}
            </Button>
          </section>

          <section className="card playground-run-history">
            <div className="playground-run-history-head">
              <h3 className="playground-section-title">Run history</h3>
              <select
                value={runHistoryFilter}
                onChange={(e) => setRunHistoryFilter(e.target.value as 'lab' | 'all')}
                aria-label="Run history filter"
              >
                <option value="lab">Lab runs</option>
                <option value="all">All runs</option>
              </select>
            </div>
            {runs.isLoading && <Skeleton className="skeleton-block" />}
            {!runs.isLoading && runHistory.length === 0 && (
              <p className="muted-text">No runs yet. Start a test to populate history.</p>
            )}
            <ul className="playground-run-list">
              {runHistory.map((run) => (
                <li key={run.id}>
                  <button
                    type="button"
                    className={`playground-run-item${selectedRunId === run.id ? ' active' : ''}`}
                    onClick={() => {
                      setSelectedRunId(run.id);
                      setLastResult(null);
                      setActiveTab('overview');
                    }}
                  >
                    <div className="playground-run-item-top">
                      <strong>{runTitle(run)}</strong>
                      <span className={`badge badge-${run.status === 'completed' ? 'success' : run.status === 'failed' ? 'error' : 'warning'}`}>
                        {run.status}
                      </span>
                    </div>
                    <div className="playground-run-item-meta muted-text">
                      <span>{String(run.meta?.mode ?? 'production')}</span>
                      <span>{run.discovered} discovered</span>
                      <span>{formatTime(run.started_at)}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </aside>

        <main className="playground-main">
          {runPlayground.isPending && (
            <section className="card playground-running-banner">
              <span className="spinner spinner-sm" aria-hidden />
              Running test, trace events will appear when the run completes…
            </section>
          )}

          {!selectedRunId && !runPlayground.isPending && (
            <section className="card playground-empty-state">
              {selectedRegistry && targetKind === 'registry' ? (
                <>
                  <h3>{selectedRegistry.name}</h3>
                  <dl className="playground-source-meta playground-source-meta-inline">
                    <div>
                      <dt>Strategy</dt>
                      <dd>{selectedRegistry.discover_kind ?? selectedRegistry.type ?? 'n/a'}</dd>
                    </div>
                    <div>
                      <dt>Fetch</dt>
                      <dd>{selectedRegistry.fetch_mode ?? 'http'}</dd>
                    </div>
                    {selectedRegistry.url && (
                      <div className="playground-source-meta-wide">
                        <dt>URL</dt>
                        <dd className="playground-url">{selectedRegistry.url}</dd>
                      </div>
                    )}
                  </dl>
                  <p className="muted-text">
                    Click <strong>Run discover</strong> to test this aggregator. Pick another from
                    the dropdown to test the next one.
                  </p>
                </>
              ) : (
                <>
                  <h3>Monitoring panel</h3>
                  <p className="muted-text">
                    {targetKind === 'registry'
                      ? 'Select an aggregator from the dropdown, run discover, then inspect strategy probes, discovered URLs, and traces here.'
                      : 'Configure a run on the left, then inspect strategy probes, discovered URLs, trace events, and rejections here.'}
                  </p>
                </>
              )}
            </section>
          )}

          {selectedRunId && runDetail.isLoading && !runDetail.data && (
            <Skeleton className="skeleton-block" />
          )}

          {selectedRunId && runDetail.data && (
            <section className="card playground-monitor">
              <header className="playground-monitor-head">
                <div>
                  <h3>{runDetail.data.source_name ?? runTitle(runDetail.data.run)}</h3>
                  <p className="muted-text">
                    Run <code>{runDetail.data.run.id}</code> · {String(runDetail.data.run.meta?.mode ?? 'production')} ·{' '}
                    {runDuration(runDetail.data.run)}
                  </p>
                </div>
                <div className="playground-monitor-actions">
                  <span className={`badge badge-${runDetail.data.run.status === 'completed' ? 'success' : runDetail.data.run.status === 'failed' ? 'error' : 'warning'}`}>
                    {runDetail.data.run.status}
                  </span>
                  <Button variant="ghost" onClick={exportRunJson}>
                    Export JSON
                  </Button>
                </div>
              </header>

              <nav className="playground-tabs" aria-label="Run monitoring sections">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    className={activeTab === tab.id ? 'active' : undefined}
                    onClick={() => setActiveTab(tab.id)}
                  >
                    {tab.label}
                    {tab.count != null && tab.count > 0 ? ` (${tab.count})` : ''}
                  </button>
                ))}
              </nav>

              {activeTab === 'overview' && (
                <div className="playground-tab-panel">
                  <dl className="run-detail-stats">
                    <div><dt>Discovered</dt><dd>{runDetail.data.run.discovered}</dd></div>
                    <div><dt>Admit</dt><dd>{verdictCounts.admit}</dd></div>
                    <div><dt>Investigate</dt><dd>{verdictCounts.investigate}</dd></div>
                    <div><dt>Reject</dt><dd>{verdictCounts.reject}</dd></div>
                    <div><dt>Created</dt><dd>{runDetail.data.run.created}</dd></div>
                    <div><dt>Errors</dt><dd>{runDetail.data.run.errors}</dd></div>
                  </dl>
                  {previewItems.length > 0 && (
                    <p className="muted-text">
                      Investigate means the gate did not have enough text to decide. Production
                      fetches those detail pages and scores them again before admitting or
                      rejecting. Enable <strong>Resolve uncertain items</strong> to do the same here.
                    </p>
                  )}
                  {winningStrategy && (
                    <p>
                      Winning strategy: <strong>{winningStrategy}</strong>
                    </p>
                  )}
                  {runDetail.data.run.error_message && (
                    <p className="form-error">{runDetail.data.run.error_message}</p>
                  )}
                  <p className="muted-text">
                    Started {formatTime(runDetail.data.run.started_at)}
                    {runDetail.data.run.finished_at && `, finished ${formatTime(runDetail.data.run.finished_at)}`}
                  </p>
                </div>
              )}

              {activeTab === 'probes' && (
                <div className="playground-tab-panel">
                  <StrategyProbesTable probes={probes} winningStrategy={winningStrategy} />
                </div>
              )}

              {activeTab === 'items' && (
                <div className="playground-tab-panel">
                  <div className="playground-items-toolbar">
                    <label>
                      Show
                      <select
                        value={itemFilter}
                        onChange={(e) => setItemFilter(e.target.value as PreviewFilter)}
                      >
                        <option value="all">All items ({previewItems.length})</option>
                        <option value="admit">Admit ({verdictCounts.admit})</option>
                        <option value="investigate">Investigate ({verdictCounts.investigate})</option>
                        <option value="reject">Reject ({verdictCounts.reject})</option>
                      </select>
                    </label>
                    <span className="muted-text">
                      Previewing up to {maxItems} discovered URLs scored by the relevance gate.
                      Open <strong>Signals</strong> on any row to see the evidence behind its score.
                    </span>
                  </div>
                  <PreviewItemsTable items={previewItems} filter={itemFilter} />
                </div>
              )}

              {activeTab === 'trace' && (
                <div className="playground-tab-panel">
                  <TraceTimeline events={runDetail.data.trace_events} showFilters />
                </div>
              )}

              {activeTab === 'rejections' && (
                <div className="playground-tab-panel">
                  {runDetail.data.rejected_items.length === 0 ? (
                    <p className="muted-text">No rejections recorded for this run.</p>
                  ) : (
                    <div className="lab-table-wrap">
                      <table className="lab-table">
                        <thead>
                          <tr>
                            <th>Stage</th>
                            <th>Reason</th>
                            <th>Score</th>
                            <th>Title</th>
                            <th>URL</th>
                          </tr>
                        </thead>
                        <tbody>
                          {runDetail.data.rejected_items.map((item) => {
                            const score = item.meta?.score;
                            const evidence = item.meta?.evidence;
                            return (
                              <tr key={item.id}>
                                <td><span className="badge badge-muted">{item.stage}</span></td>
                                <td>
                                  {item.reason}
                                  {Array.isArray(evidence) && evidence.length > 0 && (
                                    <span className="lab-evidence">{evidence.join(', ')}</span>
                                  )}
                                </td>
                                <td>{typeof score === 'number' ? score.toFixed(2) : 'n/a'}</td>
                                <td>{item.title ?? 'n/a'}</td>
                                <td className="lab-cell-urls">
                                  {item.url ? (
                                    <a href={item.url} target="_blank" rel="noreferrer">
                                      {item.url}
                                    </a>
                                  ) : (
                                    'n/a'
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'meta' && (
                <div className="playground-tab-panel">
                  <pre className="trace-payload playground-meta-json">
                    {JSON.stringify(runDetail.data.run.meta, null, 2)}
                  </pre>
                </div>
              )}
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
