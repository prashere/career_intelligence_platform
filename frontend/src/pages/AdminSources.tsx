import { useCallback, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  adminApi,
  type CandidateApprovalPayload,
  type CandidateSource,
  type DiscoveryRun,
  type SourceHealth,
} from '../api/auth';
import { Button, PageHeader, Skeleton } from '../components/ui/Primitives';
import { Modal } from '../components/ui/Modal';
import { useToast } from '../components/ui/Toast';

function formatTime(iso: string | null | undefined): string {
  if (!iso) return 'n/a';
  return new Date(iso).toLocaleString();
}

function stageLabel(stage: string): string {
  switch (stage) {
    case 'searching':
      return 'Searching…';
    case 'evaluating':
      return 'Evaluating…';
    case 'done':
      return 'Done';
    default:
      return stage;
  }
}

function verdictLabel(verdict: string): string {
  switch (verdict) {
    case 'recurring_source':
      return 'Recurring source';
    case 'one_off_page':
      return 'One-off page';
    default:
      return 'Unclear';
  }
}

function structureSummary(config: Record<string, unknown>): string {
  const discover = (config.discover as Record<string, unknown>) || {};
  if (discover.feed_urls) return 'RSS feed';
  if (discover.kind === 'html' || discover.entry_urls) return 'HTML listing';
  return 'Unknown structure';
}

export default function AdminSources() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [approveCandidate, setApproveCandidate] = useState<CandidateSource | null>(null);
  const [approvalForm, setApprovalForm] = useState<CandidateApprovalPayload | null>(null);
  const [parserJson, setParserJson] = useState('');

  const runs = useQuery({
    queryKey: ['admin-discovery-runs'],
    queryFn: () => adminApi.listDiscoveryRuns(15),
  });

  const sources = useQuery({
    queryKey: ['admin-ingestion-sources'],
    queryFn: adminApi.ingestionSources,
  });

  const activeRun = useQuery({
    queryKey: ['admin-discovery-run', activeRunId],
    queryFn: () => adminApi.getDiscoveryRun(activeRunId!),
    enabled: Boolean(activeRunId),
    refetchInterval: (query) => {
      const data = query.state.data as DiscoveryRun | undefined;
      return data?.status === 'running' ? 2000 : false;
    },
  });

  const candidates = useQuery({
    queryKey: ['admin-discovery-candidates', activeRunId],
    queryFn: () => adminApi.listDiscoveryCandidates(activeRunId!),
    enabled: Boolean(activeRunId),
    refetchInterval: activeRun.data?.status === 'running' ? 2000 : false,
  });

  const triggerRun = useMutation({
    mutationFn: adminApi.triggerSourceDiscovery,
    onSuccess: (run) => {
      setActiveRunId(run.id);
      queryClient.invalidateQueries({ queryKey: ['admin-discovery-runs'] });
      toast.push('Discovery run started', 'success');
    },
    onError: (err: Error) => toast.push(err.message, 'error'),
  });

  const rejectMutation = useMutation({
    mutationFn: (id: string) => adminApi.rejectDiscoveryCandidate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-discovery-candidates', activeRunId] });
      toast.push('Candidate rejected', 'success');
    },
    onError: (err: Error) => toast.push(err.message, 'error'),
  });

  const approveMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: CandidateApprovalPayload }) =>
      adminApi.approveDiscoveryCandidate(id, body),
    onSuccess: () => {
      setApproveCandidate(null);
      setApprovalForm(null);
      queryClient.invalidateQueries({ queryKey: ['admin-discovery-candidates', activeRunId] });
      queryClient.invalidateQueries({ queryKey: ['admin-ingestion-sources'] });
      toast.push('Source approved and activated', 'success');
    },
    onError: (err: Error) => toast.push(err.message, 'error'),
  });

  useEffect(() => {
    if (!activeRunId && runs.data?.length) {
      setActiveRunId(runs.data[0].id);
    }
  }, [runs.data, activeRunId]);

  const openApprove = useCallback(async (candidate: CandidateSource) => {
    try {
      const defaults = await adminApi.getCandidateApprovalDefaults(candidate.id);
      setApproveCandidate(candidate);
      setApprovalForm(defaults);
      setParserJson(JSON.stringify(defaults.parser_config, null, 2));
    } catch (err) {
      toast.push(err instanceof Error ? err.message : 'Failed to load defaults', 'error');
    }
  }, [toast]);

  const confirmApprove = () => {
    if (!approveCandidate || !approvalForm) return;
    try {
      const parser_config = JSON.parse(parserJson) as Record<string, unknown>;
      approveMutation.mutate({
        id: approveCandidate.id,
        body: { ...approvalForm, parser_config },
      });
    } catch {
      toast.push('Parser config must be valid JSON', 'error');
    }
  };

  const run = activeRun.data;
  const candidateList = candidates.data ?? [];

  return (
    <>
      <PageHeader
        eyebrow="Management"
        title="Sources"
        lead="Discover recurring listing sites for your profile, review parser configs, and manage the live registry."
      />

      <section className="card dashboard-panel">
        <h3 className="panel-title">Discover</h3>
        <p className="muted-text dashboard-match-sub">
          On-demand search. Proposals only — nothing is added to the live registry without your review.
        </p>
        <div className="form-nav" style={{ marginTop: '0.75rem' }}>
          <Button
            variant="gold"
            onClick={() => triggerRun.mutate()}
            disabled={triggerRun.isPending || run?.status === 'running'}
          >
            {triggerRun.isPending ? 'Starting…' : 'Discover new sources'}
          </Button>
          {run && (
            <span className="muted-text">
              Status: {run.status} · {stageLabel(run.current_stage)}
              {run.status === 'running' && ' (updating…)'}
            </span>
          )}
        </div>

        {run?.error_message && (
          <p className="field-hint" style={{ color: 'var(--burgundy)' }}>{run.error_message}</p>
        )}

        {candidates.isLoading && activeRunId ? (
          <Skeleton className="dashboard-match-skeleton" />
        ) : candidateList.length > 0 ? (
          <div className="dashboard-match-list" style={{ marginTop: '1rem' }}>
            {candidateList.map((c) => (
              <article key={c.id} className="opp-card opp-card-v2">
                <div className="opp-card-body">
                  <header className="opp-card-header">
                    <div className="opp-card-header-main">
                      <h4 className="opp-title">{c.domain}</h4>
                      <p className="opp-meta">{c.discovered_url}</p>
                    </div>
                    <div className="opp-card-header-aside">
                      <span className="opp-deadline-chip deadline-soon">
                        {Math.round(c.confidence * 100)}%
                      </span>
                    </div>
                  </header>
                  <div className="opp-chip-row">
                    <span className="badge badge-navy">{verdictLabel(c.evaluation_verdict)}</span>
                    <span className="badge badge-muted">{structureSummary(c.guessed_parser_config)}</span>
                    <span className="badge badge-muted">{c.status}</span>
                  </div>
                  <p className="opp-fit-reason"><strong>Relevance:</strong> {c.relevance_notes}</p>
                  <p className="opp-fit-reason"><strong>Legitimacy:</strong> {c.legitimacy_notes}</p>
                  {c.status === 'pending_review' && (
                    <footer className="opp-card-toolbar">
                      <div className="opp-toolbar-start">
                        <button
                          type="button"
                          className="opp-action-btn"
                          onClick={() => openApprove(c)}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          className="opp-action-btn opp-action-dismiss"
                          disabled={rejectMutation.isPending}
                          onClick={() => {
                            if (window.confirm('Reject this candidate?')) {
                              rejectMutation.mutate(c.id);
                            }
                          }}
                        >
                          Reject
                        </button>
                      </div>
                    </footer>
                  )}
                </div>
              </article>
            ))}
          </div>
        ) : activeRunId ? (
          <p className="muted-text" style={{ marginTop: '1rem' }}>
            No candidates yet for this run.
          </p>
        ) : null}
      </section>

      <section className="card dashboard-panel">
        <h3 className="panel-title">Registry</h3>
        {sources.isLoading ? (
          <Skeleton />
        ) : (
          <table className="ingestion-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Failures</th>
                <th>Last fetch</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {(sources.data ?? []).map((s: SourceHealth) => (
                <tr key={s.id}>
                  <td>{s.name}</td>
                  <td>{s.is_active ? 'Active' : 'Inactive'}</td>
                  <td>{s.consecutive_failures}</td>
                  <td>{formatTime(s.last_fetched_at)}</td>
                  <td className="muted-text">{s.last_error?.slice(0, 80) || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card dashboard-panel">
        <h3 className="panel-title">Discovery run log</h3>
        {runs.isLoading ? (
          <Skeleton />
        ) : (
          <table className="ingestion-table">
            <thead>
              <tr>
                <th>Started</th>
                <th>Status</th>
                <th>Queries</th>
                <th>Found</th>
                <th>Evaluated</th>
              </tr>
            </thead>
            <tbody>
              {(runs.data ?? []).map((r: DiscoveryRun) => (
                <tr
                  key={r.id}
                  className={r.id === activeRunId ? 'row-selected' : undefined}
                  onClick={() => setActiveRunId(r.id)}
                  style={{ cursor: 'pointer' }}
                >
                  <td>{formatTime(r.triggered_at)}</td>
                  <td>{r.status}</td>
                  <td>{r.queries_used?.length ?? 0}</td>
                  <td>{r.candidates_found}</td>
                  <td>{r.candidates_evaluated}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {approveCandidate && approvalForm && (
        <Modal
          title={`Approve source — ${approveCandidate.domain}`}
          onClose={() => {
            setApproveCandidate(null);
            setApprovalForm(null);
          }}
          actions={
            <>
              <Button
                variant="secondary"
                onClick={() => {
                  setApproveCandidate(null);
                  setApprovalForm(null);
                }}
              >
                Cancel
              </Button>
              <Button
                variant="gold"
                onClick={confirmApprove}
                disabled={approveMutation.isPending}
              >
                {approveMutation.isPending ? 'Activating…' : 'Confirm and activate'}
              </Button>
            </>
          }
        >
          <div className="form-stack">
            <label className="dashboard-filter-field">
              <span className="dashboard-filter-label">Registry ID</span>
              <input
                className="form-control"
                value={approvalForm.registry_id}
                onChange={(e) =>
                  setApprovalForm({ ...approvalForm, registry_id: e.target.value })
                }
              />
            </label>
            <label className="dashboard-filter-field">
              <span className="dashboard-filter-label">Name</span>
              <input
                className="form-control"
                value={approvalForm.name}
                onChange={(e) => setApprovalForm({ ...approvalForm, name: e.target.value })}
              />
            </label>
            <label className="dashboard-filter-field">
              <span className="dashboard-filter-label">URL</span>
              <input
                className="form-control"
                value={approvalForm.url}
                onChange={(e) => setApprovalForm({ ...approvalForm, url: e.target.value })}
              />
            </label>
            <label className="dashboard-filter-field">
              <span className="dashboard-filter-label">Parser config (JSON)</span>
              <textarea
                className="form-control cv-textarea"
                rows={12}
                value={parserJson}
                onChange={(e) => setParserJson(e.target.value)}
              />
            </label>
          </div>
        </Modal>
      )}
    </>
  );
}
