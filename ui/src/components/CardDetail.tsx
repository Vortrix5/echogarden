import { FolderOpen, Music, Share2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cardOpenUrl, fetchCard, type Card } from '../api'

interface Props {
    memoryId: string
    onClose: () => void
    onOpenGraph?: (nodeId: string) => void
}

export default function CardDetail({ memoryId, onClose, onOpenGraph }: Props) {
    const [card, setCard] = useState<Card | null>(null)
    const [error, setError] = useState('')

    useEffect(() => {
        setCard(null)
        setError('')
        fetchCard(memoryId).then(setCard).catch((e) => setError(e.message))
    }, [memoryId])

    const mime = (card as any)?.mime as string | undefined
    const mediaUrl = (card as any)?.media_url as string | undefined
    const thumbUrl = (card as any)?.thumb_url as string | undefined

    return (
        <div className="h-full flex flex-col bg-panel border-l border-border">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-border">
                <h3 className="text-sm font-medium truncate flex-1">
                    {card?.title || memoryId}
                </h3>
                <button onClick={onClose} className="text-muted hover:text-white ml-2"><X size={18} /></button>
            </div>

            {error && <p className="p-4 text-red-400 text-sm">{error}</p>}

            {card && (
                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {/* Media preview */}
                    {mime?.startsWith('image/') && mediaUrl && (
                        <div className="rounded-lg overflow-hidden border border-border bg-surface">
                            <img src={mediaUrl} alt={card.title || ''} className="w-full max-h-72 object-contain" />
                        </div>
                    )}
                    {mime?.startsWith('audio/') && mediaUrl && (
                        <div className="flex items-center gap-3 p-3 rounded-lg border border-border bg-surface">
                            <Music size={18} className="text-amber-400 shrink-0" />
                            <audio controls src={mediaUrl} className="flex-1 h-8" />
                        </div>
                    )}

                    {/* Summary */}
                    <section>
                        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">Summary</h4>
                        <p className="text-sm leading-relaxed">{card.summary || '—'}</p>
                    </section>

                    {/* Content */}
                    {card.content_text && (
                        <section>
                            <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">Content</h4>
                            <p className="text-sm leading-relaxed whitespace-pre-wrap text-gray-300 max-h-60 overflow-y-auto">
                                {card.content_text}
                            </p>
                        </section>
                    )}

                    {/* Metadata */}
                    <section>
                        <h4 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">Info</h4>
                        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                            <dt className="text-muted">Type</dt><dd>{card.type || '—'}</dd>
                            <dt className="text-muted">Created</dt><dd>{card.created_at || '—'}</dd>
                            {mime && <><dt className="text-muted">MIME</dt><dd>{mime}</dd></>}
                            {card.file_path && (
                                <><dt className="text-muted">File</dt><dd className="truncate" title={card.file_path}>{card.file_path}</dd></>
                            )}
                            {card.url && (
                                <><dt className="text-muted">URL</dt><dd className="truncate"><a href={card.url} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">{card.url}</a></dd></>
                            )}
                        </dl>
                    </section>

                    {/* Action buttons */}
                    <div className="flex items-center gap-3">
                        {(card.open_url || card.file_path || card.blob_id) && (
                            <a
                                href={card.open_url || cardOpenUrl(memoryId)}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center gap-2 text-sm text-accent hover:text-accent-hover transition-colors"
                            >
                                <FolderOpen size={14} /> Open Source
                            </a>
                        )}
                        {onOpenGraph && (
                            <button
                                onClick={() => onOpenGraph(`mem:${memoryId}`)}
                                className="flex items-center gap-2 text-sm text-accent hover:text-accent-hover transition-colors"
                            >
                                <Share2 size={14} /> Explore in Graph
                            </button>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}
