import type { Opportunity } from '../api/client'

interface Props {
  opportunity: Opportunity
  onClick?: () => void
}

export default function OpportunityCard({ opportunity, onClick }: Props) {
  const fitClass = opportunity.fit_level || 'weak'
  const urgencyClass =
    opportunity.urgency_label?.includes('day') ? '' :
    opportunity.urgency_label?.includes('week') ? 'soon' : 'later'

  return (
    <div className="opp-card" onClick={onClick} role="button" tabIndex={0}>
      <div className="opp-card-left">
        <span className={`fit-dot ${fitClass}`} />
        <div>
          <div className="opp-title">{opportunity.title}</div>
          <div className="opp-subtitle">
            {opportunity.fit_explanation || opportunity.summary?.slice(0, 100) || 'No description'}
          </div>
        </div>
      </div>
      {opportunity.urgency_label && (
        <span className={`opp-urgency ${urgencyClass}`}>{opportunity.urgency_label}</span>
      )}
    </div>
  )
}

function CardList({ title, items, onSelect }: { title: string; items: Opportunity[]; onSelect: (id: string) => void }) {
  if (!items.length) return null
  return (
    <>
      <h3 className="section-title">{title} ({items.length})</h3>
      <div className="card-list">
        {items.map((opp) => (
          <OpportunityCard key={opp.id} opportunity={opp} onClick={() => onSelect(opp.id)} />
        ))}
      </div>
    </>
  )
}

export { CardList }
