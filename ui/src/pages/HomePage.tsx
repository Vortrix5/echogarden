import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchFeedToday, fetchDigest, type FeedToday, type Digest } from '../api'
import CardItem from '../components/CardItem'
import { Clock, Tag, Bell, TrendingUp, Image, Music, Film, FileText, Activity } from 'lucide-react'

export default function HomePage() {
  const [feed, setFeed] = useState<FeedToday | null>(null)
  const [digestFallback, setDigestFallback] = useState<Digest | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    setLoading(true)
    fetchFeedToday()
      .then(setFeed)
      .catch(() => {
        // Fallback to legacy digest
        fetchDigest('24h')
          .then(setDigestFallback)
          .catch((e) => setError(e.message))
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-muted">
        <div className="animate-spin w-6 h-6 border-2 border-accent border-t-transparent rounded-full" />
      </div>
    )
  }

  if (error) {
    return <div className="p-8 text-red-400 text-sm">{error}</div>
  }

  // Legacy fallback
  if (!feed && digestFallback) {
    return <LegacyDigest digest={digestFallback} navigate={navigate} />
  }
  if (!feed) return null

  const isOverdue = (due: string) => {
    try { return new Date(due) < new Date() } catch { return false }
  }

  const stats = feed.activity_summary
  const fmtDate = (d: string) => {
    try { return new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) } catch { return d }
  }

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Today</h1>
        <p className="text-sm text-muted mt-1">{feed.date} &middot; Your personal knowledge feed</p>
      </div>

      {/* Activity bar */}
      {stats.total > 0 && (
        <div className="flex items-center gap-4 p-4 rounded-xl border border-border bg-panel">
          <Activity size={16} className="text-accent shrink-0" />
          <span className="text-sm font-medium">{stats.total} memories today</span>
          <div className="flex items-center gap-3 ml-auto text-xs text-muted">
            {stats.images > 0 && <span className="flex items-center gap-1"><Image size={12} className="text-blue-400" />{stats.images}</span>}
            {stats.audio > 0 && <span className="flex items-center gap-1"><Music size={12} className="text-amber-400" />{stats.audio}</span>}
            {stats.video > 0 && <span className="flex items-center gap-1"><Film size={12} className="text-purple-400" />{stats.video}</span>}
            {stats.files > 0 && <span className="flex items-center gap-1"><FileText size={12} className="text-gray-400" />{stats.files}</span>}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main: Recent Memories */}
        <div className="lg:col-span-2 space-y-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-muted uppercase tracking-wide">
            <Clock size={14} /> Recent Memories
          </h2>
          {feed.recent_memories.length === 0 && (
            <p className="text-sm text-muted">No memories yet today. Try dropping a file!</p>
          )}
          <div className="space-y-2">
            {feed.recent_memories.map((m) => (
              <button
                key={m.memory_id}
                onClick={() => navigate(`/search?card=${m.memory_id}`)}
                className="w-full text-left rounded-lg border border-border bg-panel hover:border-accent/40 transition-colors p-3 flex items-start gap-3"
              >
                {/* Thumbnail */}
                {m.thumb_url ? (
                  <img src={m.thumb_url} alt="" loading="lazy"
                    className="w-14 h-14 rounded-lg object-cover shrink-0 bg-surface" />
                ) : m.mime?.startsWith('audio/') ? (
                  <div className="w-14 h-14 rounded-lg bg-surface flex items-center justify-center shrink-0">
                    <Music size={18} className="text-amber-400" />
                  </div>
                ) : null}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium line-clamp-1">{m.title}</p>
                  <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{m.summary}</p>
                  <span className="text-[10px] text-muted mt-1 block">{fmtDate(m.created_at)}</span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Reminders */}
          <section>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-muted uppercase tracking-wide mb-2">
              <Bell size={14} /> Reminders
            </h2>
            {feed.reminders.length === 0 && <p className="text-xs text-muted">No reminders.</p>}
            <ul className="space-y-1.5">
              {feed.reminders.map((r) => (
                <li
                  key={r.memory_id}
                  className="flex items-start gap-2 text-sm cursor-pointer hover:text-accent transition-colors"
                  onClick={() => navigate(`/search?card=${r.memory_id}`)}
                >
                  <span className={`shrink-0 w-1.5 h-1.5 mt-1.5 rounded-full ${
                    r.overdue ? 'bg-red-500 animate-pulse'
                    : r.priority === 'high' ? 'bg-red-400'
                    : r.priority === 'low' ? 'bg-gray-400'
                    : 'bg-amber-400'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <span className="line-clamp-2">{r.text}</span>
                    <span className={`text-[10px] ml-1 ${r.overdue ? 'text-red-400' : 'text-muted'}`}>
                      {r.overdue ? 'overdue' : r.due?.slice(0, 10)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          {/* Emerging Topics */}
          <section>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-muted uppercase tracking-wide mb-2">
              <TrendingUp size={14} /> Emerging Topics
            </h2>
            <div className="flex flex-wrap gap-1.5">
              {feed.emerging_topics.map((t) => (
                <button
                  key={t.entity}
                  onClick={() => navigate(`/graph?seed=${encodeURIComponent('ent:' + t.entity)}`)}
                  className="px-2.5 py-1 rounded-full text-xs border border-border text-gray-300 hover:border-accent hover:text-accent transition-colors"
                >
                  {t.entity} <span className="text-muted ml-1">x{t.count_recent}</span>
                </button>
              ))}
              {feed.emerging_topics.length === 0 && (
                <p className="text-xs text-muted">No emerging topics yet.</p>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

/* Fallback for when /feed/today isn't available */
function LegacyDigest({ digest, navigate }: { digest: Digest; navigate: ReturnType<typeof useNavigate> }) {
  return (
    <div className="max-w-5xl mx-auto p-6 space-y-8">
      <h1 className="text-2xl font-bold">Daily Digest</h1>
      <div className="space-y-2">
        {digest.recent_cards.map((c) => (
          <CardItem
            key={c.memory_id}
            card={c}
            compact
            onClick={() => navigate(`/search?card=${c.memory_id}`)}
          />
        ))}
      </div>
    </div>
  )
}
