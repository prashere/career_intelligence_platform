import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export default function Discover() {
  const queryClient = useQueryClient()
  const [personName, setPersonName] = useState('')
  const [communityName, setCommunityName] = useState('')

  const { data: people } = useQuery({ queryKey: ['people'], queryFn: api.people })
  const { data: communities } = useQuery({ queryKey: ['communities'], queryFn: api.communities })
  const { data: experiences } = useQuery({ queryKey: ['experiences'], queryFn: api.experiences })

  const addPerson = useMutation({
    mutationFn: api.createPerson,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['people'] })
      setPersonName('')
    },
  })

  const addCommunity = useMutation({
    mutationFn: api.createCommunity,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['communities'] })
      setCommunityName('')
    },
  })

  return (
    <>
      <div className="page-header"><h2>People & Communities</h2></div>

      <div className="dashboard-grid">
        <div className="dashboard-section">
          <h3>People</h3>
          <div className="search-row">
            <input placeholder="Add researcher or mentor..." value={personName} onChange={(e) => setPersonName(e.target.value)} />
            <button className="btn" onClick={() => personName && addPerson.mutate({ name: personName, role: 'researcher' })}>Add</button>
          </div>
          {people?.map((p) => (
            <div key={p.id} className="notification-item">
              <strong>{p.name}</strong>
              <div style={{ color: '#9aa0a6', fontSize: '0.8125rem' }}>
                {p.role}{p.affiliation ? ` · ${p.affiliation}` : ''}
              </div>
              {p.research_areas?.length > 0 && (
                <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>{p.research_areas.join(', ')}</div>
              )}
            </div>
          ))}
        </div>

        <div className="dashboard-section">
          <h3>Communities</h3>
          <div className="search-row">
            <input placeholder="Add community..." value={communityName} onChange={(e) => setCommunityName(e.target.value)} />
            <button className="btn" onClick={() => communityName && addCommunity.mutate({ name: communityName, community_type: 'forum' })}>Add</button>
          </div>
          {communities?.map((c) => (
            <div key={c.id} className="notification-item">
              <strong>{c.name}</strong>
              <div style={{ color: '#9aa0a6', fontSize: '0.8125rem' }}>{c.community_type}</div>
              {c.description && <div style={{ fontSize: '0.8125rem' }}>{c.description}</div>}
            </div>
          ))}
        </div>

        <div className="dashboard-section">
          <h3>Experience</h3>
          {experiences?.map((e) => (
            <div key={e.id} className="notification-item">
              <strong>{e.title}</strong>
              <div style={{ color: '#9aa0a6', fontSize: '0.8125rem' }}>{e.experience_type} · {e.status}</div>
              {e.description && <div style={{ fontSize: '0.8125rem' }}>{e.description}</div>}
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
