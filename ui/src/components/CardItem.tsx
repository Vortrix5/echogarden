import type { Card } from '../api'

interface Props {
  card: Card
  onClick?: () => void
  compact?: boolean
}

export default function CardItem({ card, onClick, compact }: Props) {
  const time = card.created_at
    ? new Date(card.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : ''

  return (
    <button
      onClick={onClick}
      className={`w-full text-left rounded-lg border border-border bg-panel hover:border-accent/40 transition-colors
        ${compact ? 'p-3' : 'p-4'}`}
    >
      <p className={`text-sm leading-relaxed ${compact ? 'line-clamp-2' : 'line-clamp-3'}`}>
        {card.summary || card.memory_id}
      </p>
      <div className="flex items-center gap-2 mt-2 text-xs text-muted">
        {card.type && (
          <span className="px-1.5 py-0.5 rounded bg-accent/10 text-accent">{card.type}</span>
        )}
        {time && <span>{time}</span>}
      </div>
    </button>
  )
}
