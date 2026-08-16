import type { StrategyProbe } from '../../api/auth';

interface StrategyProbesTableProps {
  probes: StrategyProbe[];
  winningStrategy?: string | null;
}

export function StrategyProbesTable({ probes, winningStrategy }: StrategyProbesTableProps) {
  if (!probes.length) {
    return <p className="muted-text">No strategy probe data for this run.</p>;
  }

  return (
    <div className="lab-table-wrap">
      <table className="lab-table">
        <thead>
          <tr>
            <th>Strategy</th>
            <th>Status</th>
            <th>Raw</th>
            <th>Filtered</th>
            <th>Browser</th>
            <th>Detail</th>
            <th>Sample URLs</th>
          </tr>
        </thead>
        <tbody>
          {probes.map((probe, idx) => {
            const isWinner =
              winningStrategy != null &&
              (probe.kind === winningStrategy ||
                winningStrategy === `${probe.kind}+browser` ||
                winningStrategy.startsWith(probe.kind));
            let status = probe.ok ? 'pass' : probe.skipped ? 'skip' : 'fail';
            let statusLabel = probe.ok ? 'Pass' : probe.skipped ? 'Skip' : 'Fail';

            return (
              <tr key={`${probe.kind}-${idx}`} className={isWinner ? 'lab-row-winner' : undefined}>
                <td>
                  <code>{probe.kind}</code>
                  {isWinner && <span className="badge badge-success lab-winner-badge">Winner</span>}
                </td>
                <td>
                  <span className={`badge badge-${status === 'pass' ? 'success' : status === 'skip' ? 'muted' : 'error'}`}>
                    {statusLabel}
                  </span>
                </td>
                <td>{probe.item_count ?? 0}</td>
                <td>{probe.filtered_count ?? 0}</td>
                <td>{probe.requires_browser ? 'Yes' : 'No'}</td>
                <td className="lab-cell-detail">
                  {probe.skip_reason && <span className="muted-text">{probe.skip_reason}</span>}
                  {probe.error && !probe.skipped && <span className="form-error-inline">{probe.error}</span>}
                  {!probe.skip_reason && !probe.error && <span className="muted-text">n/a</span>}
                </td>
                <td className="lab-cell-urls">
                  {(probe.sample_urls ?? []).slice(0, 3).map((url) => (
                    <a key={url} href={url} target="_blank" rel="noreferrer">
                      {url.length > 56 ? `${url.slice(0, 56)}…` : url}
                    </a>
                  ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
