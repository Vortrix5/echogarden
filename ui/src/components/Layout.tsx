import { ChevronRight, Clock, Home, MessageCircle, Search, Share2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { fetchConversations, fetchSearchHistory, type ConversationSummary, type SearchHistoryItem } from '../api'

const NAV = [
    { to: '/', icon: Home, label: 'Today' },
    { to: '/search', icon: Search, label: 'Search' },
    { to: '/ask', icon: MessageCircle, label: 'Chat' },
    { to: '/graph', icon: Share2, label: 'Graph' },
] as const

export default function Layout() {
    const navigate = useNavigate()
    const location = useLocation()
    const [recentChats, setRecentChats] = useState<ConversationSummary[]>([])
    const [recentSearches, setRecentSearches] = useState<SearchHistoryItem[]>([])

    const refreshSidebar = useCallback(() => {
        fetchConversations(10).then(setRecentChats).catch(() => { })
        fetchSearchHistory(10).then(setRecentSearches).catch(() => { })
    }, [])

    // Initial load + refresh when route changes
    useEffect(() => {
        refreshSidebar()
    }, [location.pathname, location.search]) // eslint-disable-line react-hooks/exhaustive-deps

    // Listen for custom sidebar-refresh events (dispatched after chat or search)
    useEffect(() => {
        const handler = () => refreshSidebar()
        window.addEventListener('sidebar-refresh', handler)
        return () => window.removeEventListener('sidebar-refresh', handler)
    }, [refreshSidebar])

    return (
        <div className="flex h-screen overflow-hidden">
            {/* Sidebar */}
            <aside className="w-56 flex flex-col bg-panel border-r border-border shrink-0">
                {/* Logo */}
                <div className="px-4 py-4 border-b border-border">
                    <span className="text-accent font-bold text-base select-none">EchoGarden</span>
                </div>

                {/* Nav */}
                <nav className="px-2 py-3 space-y-0.5">
                    {NAV.map(({ to, icon: Icon, label }) => (
                        <NavLink
                            key={to}
                            to={to}
                            end={to === '/'}
                            className={({ isActive }) =>
                                `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors
                 ${isActive ? 'text-accent bg-accent/10 font-medium' : 'text-muted hover:text-white hover:bg-white/5'}`
                            }
                        >
                            <Icon size={16} />
                            <span>{label}</span>
                        </NavLink>
                    ))}
                </nav>

                <div className="border-t border-border my-1" />

                {/* Recent Chats */}
                <div className="px-3 py-2 flex-1 min-h-0 overflow-y-auto">
                    <h3 className="flex items-center gap-1.5 text-[10px] font-semibold text-muted uppercase tracking-widest mb-2 px-1">
                        <MessageCircle size={10} /> Recent Chats
                    </h3>
                    {recentChats.length === 0 && (
                        <p className="text-[11px] text-muted/60 px-1">No conversations yet</p>
                    )}
                    <div className="space-y-0.5">
                        {recentChats.map((c) => (
                            <button
                                key={c.conversation_id}
                                onClick={() => navigate(`/ask?conv=${c.conversation_id}`)}
                                className="w-full text-left flex items-center gap-1.5 px-2 py-1.5 rounded text-xs
                           text-gray-400 hover:text-white hover:bg-white/5 transition-colors group"
                            >
                                <ChevronRight size={10} className="shrink-0 text-muted/40 group-hover:text-accent" />
                                <span className="truncate">{c.title || c.conversation_id.slice(0, 12)}</span>
                            </button>
                        ))}
                    </div>

                    <h3 className="flex items-center gap-1.5 text-[10px] font-semibold text-muted uppercase tracking-widest mt-4 mb-2 px-1">
                        <Clock size={10} /> Recent Searches
                    </h3>
                    {recentSearches.length === 0 && (
                        <p className="text-[11px] text-muted/60 px-1">No searches yet</p>
                    )}
                    <div className="space-y-0.5">
                        {recentSearches.map((s) => (
                            <button
                                key={s.search_id}
                                onClick={() => navigate(`/search?q=${encodeURIComponent(s.query_text)}`)}
                                className="w-full text-left flex items-center gap-1.5 px-2 py-1.5 rounded text-xs
                           text-gray-400 hover:text-white hover:bg-white/5 transition-colors group"
                            >
                                <Search size={10} className="shrink-0 text-muted/40 group-hover:text-accent" />
                                <span className="truncate">{s.query_text}</span>
                                <span className="ml-auto text-[10px] text-muted/40 shrink-0">{s.result_count}</span>
                            </button>
                        ))}
                    </div>
                </div>
            </aside>

            {/* Main content */}
            <main className="flex-1 overflow-y-auto">
                <Outlet />
            </main>
        </div>
    )
}
