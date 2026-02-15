/* API client — all calls go through the Vite dev-server proxy (/api → backend). */

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers as Record<string, string>) },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`API ${res.status}: ${text}`)
  }
  return res.json()
}

// ── Cards ────────────────────────────────────────────────

export interface Card {
  memory_id: string
  summary?: string
  type?: string
  created_at?: string
  content_text?: string
  metadata?: Record<string, unknown>
  metadata_json?: Record<string, unknown>
  card_type?: string
  source_type?: string
  title?: string
  file_path?: string
  url?: string
  blob_id?: string
  open_url?: string
}

export function fetchCards(params?: { limit?: number; offset?: number; q?: string; source_type?: string; card_type?: string }) {
  const sp = new URLSearchParams()
  if (params?.limit) sp.set('limit', String(params.limit))
  if (params?.offset) sp.set('offset', String(params.offset))
  if (params?.q) sp.set('q', params.q)
  if (params?.source_type) sp.set('source_type', params.source_type)
  if (params?.card_type) sp.set('card_type', params.card_type)
  return request<Card[]>(`/cards?${sp}`)
}

export function fetchCard(id: string) {
  return request<Card>(`/cards/${encodeURIComponent(id)}`)
}

/** URL for opening / downloading the card's original source file. */
export function cardOpenUrl(id: string) {
  return `${BASE}/cards/${encodeURIComponent(id)}/open`
}

/** URL for streaming a raw blob. */
export function blobUrl(blobId: string) {
  return `${BASE}/blobs/${encodeURIComponent(blobId)}`
}

// ── Digest ───────────────────────────────────────────────

export interface DigestEntity { canonical: string; type: string; count: number }
export interface DigestReminder { text: string; due: string; priority: string; memory_id: string }
export interface DigestCluster {
  entity: { id: string; label: string; type: string }
  related_memory_ids: string[]
}
export interface Digest {
  window: string
  recent_cards: Card[]
  top_entities: DigestEntity[]
  reminders: DigestReminder[]
  actions: DigestReminder[]          // backward-compat alias
  suggested_clusters: DigestCluster[]
}

export function fetchDigest(window: '24h' | '7d' | '30d' = '24h', limit = 50) {
  return request<Digest>(`/digest?window=${window}&limit=${limit}`)
}

// ── Feed Today (Phase 9) ─────────────────────────────────

export interface FeedReminder { text: string; due: string; priority: string; memory_id: string; overdue: boolean }
export interface FeedMemory {
  memory_id: string; title: string; summary: string; mime: string
  thumb_url: string; media_url: string; open_url: string; created_at: string
}
export interface FeedTopic { entity: string; type: string; count_recent: number }
export interface ActivitySummary { total: number; images: number; audio: number; video: number; files: number }
export interface FeedToday {
  date: string; reminders: FeedReminder[]; recent_memories: FeedMemory[]
  emerging_topics: FeedTopic[]; activity_summary: ActivitySummary
}

export function fetchFeedToday() {
  return request<FeedToday>('/feed/today')
}

// ── Retrieve (search) ────────────────────────────────────

export interface RetrieveHit {
  memory_id: string
  summary?: string
  final_score: number
  score: number
  reasons: string[]
  snippet?: string
  source_type?: string
  created_at?: string
  // Phase 9 — media-first fields
  title?: string
  mime?: string
  media_url?: string
  thumb_url?: string
  open_url?: string
  signals?: { fts: number; semantic: number; graph: number; recency: number; source_boost: number }
}
export interface RetrieveResponse {
  results: RetrieveHit[]
  trace_id?: string
}

export async function retrieve(query: string, top_k = 8) {
  const resp = await request<{ results: any[] }>('/retrieve', {
    method: 'POST',
    body: JSON.stringify({ query, top_k }),
  })
  return {
    ...resp,
    results: (resp.results || []).map((r: any) => ({
      ...r,
      score: r.final_score ?? r.score ?? 0,
    })),
  } as RetrieveResponse
}

// ── Search History ───────────────────────────────────────

export interface SearchHistoryItem {
  search_id: string
  query_text: string
  result_count: number
  created_at: string
}

export function fetchSearchHistory(limit = 20) {
  return request<SearchHistoryItem[]>(`/search/history?limit=${limit}`)
}

// ── Chat ─────────────────────────────────────────────────

export interface Citation {
  memory_id: string
  quote: string
  source_type: string
  created_at: string
  title?: string
  file_path?: string
  url?: string
  blob_id?: string
  open_url?: string
}
export interface Evidence {
  memory_id: string
  summary: string
  snippet: string
  score: number
  reasons: string[]
  title?: string
  source_type?: string
  file_path?: string
  open_url?: string
}
export interface ChatResponse {
  trace_id: string
  answer: string
  verdict: string
  citations: Citation[]
  evidence: Evidence[]
  status: string
  conversation_id?: string
}

export function chat(message: string, top_k = 8, conversation_id?: string) {
  return request<ChatResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify({
      message,
      top_k,
      use_graph: true,
      hops: 1,
      ...(conversation_id ? { conversation_id } : {}),
    }),
  })
}

// ── Conversations ────────────────────────────────────────

export interface ConversationSummary {
  conversation_id: string
  title: string
  created_at: string
  updated_at: string
}
export interface ConversationTurn {
  turn_id: string
  user_text: string
  assistant_text: string
  verdict?: string
  created_at: string
}
export interface ConversationDetail {
  conversation_id: string
  title: string
  created_at: string
  updated_at: string
  turns: ConversationTurn[]
}

export function fetchConversations(limit = 20) {
  return request<ConversationSummary[]>(`/conversations?limit=${limit}`)
}

export function fetchConversation(id: string) {
  return request<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`)
}

// ── Graph ────────────────────────────────────────────────

export interface GraphNode {
  id: string
  type: string
  label: string
  props: Record<string, unknown>
}
export interface GraphEdge {
  id: string
  source: string
  target: string
  type: string
  weight: number
}
export interface SubgraphResponse {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export function fetchSubgraph(seed: string, hops = 1, limit = 200) {
  const sp = new URLSearchParams({ seed, hops: String(hops), limit: String(limit) })
  return request<SubgraphResponse>(`/graph/subgraph?${sp}`)
}

export function searchGraphNodes(query: string, type?: string, limit = 20) {
  const sp = new URLSearchParams({ query, limit: String(limit) })
  if (type) sp.set('type', type)
  return request<{ nodes: GraphNode[] }>(`/graph/search?${sp}`)
}

export function fetchNeighbors(nodeId: string, hops = 1, limit = 200) {
  const sp = new URLSearchParams({ node_id: nodeId, hops: String(hops), limit: String(limit) })
  return request<SubgraphResponse>(`/graph/neighbors?${sp}`)
}
