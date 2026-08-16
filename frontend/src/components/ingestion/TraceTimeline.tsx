import { useMemo, useState } from 'react';
import type { TraceEvent } from '../../api/auth';

const LEVEL_CLASS: Record<string, string> = {
  debug: 'trace-level-debug',
  info: 'trace-level-info',
  warn: 'trace-level-warn',
  error: 'trace-level-error',
};

interface TraceTimelineProps {
  events: TraceEvent[];
  onSelectRun?: (runId: string) => void;
  showFilters?: boolean;
}

export function TraceTimeline({ events, showFilters = false }: TraceTimelineProps) {
  const [levelFilter, setLevelFilter] = useState<string>('all');
  const [stageFilter, setStageFilter] = useState<string>('all');
  const [expandPayloads, setExpandPayloads] = useState(false);

  const stages = useMemo(
    () => [...new Set(events.map((ev) => ev.stage))].sort(),
    [events],
  );

  const filtered = useMemo(() => {
    return events.filter((ev) => {
      if (levelFilter !== 'all' && ev.level !== levelFilter) return false;
      if (stageFilter !== 'all' && ev.stage !== stageFilter) return false;
      return true;
    });
  }, [events, levelFilter, stageFilter]);

  if (!events.length) {
    return <p className="muted-text">No trace events recorded for this run.</p>;
  }

  return (
    <div className="trace-panel">
      {showFilters && (
        <div className="trace-toolbar">
          <label className="trace-filter">
            <span>Level</span>
            <select value={levelFilter} onChange={(e) => setLevelFilter(e.target.value)}>
              <option value="all">All</option>
              <option value="debug">Debug</option>
              <option value="info">Info</option>
              <option value="warn">Warn</option>
              <option value="error">Error</option>
            </select>
          </label>
          <label className="trace-filter">
            <span>Stage</span>
            <select value={stageFilter} onChange={(e) => setStageFilter(e.target.value)}>
              <option value="all">All</option>
              {stages.map((stage) => (
                <option key={stage} value={stage}>
                  {stage}
                </option>
              ))}
            </select>
          </label>
          <label className="trace-filter trace-filter-check">
            <input
              type="checkbox"
              checked={expandPayloads}
              onChange={(e) => setExpandPayloads(e.target.checked)}
            />
            Expand payloads
          </label>
          <span className="muted-text trace-count">
            {filtered.length} / {events.length} events
          </span>
        </div>
      )}

      {filtered.length === 0 ? (
        <p className="muted-text">No events match the current filters.</p>
      ) : (
        <ol className="trace-timeline">
          {filtered.map((ev) => (
            <li key={ev.id} className={`trace-event trace-event-${ev.level}`}>
              <div className="trace-event-head">
                <span className="trace-seq">#{ev.seq}</span>
                <span className={`trace-level ${LEVEL_CLASS[ev.level] ?? ''}`}>{ev.level}</span>
                <span className="trace-stage">{ev.stage}</span>
                <span className="trace-event-name">{ev.event}</span>
                <span className="trace-time">{new Date(ev.created_at).toLocaleTimeString()}</span>
                {ev.duration_ms != null && (
                  <span className="trace-duration">{ev.duration_ms}ms</span>
                )}
              </div>
              <p className="trace-message">{ev.message}</p>
              {ev.payload && Object.keys(ev.payload).length > 0 && (
                <details className="trace-payload-details" open={expandPayloads}>
                  <summary>Payload</summary>
                  <pre className="trace-payload">{JSON.stringify(ev.payload, null, 2)}</pre>
                </details>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

interface RunDetailPanelProps {
  sourceName: string | null;
  run: {
    id: string;
    status: string;
    discovered: number;
    prefilter_drop: number;
    created: number;
    updated: number;
    rejected: number;
    errors: number;
    error_message: string | null;
    started_at: string;
    finished_at: string | null;
    meta: Record<string, unknown>;
  };
  traceEvents: TraceEvent[];
  rejectedItems: Array<{
    id: string;
    stage: string;
    reason: string;
    url: string | null;
    title: string | null;
  }>;
}

export function RunDetailPanel({ sourceName, run, traceEvents, rejectedItems }: RunDetailPanelProps) {
  const mode = (run.meta?.mode as string) ?? 'production';
  const dryRun = Boolean(run.meta?.dry_run);

  return (
    <div className="run-detail-panel">
      <header className="run-detail-head">
        <div>
          <h3>{sourceName ?? 'Unknown source'}</h3>
          <p className="muted-text">
            Run <code>{run.id.slice(0, 8)}</code> · {mode}
            {dryRun && ' · dry run'}
          </p>
        </div>
        <span className={`badge badge-${run.status === 'completed' ? 'success' : run.status === 'failed' ? 'error' : 'warning'}`}>
          {run.status}
        </span>
      </header>

      <dl className="run-detail-stats">
        <div><dt>Discovered</dt><dd>{run.discovered}</dd></div>
        <div><dt>Prefilter drop</dt><dd>{run.prefilter_drop}</dd></div>
        <div><dt>Created</dt><dd>{run.created}</dd></div>
        <div><dt>Updated</dt><dd>{run.updated}</dd></div>
        <div><dt>Rejected</dt><dd>{run.rejected}</dd></div>
        <div><dt>Errors</dt><dd>{run.errors}</dd></div>
      </dl>

      {run.error_message && <p className="form-error">{run.error_message}</p>}

      {(run.meta?.winning_strategy as string) && (
        <p className="muted-text">
          Winning strategy: <strong>{String(run.meta.winning_strategy)}</strong>
        </p>
      )}

      <h4 className="panel-subtitle">Trace timeline</h4>
      <TraceTimeline events={traceEvents} showFilters />

      {rejectedItems.length > 0 && (
        <>
          <h4 className="panel-subtitle">Rejections ({rejectedItems.length})</h4>
          <ul className="run-rejected-list">
            {rejectedItems.slice(0, 30).map((item) => (
              <li key={item.id}>
                <span className={`badge badge-muted`}>{item.stage}</span>
                <strong>{item.reason}</strong>
                {item.title && <span className="muted-text">, {item.title}</span>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
