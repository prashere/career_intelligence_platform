import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export default function Detail() {
  const { id } = useParams<{ id: string }>()
  const [message, setMessage] = useState('')
  const [chatHistory, setChatHistory] = useState<{ role: string; content: string }[]>([])
  const [useAgent, setUseAgent] = useState(true)
  const queryClient = useQueryClient()

  const { data: opp, isLoading } = useQuery({
    queryKey: ['opportunity', id],
    queryFn: () => api.opportunity(id!),
    enabled: !!id,
  })

  const statusMutation = useMutation({
    mutationFn: (status: string) => api.updateStatus(id!, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['opportunity', id] }),
  })

  const chatMutation = useMutation({
    mutationFn: (msg: string) => (useAgent ? api.agentChat(id!, msg) : api.chat(id!, msg)),
    onSuccess: (data) => {
      setChatHistory((h) => [
        ...h,
        { role: 'assistant', content: data.reply },
      ])
    },
  })

  const handleSend = () => {
    if (!message.trim()) return
    setChatHistory((h) => [...h, { role: 'user', content: message }])
    chatMutation.mutate(message)
    setMessage('')
  }

  if (isLoading || !opp) return <div className="empty-state">Loading...</div>

  return (
    <>
      <Link to="/" style={{ fontSize: '0.875rem' }}>← Back to feed</Link>

      <div className="detail-grid" style={{ marginTop: '1rem' }}>
        <div className="detail-panel">
          <h3>{opp.title}</h3>
          {opp.institution && <p style={{ color: '#9aa0a6', fontSize: '0.875rem' }}>{opp.institution}{opp.program ? ` · ${opp.program}` : ''}</p>}
          {opp.urgency_label && <p style={{ color: '#f87171', fontSize: '0.875rem', marginTop: '0.5rem' }}>Deadline: {opp.urgency_label}</p>}

          {opp.fit_explanation && (
            <div className="ai-box">
              <strong>AI Recommendation:</strong> Ranked #{opp.fit_level === 'strong' ? '1' : '—'} in {opp.opportunity_type}s: {opp.fit_explanation}
            </div>
          )}

          <h4 style={{ marginTop: '1rem', fontSize: '0.875rem', color: '#9aa0a6' }}>Requirements</h4>
          <ul className="requirements-list">
            {(opp.requirements.length ? opp.requirements : ['No requirements listed']).map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>

          <div className="actions-row">
            <button className="btn btn-secondary" onClick={() => statusMutation.mutate('saved')}>Save</button>
            <button className="btn" onClick={() => statusMutation.mutate('in_progress')}>Start applying</button>
            <a className="btn btn-secondary" href={api.calendarUrl(opp.id)} download>Add to calendar</a>
            <a className="btn btn-secondary" href={opp.url} target="_blank" rel="noreferrer">Official page</a>
          </div>
        </div>

        <div className="detail-panel chat-panel">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <h3 style={{ fontSize: '0.9375rem' }}>Ask about this opportunity</h3>
            <label style={{ fontSize: '0.75rem', color: '#9aa0a6' }}>
              <input type="checkbox" checked={useAgent} onChange={(e) => setUseAgent(e.target.checked)} /> Agent mode
            </label>
          </div>

          <div className="chat-messages">
            {chatHistory.length === 0 && (
              <div className="chat-msg assistant" style={{ color: '#9aa0a6' }}>
                Try: "How competitive is this one usually?"
              </div>
            )}
            {chatHistory.map((msg, i) => (
              <div key={i} className={`chat-msg ${msg.role}`}>{msg.content}</div>
            ))}
            {chatMutation.isPending && <div className="chat-msg assistant">Thinking...</div>}
          </div>

          <div className="chat-input-row">
            <input
              placeholder="Ask a follow-up..."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            />
            <button className="btn" onClick={handleSend} disabled={chatMutation.isPending}>Send</button>
          </div>
        </div>
      </div>
    </>
  )
}
