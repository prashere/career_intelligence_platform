import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { CardList } from '../components/OpportunityCard'

export default function Feed() {
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  const { data, isLoading, error } = useQuery({
    queryKey: ['feed', query],
    queryFn: () => api.feed(query || undefined),
  })

  const handleSearch = () => setQuery(search)

  if (isLoading) return <div className="empty-state">Loading opportunities...</div>
  if (error) return <div className="empty-state">Failed to load feed. Is the API running?</div>

  const total = (data?.scholarships.length || 0) + (data?.fellowships.length || 0) + (data?.other.length || 0)

  return (
    <>
      <div className="page-header">
        <h2>Opportunities</h2>
      </div>

      <div className="search-row">
        <input
          placeholder="Search opportunities..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
        />
        <button className="btn" onClick={handleSearch}>Filter</button>
      </div>

      {data && (
        <div className="summary-bar">
          {data.summary.new_since} new since Tuesday · {data.summary.deadlines_this_week} deadlines this week · {data.summary.prep_milestones_due} prep milestone{data.summary.prep_milestones_due !== 1 ? 's' : ''} due
        </div>
      )}

      {total === 0 ? (
        <div className="empty-state">
          <p>No opportunities yet.</p>
          <p style={{ marginTop: '0.5rem', fontSize: '0.875rem' }}>
            Run the seed script or trigger ingestion to populate the feed.
          </p>
        </div>
      ) : (
        <>
          <CardList title="Scholarships" items={data?.scholarships || []} onSelect={(id) => navigate(`/opportunities/${id}`)} />
          <CardList title="Fellowships" items={data?.fellowships || []} onSelect={(id) => navigate(`/opportunities/${id}`)} />
          <CardList title="Other" items={data?.other || []} onSelect={(id) => navigate(`/opportunities/${id}`)} />
        </>
      )}
    </>
  )
}
