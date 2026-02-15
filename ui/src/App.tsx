import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import AskPage from './pages/AskPage'
import GraphPage from './pages/GraphPage'
import HomePage from './pages/HomePage'
import SearchPage from './pages/SearchPage'

export default function App() {
    return (
        <Routes>
            <Route element={<Layout />}>
                <Route path="/" element={<HomePage />} />
                <Route path="/search" element={<SearchPage />} />
                <Route path="/ask" element={<AskPage />} />
                <Route path="/graph" element={<GraphPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
        </Routes>
    )
}
