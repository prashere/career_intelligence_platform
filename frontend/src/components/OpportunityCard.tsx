import type { Opportunity } from '../api/client';
import { Badge } from './ui/Primitives';

interface Props {
  opportunity: Opportunity;
  onClick?: () => void;
}

function fitLabel(level?: string) {
  if (level === 'strong') return 'Strong fit';
  if (level === 'moderate') return 'Moderate fit';
  return 'Exploring';
}

function fitBadgeVariant(level?: string): 'success' | 'gold' | 'muted' {
  if (level === 'strong') return 'success';
  if (level === 'moderate') return 'gold';
  return 'muted';
}

export default function OpportunityCard({ opportunity, onClick }: Props) {
  const urgencyClass =
    opportunity.urgency_label?.includes('day') ? 'urgent' :
    opportunity.urgency_label?.includes('week') ? 'soon' : 'later';

  return (
    <article
      className="opp-card"
      onClick={onClick}
      onKeyDown={(e) => e.key === 'Enter' && onClick?.()}
      role="button"
      tabIndex={0}
    >
      <div className="opp-card-main">
        <div className="opp-card-badges">
          <Badge variant={fitBadgeVariant(opportunity.fit_level)}>{fitLabel(opportunity.fit_level)}</Badge>
          {opportunity.opportunity_type && (
            <Badge variant="navy">{opportunity.opportunity_type}</Badge>
          )}
        </div>
        <h4 className="opp-title">{opportunity.title}</h4>
        {(opportunity.institution || opportunity.program) && (
          <p className="opp-meta">
            {[opportunity.institution, opportunity.program].filter(Boolean).join(' · ')}
          </p>
        )}
        <p className="opp-summary">
          {opportunity.fit_explanation || opportunity.summary || 'No description available'}
        </p>
      </div>
      <div className="opp-card-aside">
        {opportunity.urgency_label && (
          <span className={`opp-deadline ${urgencyClass}`}>{opportunity.urgency_label}</span>
        )}
        {opportunity.fit_percent != null && (
          <span className="opp-score">{opportunity.fit_percent}% match</span>
        )}
      </div>
    </article>
  );
}

export function CardList({
  title,
  items,
  onSelect,
}: {
  title: string;
  items: Opportunity[];
  onSelect: (id: string) => void;
}) {
  if (!items.length) return null;
  return (
    <section className="feed-section">
      <h3 className="section-title">{title} <span className="section-count">{items.length}</span></h3>
      <div className="card-list">
        {items.map((opp) => (
          <OpportunityCard key={opp.id} opportunity={opp} onClick={() => onSelect(opp.id)} />
        ))}
      </div>
    </section>
  );
}
