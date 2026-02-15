import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import GraphViewer from '../components/GraphViewer'
import CardDetail from '../components/CardDetail'
import type { GraphNode } from '../api'

export default function GraphPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [seedNodeId, setSeedNodeId] = useState<string | undefined>(params.get('seed') || undefined)
  const [selectedCard, setSelectedCard] = useState<string | null>(null)

  useEffect(() => {
    const s = params.get('seed')
    if (s) setSeedNodeId(s)
  }, [params])

  const handleNodeClick = (node: GraphNode) => {
    if (node.type === 'MemoryCard') {
      // Extract memory_id from node id (mem:xxx → xxx)
      const memId = node.id.startsWith('mem:') ? node.id.slice(4) : node.id
      setSelectedCard(memId)
    } else {
      // For entities, re-seed the graph
      setSeedNodeId(node.id)
      navigate(`/graph?seed=${encodeURIComponent(node.id)}`, { replace: true })
    }
  }

  return (
    <div className="flex h-full">
      {/* Graph canvas */}
      <div className={`${selectedCard ? 'w-3/5' : 'w-full'} transition-all`}>
        <GraphViewer seedNodeId={seedNodeId} onNodeClick={handleNodeClick} />
      </div>

      {/* Card detail sidebar */}
      {selectedCard && (
        <div className="w-2/5 border-l border-border">
          <CardDetail
            memoryId={selectedCard}
            onClose={() => setSelectedCard(null)}
            onOpenGraph={(nodeId) => {
              setSeedNodeId(nodeId)
              navigate(`/graph?seed=${encodeURIComponent(nodeId)}`, { replace: true })
            }}
          />
        </div>
      )}
    </div>
  )
}
