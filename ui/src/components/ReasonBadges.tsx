interface Props {
  reasons: string[]
}

const BADGES: Record<string, { bg: string; text: string }> = {
  fts: { bg: 'bg-emerald-500/15 text-emerald-400', text: 'FTS' },
  semantic: { bg: 'bg-blue-500/15 text-blue-400', text: 'Semantic' },
  graph: { bg: 'bg-purple-500/15 text-purple-400', text: 'Graph' },
  recency: { bg: 'bg-amber-500/15 text-amber-400', text: 'Recent' },
  source_boost: { bg: 'bg-pink-500/15 text-pink-400', text: 'Source' },
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
