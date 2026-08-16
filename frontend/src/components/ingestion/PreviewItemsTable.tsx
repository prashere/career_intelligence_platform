import { Fragment, useState } from 'react';
import type { PreviewItem, RelevanceSignal, RelevanceVerdict } from '../../api/auth';

export type { PreviewItem } from '../../api/auth';

export type PreviewFilter = 'all' | RelevanceVerdict;

interface PreviewItemsTableProps {
  items: PreviewItem[];
  filter?: PreviewFilter;
}

const VERDICT_BADGE: Record<RelevanceVerdict, string> = {
  admit: 'success',
  investigate: 'warning',
  reject: 'error',
};

const VERDICT_LABEL: Record<RelevanceVerdict, string> = {
  admit: 'Admit',
  investigate: 'Investigate',
  reject: 'Reject',
};

/** Runs recorded before the relevance gate only carry a pass/fail flag. */
function verdictOf(item: PreviewItem): RelevanceVerdict {
  if (item.verdict) return item.verdict;
  return item.prefilter_pass === false ? 'reject' : 'admit';
}

function reasonOf(item: PreviewItem): string {
  return item.reason || item.prefilter_reason || '';
}

function signalList(signals: Record<string, RelevanceSignal> | undefined): RelevanceSignal[] {
  if (!signals) return [];
  return Object.values(signals);
}

export function PreviewItemsTable({ items, filter = 'all' }: PreviewItemsTableProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const filtered = items.filter((item) => filter === 'all' || verdictOf(item) === filter);

  if (!filtered.length) {
    return <p className="muted-text">No discovered items to show.</p>;
  }

  return (
    <div className="lab-table-wrap">
      <table className="lab-table">
        <thead>
          <tr>
            <th>Verdict</th>
            <th>Score</th>
            <th>Title</th>
            <th>Why</th>
            <th>URL</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((item) => {
            const verdict = verdictOf(item);
            const isOpen = expanded === item.url;
            const signals = signalList(item.signals);

            return (
              <Fragment key={item.url}>
                <tr className={verdict === 'reject' ? 'lab-row-drop' : undefined}>
                  <td>
                    <span className={`badge badge-${VERDICT_BADGE[verdict]}`}>
                      {VERDICT_LABEL[verdict]}
                    </span>
                    {item.resolved && <span className="lab-drop-reason">after detail fetch</span>}
                  </td>
                  <td className="lab-cell-score">
                    {typeof item.score === 'number' ? item.score.toFixed(2) : 'n/a'}
                    {typeof item.sufficiency === 'number' && (
                      <span className="lab-subscore">info {item.sufficiency.toFixed(2)}</span>
                    )}
                  </td>
                  <td>
                    {item.title || 'n/a'}
                    {item.type_label && <span className="lab-subscore">{item.type_label}</span>}
                  </td>
                  <td className="lab-cell-why">
                    <span className="lab-drop-reason">{reasonOf(item) || 'n/a'}</span>
                    {item.evidence && item.evidence.length > 0 && (
                      <span className="lab-evidence">{item.evidence.slice(0, 3).join(', ')}</span>
                    )}
                    {item.resolve_error && (
                      <span className="form-error">{item.resolve_error}</span>
                    )}
                    {signals.length > 0 && (
                      <button
                        type="button"
                        className="lab-link-button"
                        onClick={() => setExpanded(isOpen ? null : item.url)}
                      >
                        {isOpen ? 'Hide signals' : 'Signals'}
                      </button>
                    )}
                  </td>
                  <td className="lab-cell-urls">
                    <a href={item.url} target="_blank" rel="noreferrer">
                      {item.url}
                    </a>
                  </td>
                </tr>
                {isOpen && (
                  <tr className="lab-row-detail">
                    <td colSpan={5}>
                      <div className="lab-signal-grid">
                        {signals.map((signal) => (
                          <div
                            key={signal.name}
                            className={`lab-signal${signal.matched ? ' matched' : ''}`}
                          >
                            <div className="lab-signal-head">
                              <strong>{signal.name.replace(/_/g, ' ')}</strong>
                              <span>{signal.matched ? signal.strength.toFixed(2) : 'no match'}</span>
                            </div>
                            {signal.evidence.length > 0 && (
                              <p className="lab-signal-evidence">{signal.evidence.join(', ')}</p>
                            )}
                            <p className="muted-text">
                              {signal.found_in ? `found in ${signal.found_in}` : ''}
                              {signal.note ? ` · ${signal.note}` : ''}
                            </p>
                          </div>
                        ))}
                      </div>
                      <dl className="lab-score-breakdown">
                        <div>
                          <dt>Corpus</dt>
                          <dd>{item.corpus_score?.toFixed(2) ?? 'n/a'}</dd>
                        </div>
                        <div>
                          <dt>Fit</dt>
                          <dd>{item.fit_score?.toFixed(2) ?? 'n/a'}</dd>
                        </div>
                        <div>
                          <dt>Final</dt>
                          <dd>{item.score?.toFixed(2) ?? 'n/a'}</dd>
                        </div>
                        <div>
                          <dt>Scored at</dt>
                          <dd>{item.stage === 'post_extract' ? 'full text' : 'discover'}</dd>
                        </div>
                      </dl>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
