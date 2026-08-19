import { useState } from 'react';
import type { Opportunity } from '../api/client';
import { Badge } from './ui/Primitives';

interface Props {
  opportunity: Opportunity;
  onClick?: () => void;
  showRank?: boolean;
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

function formatComponentLabel(key: string) {
  return key.charAt(0).toUpperCase() + key.slice(1);
}

const COMPONENT_HELP: Record<string, string> = {
  semantic: 'How closely the listing text matches your interests and skills',
  eligibility: 'Whether you meet the stated degree, funding and region rules',
  urgency: 'How soon the deadline falls',
  affinity: 'Similarity to opportunities you saved or dismissed',
};

const REASON_ICON: Record<string, string> = {
  positive: '+',
  negative: '−',
  neutral: '·',
};

function renderReasonGroup(
  heading: string,
  items: { code: string; label: string; direction: string }[],
) {
  if (!items.length) return null;
  return (
    <div className="opp-reason-group">
      <p className="opp-reason-group-title">{heading}</p>
      <ul className="opp-reason-list">
        {items.map((r, i) => (
          <li key={`${r.code}-${i}`} className={`opp-reason-item opp-reason-${r.direction}`}>
            <span className="opp-reason-icon" aria-hidden="true">
              {REASON_ICON[r.direction] ?? '·'}
            </span>
            <span className="opp-reason-label">{r.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function OpportunityCard({ opportunity, onClick, showRank = false }: Props) {
  const [expanded, setExpanded] = useState(false);
  const breakdown = opportunity.score_breakdown;
  const reasons = breakdown?.reasons ?? breakdown?.eligibility_reasons ?? [];
  const hidePercent = breakdown?.hide_match_percent ?? reasons.length === 0;

  const positives = reasons.filter((r) => r.direction === 'positive');
  const negatives = reasons.filter((r) => r.direction === 'negative');
  const context = reasons.filter((r) => r.direction === 'neutral');
  const keywordOnly = reasons.some((r) => r.code === 'semantic_keyword_only');

  const urgencyClass =
    opportunity.urgency_label?.includes('day') ? 'urgent' :
    opportunity.urgency_label?.includes('week') ? 'soon' : 'later';

  const fitLine = hidePercent
    ? fitLabel(opportunity.fit_level)
    : `${fitLabel(opportunity.fit_level)} · ${opportunity.fit_percent}%`;

  const primaryReason =
    opportunity.fit_explanation ||
    (hidePercent ? 'This listing has too little detail to match against your profile' : opportunity.summary);

  return (
    <article
      className="opp-card opp-card-v2"
      onClick={onClick}
      onKeyDown={(e) => e.key === 'Enter' && onClick?.()}
      role="button"
      tabIndex={0}
    >
      <div className="opp-card-main">
        <div className="opp-card-head-row">
          {showRank && opportunity.rank_position != null && opportunity.rank_position <= 10 && (
            <span className="opp-rank-badge">#{opportunity.rank_position}</span>
          )}
          <h4 className="opp-title">{opportunity.title}</h4>
        </div>

        {(opportunity.institution || opportunity.program) && (
          <p className="opp-meta">
            {[opportunity.institution, opportunity.program].filter(Boolean).join(' · ')}
          </p>
        )}

        <p className="opp-fit-reason">{primaryReason}</p>

        <div className="opp-chip-row">
          <Badge variant={fitBadgeVariant(opportunity.fit_level)}>{fitLine}</Badge>
          {opportunity.opportunity_type && (
            <Badge variant="navy">{opportunity.opportunity_type}</Badge>
          )}
          {opportunity.verification_status === 'primary_confirmed' && (
            <Badge variant="success">Verified</Badge>
          )}
          {opportunity.tags?.slice(0, 2).map((tag) => (
            <span key={tag} className="opp-tag-chip">{tag}</span>
          ))}
        </div>

        <div className="opp-why-toggle-wrap">
          <button
            type="button"
            className="opp-why-toggle"
            onClick={(e) => {
              e.stopPropagation();
              setExpanded((v) => !v);
            }}
            aria-expanded={expanded}
          >
            {expanded ? 'Hide match details' : 'Why this match'}
          </button>
        </div>

        {expanded && (
          <div className="opp-why-panel" onClick={(e) => e.stopPropagation()}>
            {renderReasonGroup('Why it fits you', positives)}
            {renderReasonGroup('What holds it back', negatives)}
            {renderReasonGroup('About this listing', context)}

            {reasons.length === 0 && (
              <p className="opp-reason-empty">
                This listing has too little text to compare against your profile.
              </p>
            )}

            {breakdown && (
              <div className="opp-component-grid">
                {(['semantic', 'eligibility', 'urgency', 'affinity'] as const).map((key) => {
                  const val = breakdown[key];
                  if (val == null) return null;
                  const available = breakdown.components_available?.includes(key);
                  return (
                    <div
                      key={key}
                      className={`opp-component-cell${available ? '' : ' opp-component-muted'}`}
                      title={COMPONENT_HELP[key]}
                    >
                      <span className="opp-component-name">{formatComponentLabel(key)}</span>
                      <span className="opp-component-value">
                        {available ? `${Math.round(val * 100)}%` : 'n/a'}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}

            {keywordOnly && (
              <p className="opp-degraded-note">
                Matched on keywords — the semantic model is not configured, so wording
                differences may be missed.
              </p>
            )}
          </div>
        )}
      </div>

      <div className="opp-card-aside">
        {opportunity.urgency_label && (
          <span className={`opp-deadline ${urgencyClass}`}>{opportunity.urgency_label}</span>
        )}
        {!hidePercent && opportunity.fit_percent != null && (
          <span className="opp-score-pill">{opportunity.fit_percent}%</span>
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
