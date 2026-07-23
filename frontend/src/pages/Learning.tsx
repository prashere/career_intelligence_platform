import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export default function Learning() {
  const [title, setTitle] = useState('')
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['learning'], queryFn: api.learning })

  const createMutation = useMutation({
    mutationFn: api.createLearning,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['learning'] })
      setTitle('')
    },
  })

  if (isLoading) return <div className="empty-state">Loading...</div>

  return (
    <>
      <div className="page-header"><h2>Upskilling</h2></div>

      <div className="search-row" style={{ maxWidth: 500 }}>
        <input placeholder="Add course or certification..." value={title} onChange={(e) => setTitle(e.target.value)} />
        <button className="btn" onClick={() => title && createMutation.mutate({ title, item_type: 'course' })}>Add</button>
      </div>

      <div className="dashboard-section" style={{ marginTop: '1rem' }}>
        {data?.length ? data.map((item) => (
          <div key={item.id} style={{ marginBottom: '1rem' }}>
            <div style={{ fontWeight: 500 }}>{item.title}</div>
            <div style={{ fontSize: '0.8125rem', color: '#9aa0a6' }}>{item.item_type} · {item.status}</div>
            <div className="progress-bar">
              <div className="progress-bar-fill" style={{ width: `${item.progress_percent}%` }} />
            </div>
            {item.outcome_notes && <div style={{ fontSize: '0.8125rem', marginTop: '0.25rem' }}>{item.outcome_notes}</div>}
          </div>
        )) : <p style={{ color: '#9aa0a6' }}>No learning items yet</p>}
      </div>
    </>
  )
}
