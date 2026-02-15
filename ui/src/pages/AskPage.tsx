import { ExternalLink, FileText, FolderOpen, Send, Share2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  chat, fetchConversation,
  type ChatResponse, type Citation,
  type ConversationTurn,
  type Evidence
} from '../api'
import GraphViewer from '../components/GraphViewer'
import ReasonBadges from '../components/ReasonBadges'

interface Message {
  role: 'user' | 'assistant'
  text: string
  response?: ChatResponse
}

/** Parse answer text and render [filename] references as highlighted badges. */
function AnswerText({ text }: { text: string }) {
  // Split on [some text] patterns — but not URLs like [http...]
  const parts = text.split(/(\[[^\]\[]{1,200}\])/g)
  return (
    <span>
      {parts.map((part, i) => {
        const m = part.match(/^\[(.+)\]$/)
        if (m && !m[1].startsWith('http')) {
          return (
            <span
              key={i}
              className="inline-flex items-center gap-1 mx-0.5 px-2 py-0.5 rounded-full
                         bg-accent/15 text-accent text-xs font-medium border border-accent/25
                         whitespace-nowrap"
            >
              <FileText size={10} className="shrink-0" />
              {m[1]}
            </span>
          )
        }
        return <span key={i}>{part}</span>
      })}
    </span>
  )
}

export default function AskPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const [input, setInput] = useState(params.get('q') || '')
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [graphSeed, setGraphSeed] = useState<string | undefined>()
  const [showGraph, setShowGraph] = useState(false)
  const [conversationId, setConversationId] = useState<string | undefined>()
  const [loadedConv, setLoadedConv] = useState<string | null>(null)

  // Load existing conversation from URL param (react to changes)
  useEffect(() => {
    const conv = params.get('conv')
    if (conv && conv !== loadedConv) {
      setLoadedConv(conv)
      setConversationId(conv)
      fetchConversation(conv)
        .then((detail) => {
          const restored: Message[] = []
          detail.turns.forEach((t: ConversationTurn) => {
            if (t.user_text) restored.push({ role: 'user', text: t.user_text })
            if (t.assistant_text) restored.push({ role: 'assistant', text: t.assistant_text })
          })
          setMessages(restored)
        })
        .catch(() => { })
    } else if (!conv && loadedConv) {
      // URL cleared (new chat clicked) — reset state
      setLoadedConv(null)
      setMessages([])
      setConversationId(undefined)
      setShowGraph(false)
      setGraphSeed(undefined)
      setInput('')
    }
  }, [params]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-ask if query param is passed (and not loading a conversation)
  useEffect(() => {
    const q = params.get('q')
    const conv = params.get('conv')
    if (q && !conv && messages.length === 0) {
      setInput(q)
      handleSend(q)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSend = useCallback(async (overrideQuery?: string) => {
    const q = overrideQuery || input
    if (!q.trim() || loading) return
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', text: q }])
    setLoading(true)
    try {
      const resp = await chat(q, 3, conversationId)
      setMessages((prev) => [...prev, { role: 'assistant', text: resp.answer, response: resp }])
      // Track conversation thread
      if (resp.conversation_id) setConversationId(resp.conversation_id)
      // Seed graph from first citation
      if (resp.citations.length > 0) {
        setGraphSeed(`mem:${resp.citations[0].memory_id}`)
        setShowGraph(true)
      }
      // Notify sidebar to refresh
      window.dispatchEvent(new Event('sidebar-refresh'))
    } catch (e: any) {
      setMessages((prev) => [...prev, { role: 'assistant', text: `Error: ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }, [input, loading, conversationId])

  /** Start a fresh conversation. */
  const handleNewChat = () => {
    setMessages([])
    setConversationId(undefined)
    setLoadedConv(null)
    setShowGraph(false)
    setGraphSeed(undefined)
    setInput('')
    // Clear URL params so sidebar click detection works
    navigate('/ask', { replace: true })
  }

  return (
    <div className="flex h-full">
      {/* Chat panel */}
      <div className={`flex flex-col ${showGraph ? 'w-3/5' : 'w-full'} transition-all`}>
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-6 py-2 border-b border-border bg-panel text-xs text-muted">
          <button
            onClick={handleNewChat}
            className="px-2 py-1 rounded hover:bg-white/5 hover:text-white transition-colors"
          >
            + New Chat
          </button>
          {conversationId && (
            <span className="ml-auto font-mono text-[10px] opacity-50">
              {conversationId.slice(0, 12)}
            </span>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.length === 0 && !loading && (
            <div className="flex flex-col items-center justify-center h-full text-muted">
              <Send size={48} strokeWidth={1} className="mb-4 opacity-30 rotate-[-20deg]" />
              <p className="text-lg">Ask anything</p>
              <p className="text-sm mt-1">Get grounded answers with citations from your knowledge base.</p>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div key={idx} className={`max-w-3xl ${msg.role === 'user' ? 'ml-auto' : ''}`}>
              {msg.role === 'user' ? (
                <div className="bg-accent/10 border border-accent/20 rounded-lg px-4 py-3 text-sm">
                  {msg.text}
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Answer */}
                  <div className="text-sm leading-relaxed">
                    <AnswerText text={msg.text} />
                  </div>

                  {/* Verdict */}
                  {msg.response?.verdict && (
                    <div className="text-xs text-muted italic">
                      Verdict: {msg.response.verdict}
                    </div>
                  )}

                  {/* Citations — enriched */}
                  {msg.response?.citations && msg.response.citations.length > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1.5">Citations</h4>
                      <div className="space-y-1.5">
                        {msg.response.citations.map((c: Citation, ci: number) => (
                          <div
                            key={ci}
                            className="flex items-start gap-2 p-2 rounded-lg border border-border bg-surface text-xs"
                          >
                            <FileText size={12} className="shrink-0 mt-0.5 text-accent" />
                            <div className="flex-1 min-w-0">
                              <button
                                onClick={() => navigate(`/search?card=${c.memory_id}`)}
                                className="font-medium text-accent hover:underline truncate block text-left"
                              >
                                {c.title || c.memory_id.slice(0, 20)}
                              </button>
                              {c.file_path && (
                                <p className="text-[10px] text-muted truncate">{c.file_path}</p>
                              )}
                              {c.quote && (
                                <p className="text-muted mt-0.5 line-clamp-2 italic">"{c.quote}"</p>
                              )}
                            </div>
                            {c.open_url && (
                              <a
                                href={c.open_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="shrink-0 px-1.5 py-1 rounded text-[10px] bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
                                title="Open source"
                              >
                                <FolderOpen size={12} />
                              </a>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Evidence — enriched */}
                  {msg.response?.evidence && msg.response.evidence.length > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1.5">Evidence</h4>
                      <div className="space-y-1.5">
                        {msg.response.evidence.map((ev: Evidence, ei: number) => (
                          <div
                            key={ei}
                            className="flex items-start gap-2 p-2 rounded border border-border bg-surface text-xs cursor-pointer hover:border-accent/40 transition-colors"
                            onClick={() => navigate(`/search?card=${ev.memory_id}`)}
                          >
                            <div className="flex-1 min-w-0">
                              <p className="font-medium line-clamp-1">
                                {ev.title || ev.summary || ev.memory_id}
                              </p>
                              {ev.file_path && (
                                <p className="text-[10px] text-muted truncate">{ev.file_path}</p>
                              )}
                              {ev.snippet && <p className="text-muted line-clamp-1 mt-0.5">{ev.snippet}</p>}
                            </div>
                            <div className="flex items-center gap-1 shrink-0">
                              <ReasonBadges reasons={ev.reasons} />
                              <span className="font-mono text-accent">{ev.score.toFixed(2)}</span>
                              {ev.open_url && (
                                <a
                                  href={ev.open_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  onClick={(e) => e.stopPropagation()}
                                  className="ml-1 text-muted hover:text-accent"
                                  title="Open source"
                                >
                                  <FolderOpen size={12} />
                                </a>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Trace link */}
                  {msg.response?.trace_id && (
                    <a
                      href={`/api/exec/${msg.response.trace_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-muted hover:text-accent transition-colors"
                    >
                      <ExternalLink size={10} /> View trace
                    </a>
                  )}

                  {/* Graph toggle */}
                  {msg.response?.citations && msg.response.citations.length > 0 && (
                    <button
                      onClick={() => {
                        setGraphSeed(`mem:${msg.response!.citations[0].memory_id}`)
                        setShowGraph(true)
                      }}
                      className="inline-flex items-center gap-1 text-xs text-muted hover:text-accent transition-colors"
                    >
                      <Share2 size={10} /> Show in graph
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex items-center gap-2 text-muted text-sm">
              <div className="animate-spin w-4 h-4 border-2 border-accent border-t-transparent rounded-full" />
              Thinking...
            </div>
          )}
        </div>

        {/* Input */}
        <div className="p-4 border-t border-border bg-panel">
          <div className="relative max-w-3xl mx-auto">
            <input
              className="w-full bg-surface border border-border rounded-lg pl-4 pr-12 py-3 text-sm
                         focus:outline-none focus:border-accent placeholder:text-muted"
              placeholder="Ask a question..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              disabled={loading}
            />
            <button
              onClick={() => handleSend()}
              disabled={loading || !input.trim()}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-accent hover:text-accent-hover
                         disabled:opacity-30 transition-colors"
            >
              <Send size={18} />
            </button>
          </div>
        </div>
      </div>

      {/* Graph panel */}
      {showGraph && (
        <div className="w-2/5 border-l border-border flex flex-col">
          <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-panel text-xs">
            <span className="text-muted">Cited nodes graph</span>
            <button onClick={() => setShowGraph(false)} className="text-muted hover:text-white">✕</button>
          </div>
          <div className="flex-1">
            <GraphViewer
              seedNodeId={graphSeed}
              onNodeClick={(n) => {
                if (n.type === 'MemoryCard') {
                  navigate(`/search?card=${n.id.replace('mem:', '')}`)
                }
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
