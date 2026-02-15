import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { retrieve, fetchSearchHistory, type RetrieveHit, type SearchHistoryItem } from '../api'
import CardDetail from '../components/CardDetail'
import ReasonBadges from '../components/ReasonBadges'
import { Search, Share2, MessageCircle, Clock, LayoutGrid, List, Image, FileText, Music, Film } from 'lucide-react'

type ViewMode = 'grid' | 'list'

function mimeIcon(mime?: string) {
  if (!mime) return <FileText size={20} className="text-muted" />
  if (mime.startsWith('image/')) return <Image size={20} className="text-blue-400" />
  if (mime.startsWith('audio/')) return <Music size={20} className="text-amber-400" />
  if (mime.startsWith('video/')) return <Film size={20} className="text-purple-400" />
  return <FileText size={20} className="text-muted" />
}

function hasImages(results: RetrieveHit[]) {
  return results.filter(r => r.mime?.startsWith('image/')).length > results.length / 2
}

export default function SearchPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<RetrieveHit[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(params.get('card'))
  const [history, setHistory] = useState<SearchHistoryItem[]>([])
  const [view, setView] = useState<ViewMode>('list')

  // Load search history on mount
  useEffect(() => {
    fetchSearchHistory(10).then(setHistory).catch(() => {})
  }, [])

  // Open card from URL param
  useEffect(() => {
    const card = params.get('card')
    if (card) setSelectedId(card)
  }, [params])

  // Execute search from URL param
  useEffect(() => {
    const q = params.get('q')
    if (q && !query) {
      setQuery(q)
      doSearchFor(q)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const doSearchFor = async (q: string) => {
    if (!q.trim()) return
    setLoading(true)
    try {
      const resp = await retrieve(q)
      const hits = resp.results || []
      setResults(hits)
      setSelectedId(null)
      // Auto-select grid if majority are images
      if (hasImages(hits)) setView('grid')
      // Refresh history + sidebar
      fetchSearchHistory(10).then(setHistory).catch(() => {})
      window.dispatchEvent(new Event('sidebar-refresh'))
    } catch (e) {
      console.error('Search failed', e)
    } finally {
      setLoading(false)
    }
  }

  const doSearch = useCallback(() => doSearchFor(query), [query])

  const askWithResults = () => {
    navigate(`/ask?q=${encodeURIComponent(query)}`)
  }

  const fmtDate = (d?: string) => {
    if (!d) return ''
    try { return new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) } catch { return '' }
  }

  return (
    <div className="flex h-full">
      {/* Left: search + results */}
      <div className={`flex flex-col ${selectedId ? 'w-3/5' : 'w-full'} transition-all`}>
        {/* Search bar */}
        <div className="p-4 border-b border-border bg-panel">
          <div className="relative max-w-2xl">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              className="w-full bg-surface border border-border rounded-lg pl-10 pr-4 py-2.5 text-sm
                         focus:outline-none focus:border-accent placeholder:text-muted"
              placeholder="Search your knowledge base..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && doSearch()}
              autoFocus
            />
          </div>
          {results.length > 0 && (
            <div className="flex items-center gap-3 mt-3">
              <span className="text-xs text-muted">{results.length} results</span>
              <button
                onClick={askWithResults}
                className="flex items-center gap-1.5 text-xs text-accent hover:text-accent-hover transition-colors"
              >
                <MessageCircle size={12} /> Ask using these results
              </button>
              <div className="ml-auto flex items-center gap-1">
                <button onClick={() => setView('grid')}
                  className={`p-1.5 rounded ${view === 'grid' ? 'bg-accent/15 text-accent' : 'text-muted hover:text-white'}`}
                  title="Grid view"><LayoutGrid size={14} /></button>
                <button onClick={() => setView('list')}
                  className={`p-1.5 rounded ${view === 'list' ? 'bg-accent/15 text-accent' : 'text-muted hover:text-white'}`}
                  title="List view"><List size={14} /></button>
              </div>
            </div>
          )}
        </div>

        {/* Results */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading && (
            <div className="flex justify-center py-12">
              <div className="animate-spin w-6 h-6 border-2 border-accent border-t-transparent rounded-full" />
            </div>
          )}

          {/* Empty state */}
          {!loading && results.length === 0 && !selectedId && (
            <div>
              {history.length > 0 && !query && (
                <div className="mb-6">
                  <h3 className="flex items-center gap-1.5 text-xs font-semibold text-muted uppercase tracking-wide mb-3">
                    <Clock size={12} /> Recent Searches
                  </h3>
                  <div className="space-y-1">
                    {history.map((h) => (
                      <button
                        key={h.search_id}
                        onClick={() => { setQuery(h.query_text); doSearchFor(h.query_text) }}
                        className="w-full text-left flex items-center gap-2 px-3 py-2 rounded-lg border border-border
                                   hover:border-accent/40 transition-colors text-sm"
                      >
                        <Search size={12} className="text-muted shrink-0" />
                        <span className="flex-1 truncate">{h.query_text}</span>
                        <span className="text-xs text-muted shrink-0">{h.result_count} results</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {!query && history.length === 0 && (
                <div className="flex flex-col items-center justify-center py-20 text-muted">
                  <Search size={48} strokeWidth={1} className="mb-4 opacity-30" />
                  <p className="text-lg">Search your knowledge</p>
                  <p className="text-sm mt-1">Type a query to find cards, documents, and insights.</p>
                </div>
              )}
              {query && !loading && (
                <p className="text-sm text-muted py-8 text-center">No results found. Try a different query.</p>
              )}
            </div>
          )}

          {/* ── Grid View ──────────────────────────────── */}
          {view === 'grid' && results.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {results.map((hit) => (
                <button
                  key={hit.memory_id}
                  onClick={() => setSelectedId(hit.memory_id)}
                  className={`group relative rounded-xl border overflow-hidden transition-colors
                    ${selectedId === hit.memory_id ? 'border-accent ring-1 ring-accent/30' : 'border-border hover:border-accent/40'}`}
                >
                  {/* Thumbnail or icon */}
                  {hit.thumb_url ? (
                    <img
                      src={hit.thumb_url}
                      alt={hit.title || ''}
                      loading="lazy"
                      className="w-full aspect-square object-cover bg-surface"
                    />
                  ) : (
                    <div className="w-full aspect-square bg-surface flex items-center justify-center">
                      {mimeIcon(hit.mime)}
                    </div>
                  )}
                  {/* Overlay */}
                  <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent p-2.5 pt-8">
                    <p className="text-xs font-medium text-white line-clamp-2">
                      {hit.title || hit.summary?.slice(0, 50) || hit.memory_id.slice(0, 12)}
                    </p>
                    <div className="flex items-center gap-1.5 mt-1">
                      <span className="text-[10px] text-gray-300">{fmtDate(hit.created_at)}</span>
                      {hit.source_type && (
                        <span className="text-[10px] px-1 py-0.5 rounded bg-white/10 text-gray-300">{hit.source_type}</span>
                      )}
                    </div>
                  </div>
                  {/* Score badge */}
                  <span className="absolute top-1.5 right-1.5 text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/60 text-accent">
                    {hit.score.toFixed(2)}
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* ── List View ──────────────────────────────── */}
          {view === 'list' && results.length > 0 && (
            <div className="space-y-2">
              {results.map((hit) => (
                <button
                  key={hit.memory_id}
                  onClick={() => setSelectedId(hit.memory_id)}
                  className={`w-full text-left p-4 rounded-lg border transition-colors flex items-start gap-3
                    ${selectedId === hit.memory_id
                      ? 'border-accent bg-accent/5'
                      : 'border-border bg-panel hover:border-accent/40'}`}
                >
                  {/* Thumbnail / icon */}
                  {hit.thumb_url ? (
                    <img src={hit.thumb_url} alt="" loading="lazy"
                      className="w-16 h-16 rounded-lg object-cover shrink-0 bg-surface" />
                  ) : (
                    <div className="w-16 h-16 rounded-lg bg-surface flex items-center justify-center shrink-0">
                      {mimeIcon(hit.mime)}
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium line-clamp-1">
                      {hit.title || hit.summary?.slice(0, 60) || hit.memory_id.slice(0, 16)}
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">
                      {hit.summary || ''}
                    </p>
                    <div className="flex items-center gap-2 mt-2">
                      <ReasonBadges reasons={hit.reasons} />
                      {hit.source_type && (
                        <span className="text-[10px] text-muted">{hit.source_type}</span>
                      )}
                      {hit.created_at && (
                        <span className="text-[10px] text-muted">{fmtDate(hit.created_at)}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span className="text-xs font-mono text-accent">{hit.score.toFixed(2)}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        navigate(`/graph?seed=${encodeURIComponent('mem:' + hit.memory_id)}`)
                      }}
                      className="text-muted hover:text-accent transition-colors"
                      title="Explore in Graph"
                    >
                      <Share2 size={14} />
                    </button>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right: card detail drawer */}
      {selectedId && (
        <div className="w-2/5 border-l border-border">
          <CardDetail
            memoryId={selectedId}
            onClose={() => setSelectedId(null)}
            onOpenGraph={(nodeId) => navigate(`/graph?seed=${encodeURIComponent(nodeId)}`)}
          />
        </div>
      )}
    </div>
  )
}
