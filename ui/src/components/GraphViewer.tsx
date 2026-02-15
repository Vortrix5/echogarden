import { useCallback, useEffect, useRef, useState } from 'react'
import type { GraphNode, GraphEdge, SubgraphResponse } from '../api'
import { fetchSubgraph, fetchNeighbors, searchGraphNodes } from '../api'
import { Search, Maximize2, ZoomIn, ZoomOut, Box } from 'lucide-react'

// Lazy-load force-graph to avoid SSR issues
import ForceGraph2D from 'react-force-graph-2d'

// Node type → color mapping
const TYPE_COLORS: Record<string, string> = {
  MemoryCard: '#6c63ff',
  Entity: '#22d3ee',
  Person: '#f472b6',
  Organization: '#fb923c',
  Location: '#4ade80',
  Topic: '#a78bfa',
  Concept: '#facc15',
}

function nodeColor(type: string): string {
  return TYPE_COLORS[type] || '#8b8fa3'
}

interface Props {
  seedNodeId?: string
  onNodeClick?: (node: GraphNode) => void
}

interface ForceGraphNode extends GraphNode {
  x?: number
  y?: number
  z?: number
  vx?: number
  vy?: number
  vz?: number
}

interface GraphData {
  nodes: ForceGraphNode[]
  links: { source: string; target: string; type: string; id: string; weight: number }[]
}

export default function GraphViewer({ seedNodeId, onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const fgRef = useRef<any>(null)
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] })
  const [loading, setLoading] = useState(false)
  const [hops, setHops] = useState(1)
  const [limit, setLimit] = useState(150)
  const [searchQuery, setSearchQuery] = useState('')
  const [is3D, setIs3D] = useState(false)
  const [filterTypes, setFilterTypes] = useState<Set<string>>(new Set())

  // Dynamic import for 3D
  const [ForceGraph3DComp, setForceGraph3DComp] = useState<any>(null)
  useEffect(() => {
    if (is3D) {
      import('react-force-graph-3d').then((mod) => setForceGraph3DComp(() => mod.default))
    }
  }, [is3D])

  const allTypes = Array.from(new Set(graphData.nodes.map((n) => n.type)))

  const loadSubgraph = useCallback(async (seed: string, h: number, lim: number) => {
    setLoading(true)
    try {
      const resp: SubgraphResponse = await fetchSubgraph(seed, h, lim)
      applyGraphData(resp)
    } catch (e) {
      console.error('Graph load error', e)
    } finally {
      setLoading(false)
    }
  }, [])

  const applyGraphData = (resp: SubgraphResponse) => {
    const nodeMap = new Map<string, ForceGraphNode>()
    resp.nodes.forEach((n) => nodeMap.set(n.id, { ...n }))
    const links = resp.edges
      .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map((e) => ({ source: e.source, target: e.target, type: e.type, id: e.id, weight: e.weight }))
    setGraphData({ nodes: Array.from(nodeMap.values()), links })
  }

  // Load on seed change
  useEffect(() => {
    if (seedNodeId) {
      loadSubgraph(seedNodeId, hops, limit)
    }
  }, [seedNodeId, hops, limit, loadSubgraph])

  // Search nodes
  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    setLoading(true)
    try {
      const res = await searchGraphNodes(searchQuery)
      if (res.nodes.length > 0) {
        // Load subgraph seeded from first result
        await loadSubgraph(res.nodes[0].id, hops, limit)
      }
    } catch (e) {
      console.error('Search error', e)
    } finally {
      setLoading(false)
    }
  }

  // Expand node
  const expandNode = async (nodeId: string) => {
    try {
      const resp = await fetchNeighbors(nodeId, 1, 100)
      setGraphData((prev) => {
        const nodeMap = new Map(prev.nodes.map((n) => [n.id, n]))
        resp.nodes.forEach((n) => { if (!nodeMap.has(n.id)) nodeMap.set(n.id, { ...n }) })
        const existingEdgeIds = new Set(prev.links.map((l) => l.id))
        const newLinks = resp.edges
          .filter((e) => !existingEdgeIds.has(e.id) && nodeMap.has(e.source) && nodeMap.has(e.target))
          .map((e) => ({ source: e.source, target: e.target, type: e.type, id: e.id, weight: e.weight }))
        return { nodes: Array.from(nodeMap.values()), links: [...prev.links, ...newLinks] }
      })
    } catch (e) {
      console.error('Expand error', e)
    }
  }

  const handleNodeClick = (node: any) => {
    if (node.type === 'MemoryCard') {
      onNodeClick?.(node as GraphNode)
    } else {
      expandNode(node.id)
    }
  }

  const filteredData = filterTypes.size > 0
    ? {
        nodes: graphData.nodes.filter((n) => filterTypes.has(n.type)),
        links: graphData.links.filter((l) => {
          const src = typeof l.source === 'string' ? l.source : (l.source as any).id
          const tgt = typeof l.target === 'string' ? l.target : (l.target as any).id
          return graphData.nodes.some((n) => n.id === src && filterTypes.has(n.type))
            && graphData.nodes.some((n) => n.id === tgt && filterTypes.has(n.type))
        }),
      }
    : graphData

  const [dims, setDims] = useState({ w: 800, h: 600 })
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => {
      setDims({ w: entry.contentRect.width, h: entry.contentRect.height })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const GraphComp = is3D && ForceGraph3DComp ? ForceGraph3DComp : ForceGraph2D

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-panel flex-wrap">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
          <input
            className="w-full bg-surface border border-border rounded-md pl-8 pr-3 py-1.5 text-sm focus:outline-none focus:border-accent"
            placeholder="Search nodes..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
        </div>

        {/* Hops */}
        <div className="flex items-center gap-1 text-xs text-muted">
          <span>Hops</span>
          <select
            value={hops}
            onChange={(e) => setHops(Number(e.target.value))}
            className="bg-surface border border-border rounded px-1.5 py-1 text-xs focus:outline-none"
          >
            <option value={1}>1</option>
            <option value={2}>2</option>
          </select>
        </div>

        {/* Limit slider */}
        <div className="flex items-center gap-1 text-xs text-muted">
          <span>Limit</span>
          <input
            type="range" min={50} max={300} value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="w-20 accent-accent"
          />
          <span className="w-7 text-right">{limit}</span>
        </div>

        {/* Type filters */}
        {allTypes.length > 0 && (
          <div className="flex items-center gap-1">
            {allTypes.map((t) => (
              <button
                key={t}
                onClick={() => setFilterTypes((prev) => {
                  const next = new Set(prev)
                  next.has(t) ? next.delete(t) : next.add(t)
                  return next
                })}
                className={`px-2 py-0.5 rounded-full text-xs border transition-colors
                  ${filterTypes.has(t) ? 'border-accent text-accent bg-accent/10' : 'border-border text-muted hover:text-white'}`}
                style={filterTypes.has(t) ? {} : { borderColor: nodeColor(t) + '60', color: nodeColor(t) }}
              >
                {t}
              </button>
            ))}
          </div>
        )}

        {/* 3D toggle */}
        <button
          onClick={() => setIs3D(!is3D)}
          className={`flex items-center gap-1 px-2 py-1 rounded text-xs border transition-colors
            ${is3D ? 'border-accent text-accent bg-accent/10' : 'border-border text-muted hover:text-white'}`}
          title="Toggle 3D mode"
        >
          <Box size={14} />
          {is3D ? '3D' : '2D'}
        </button>

        {/* Zoom controls */}
        <button onClick={() => fgRef.current?.zoomToFit(300)} className="text-muted hover:text-white" title="Fit">
          <Maximize2 size={16} />
        </button>
      </div>

      {/* Graph canvas */}
      <div ref={containerRef} className="flex-1 relative bg-surface">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-surface/60 z-10">
            <div className="animate-spin w-6 h-6 border-2 border-accent border-t-transparent rounded-full" />
          </div>
        )}

        {filteredData.nodes.length === 0 && !loading ? (
          <div className="absolute inset-0 flex items-center justify-center text-muted text-sm">
            {seedNodeId
              ? 'No graph data found for this node.'
              : 'Search for a node or select a card to visualize its graph.'}
          </div>
        ) : (
          <GraphComp
            ref={fgRef}
            width={dims.w}
            height={dims.h}
            graphData={filteredData}
            nodeLabel={(node: any) => `${node.label} (${node.type})`}
            nodeColor={(node: any) => nodeColor(node.type)}
            nodeRelSize={6}
            nodeVal={(node: any) => node.type === 'MemoryCard' ? 3 : 2}
            nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
              const r = node.type === 'MemoryCard' ? 5 : 4
              const color = nodeColor(node.type)
              ctx.beginPath()
              ctx.arc(node.x!, node.y!, r, 0, 2 * Math.PI)
              ctx.fillStyle = color
              ctx.fill()
              if (globalScale > 1.5) {
                const label = (node.label as string || '').slice(0, 20)
                ctx.font = `${Math.max(10 / globalScale, 2)}px sans-serif`
                ctx.textAlign = 'center'
                ctx.fillStyle = '#e2e8f0'
                ctx.fillText(label, node.x!, node.y! + r + 8 / globalScale)
              }
            }}
            linkColor={() => '#2a2d3a'}
            linkWidth={(link: any) => Math.max(0.5, (link.weight || 0.5) * 2)}
            linkDirectionalParticles={1}
            linkDirectionalParticleWidth={1.5}
            linkDirectionalParticleColor={() => '#6c63ff40'}
            onNodeClick={handleNodeClick}
            cooldownTicks={80}
            enableNodeDrag
            backgroundColor="#0f1117"
          />
        )}
      </div>
    </div>
  )
}
