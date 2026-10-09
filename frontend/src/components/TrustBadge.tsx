import type { OpportunityTrust } from '../api/client';
import { Badge, type BadgeVariant } from './ui/Primitives';

function trustBadgeVariant(state: OpportunityTrust['state']): BadgeVariant {
  switch (state) {
    case 'verified':
      return 'success';
    case 'aggregator_only':
      return 'navy';
    case 'conflict':
      return 'warning';
    default:
      return 'muted';
  }
}

function formatCheckedAt(checkedAt?: string): string {
  if (!checkedAt) return 'Not checked yet';
  const date = new Date(checkedAt);
  if (Number.isNaN(date.getTime())) return 'Check date unavailable';
  return `Last checked ${date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })}`;
}

export function TrustBadge({ trust }: { trust: OpportunityTrust }) {
  const checkedLine = formatCheckedAt(trust.checked_at);

  return (
    <span className="hint-popover-wrap trust-badge-wrap">
      <button
        type="button"
        className="trust-badge-trigger"
        aria-label={`Trust: ${trust.label}`}
      >
        <Badge variant={trustBadgeVariant(trust.state)}>{trust.label}</Badge>
      </button>
      <div className="hint-popover trust-hint-popover" role="tooltip">
        <p className="hint-popover-title">{trust.label}</p>
        <p className="trust-hint-body">{trust.hint}</p>
        <p className="trust-hint-meta muted-text">{checkedLine}</p>
        {trust.primary_url && (
          <a
            href={trust.primary_url}
            target="_blank"
            rel="noopener noreferrer"
            className="trust-hint-link"
            onClick={(e) => e.stopPropagation()}
          >
            View official page
          </a>
        )}
      </div>
    </span>
  );
}
