import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import HomePage from './pages/HomePage'
import SearchPage from './pages/SearchPage'

export default function App() {
    return (
        <Routes>
            <Route element={<Layout />}>
                <Route path="/" element={<HomePage />} />
                <Route path="/search" element={<SearchPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
        </Routes>
    )
}
