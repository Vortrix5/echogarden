interface Props {
  reasons: string[]
}

// Keys are the reason names emitted by api/app/retrieval/service.py.
const BADGES: Record<string, { bg: string; text: string }> = {
  fts_match: { bg: 'bg-emerald-500/15 text-emerald-400', text: 'FTS' },
  semantic_text: { bg: 'bg-blue-500/15 text-blue-400', text: 'Semantic' },
  graph_expand: { bg: 'bg-purple-500/15 text-purple-400', text: 'Graph' },
}

export default function ReasonBadges({ reasons }: Props) {
  if (!reasons || reasons.length === 0) return null
  return (
    <span className="inline-flex gap-1 flex-wrap">
      {reasons.map((r) => {
        const badge = BADGES[r] || { bg: 'bg-gray-500/15 text-gray-400', text: r }
        return (
          <span key={r} className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${badge.bg}`}>
            {badge.text}
          </span>
        )
      })}
    </span>
  )
}
