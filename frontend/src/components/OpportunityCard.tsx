import { useState } from 'react';
import type { Opportunity } from '../api/client';
import {
  DISMISS_REASONS,
  type OpportunityStatus,
} from '../hooks/useOpportunityStatusMutation';
import { downloadCalendarFile, openGoogleCalendar } from '../hooks/useCalendarExport';
import CardCalendarActions from './CardCalendarActions';
import {
  DeadlineChip,
  deadlineChipClass,
  deadlineChipLabel,
  hasCalendarDeadline,
} from './DeadlineChip';
import { TrustBadge } from './TrustBadge';
import { Badge, Button } from './ui/Primitives';
import { Modal } from './ui/Modal';

interface Props {
  opportunity: Opportunity;
  onClick?: () => void;
  showRank?: boolean;
  onStatusChange?: (
    status: OpportunityStatus | 'new',
    dismissReason?: string,
  ) => void;
  statusPending?: boolean;
  allowRestore?: boolean;
  variant?: 'default' | 'priority';
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

function statusBadge(status?: string) {
  switch (status) {
    case 'saved':
      return { label: 'Saved', variant: 'gold' as const };
    case 'applied':
    case 'in_progress':
      return { label: 'Applied', variant: 'success' as const };
    case 'dismissed':
    case 'archived':
      return { label: 'Dismissed', variant: 'muted' as const };
    default:
      return null;
  }
}

function statusCardClass(status?: string) {
  switch (status) {
    case 'saved':
      return 'opp-card-status-saved';
    case 'applied':
    case 'in_progress':
      return 'opp-card-status-applied';
    case 'dismissed':
    case 'archived':
      return 'opp-card-status-dismissed';
    default:
      return '';
  }
}

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

export default function OpportunityCard({
  opportunity,
  onClick,
  showRank = false,
  onStatusChange,
  statusPending = false,
  allowRestore = false,
  variant = 'default',
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [dismissOpen, setDismissOpen] = useState(false);
  const [calendarPending, setCalendarPending] = useState(false);
  const breakdown = opportunity.score_breakdown;
  const reasons = breakdown?.reasons ?? breakdown?.eligibility_reasons ?? [];
  const hidePercent = breakdown?.hide_match_percent ?? reasons.length === 0;

  const positives = reasons.filter((r) => r.direction === 'positive');
  const negatives = reasons.filter((r) => r.direction === 'negative');
  const context = reasons.filter((r) => r.direction === 'neutral');
  const keywordOnly = reasons.some((r) => r.code === 'semantic_keyword_only');

  const deadlineLabel = deadlineChipLabel(opportunity);
  const deadlineClass = deadlineChipClass(opportunity.deadline_bucket);
  const canExportCalendar = hasCalendarDeadline(opportunity);

  const showFitPercent = !hidePercent && opportunity.fit_percent != null;
  const fitLine = showFitPercent
    ? `${fitLabel(opportunity.fit_level)} · ${opportunity.fit_percent}%`
    : fitLabel(opportunity.fit_level);

  const primaryReason =
    opportunity.fit_explanation ||
    (hidePercent
      ? 'This listing has too little detail to match against your profile'
      : opportunity.summary);

  const statusInfo = statusBadge(opportunity.status);
  const isDismissed = opportunity.status === 'dismissed' || opportunity.status === 'archived';
  const isSaved = opportunity.status === 'saved';
  const isApplied = opportunity.status === 'applied' || opportunity.status === 'in_progress';

  async function handleDownloadCalendar() {
    if (!canExportCalendar) return;
    setCalendarPending(true);
    try {
      await downloadCalendarFile(opportunity.id, opportunity.title);
    } finally {
      setCalendarPending(false);
    }
  }

  async function handleGoogleCalendar() {
    if (!canExportCalendar) return;
    setCalendarPending(true);
    try {
      await openGoogleCalendar(opportunity.id);
    } finally {
      setCalendarPending(false);
    }
  }

  const showStatusToolbar =
    (onStatusChange && !allowRestore) || (allowRestore && isDismissed && onStatusChange);
  const showToolbar = showStatusToolbar || canExportCalendar;

  return (
    <>
      <article
        className={`opp-card opp-card-v2 ${variant === 'priority' ? 'opp-card-priority' : ''} ${statusCardClass(opportunity.status)}`}
        onClick={onClick}
        onKeyDown={(e) => e.key === 'Enter' && onClick?.()}
        role={onClick ? 'button' : undefined}
        tabIndex={onClick ? 0 : undefined}
      >
        <div className="opp-card-body">
          <header className="opp-card-header">
            <div className="opp-card-header-main">
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
            </div>
            {deadlineLabel && (
              <div className="opp-card-header-aside">
                <DeadlineChip label={deadlineLabel} className={deadlineClass} />
              </div>
            )}
          </header>

          <p className="opp-fit-reason">{primaryReason}</p>

          <div className="opp-chip-row">
            <Badge variant={fitBadgeVariant(opportunity.fit_level)}>{fitLine}</Badge>
            {statusInfo && <Badge variant={statusInfo.variant}>{statusInfo.label}</Badge>}
            {opportunity.opportunity_type && (
              <Badge variant="navy">{opportunity.opportunity_type}</Badge>
            )}
            {opportunity.trust && <TrustBadge trust={opportunity.trust} />}
            {opportunity.tags?.slice(0, 3).map((tag) => (
              <span key={tag} className="opp-tag-chip">{tag}</span>
            ))}
          </div>

          {showToolbar && (
            <footer
              className={`opp-card-toolbar${showStatusToolbar && canExportCalendar ? ' opp-card-toolbar-split' : ''}`}
              onClick={(e) => e.stopPropagation()}
            >
              {showStatusToolbar && (
                <div className="opp-toolbar-start">
                  {allowRestore && isDismissed && onStatusChange ? (
                    <button
                      type="button"
                      className="opp-restore-btn"
                      disabled={statusPending}
                      onClick={() => onStatusChange('new')}
                    >
                      Restore to matches
                    </button>
                  ) : onStatusChange && !allowRestore ? (
                    <div className="opp-status-actions">
                      <button
                        type="button"
                        className={`opp-action-btn${isSaved ? ' active' : ''}`}
                        disabled={statusPending || isDismissed}
                        onClick={() => onStatusChange(isSaved ? 'new' : 'saved')}
                      >
                        {isSaved ? 'Unsave' : 'Save'}
                      </button>
                      <button
                        type="button"
                        className={`opp-action-btn${isApplied ? ' active' : ''}`}
                        disabled={statusPending || isDismissed}
                        onClick={() => onStatusChange(isApplied ? 'new' : 'applied')}
                      >
                        {isApplied ? 'Unapply' : 'Applied'}
                      </button>
                      <button
                        type="button"
                        className="opp-action-btn opp-action-dismiss"
                        disabled={statusPending || isDismissed}
                        onClick={() => setDismissOpen(true)}
                      >
                        Dismiss
                      </button>
                    </div>
                  ) : null}
                </div>
              )}

              {canExportCalendar && (
                <div className="opp-toolbar-end">
                  <CardCalendarActions
                    disabled={calendarPending || isDismissed}
                    onDownloadIcs={handleDownloadCalendar}
                    onGoogleCalendar={handleGoogleCalendar}
                  />
                </div>
              )}
            </footer>
          )}

          <div className="opp-card-links">
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
                  Matched on keywords. The semantic model is not configured, so wording
                  differences may be missed.
                </p>
              )}
            </div>
          )}
        </div>
      </article>

      {dismissOpen && onStatusChange && (
        <Modal
          title="Why are you dismissing this?"
          onClose={() => setDismissOpen(false)}
          actions={
            <Button variant="secondary" onClick={() => setDismissOpen(false)}>
              Cancel
            </Button>
          }
        >
          <p className="opp-dismiss-hint muted-text">
            Your reason helps us rank similar listings lower.
          </p>
          <div className="opp-dismiss-reasons">
            {DISMISS_REASONS.map(({ code, label }) => (
              <button
                key={code}
                type="button"
                className="opp-dismiss-reason-btn"
                onClick={() => {
                  onStatusChange('dismissed', code);
                  setDismissOpen(false);
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </Modal>
      )}
    </>
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
