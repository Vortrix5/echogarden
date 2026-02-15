import { useState, useCallback } from 'react';
import SearchBar from './components/SearchBar';
import SearchResults from './components/SearchResults';
import GraphView from './components/GraphView';
import MemoryGraph3D from './components/MemoryGraph3D';
import './App.css';

function App() {
  const [query, setQuery] = useState('');
  const [topMatches, setTopMatches] = useState([]);
  const [rest, setRest] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [viewMode, setViewMode] = useState('demo'); // Default to demo as requested

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const res = await fetch(
        `http://localhost:3001/api/files?q=${encodeURIComponent(query)}`
      );
      const data = await res.json();
      setTopMatches(data.topMatches);
      setRest(data.rest);
    } catch (err) {
      console.error('Failed to fetch files:', err);
      setTopMatches([]);
      setRest([]);
    } finally {
      setLoading(false);
    }
  }, [query]);

  const handleClear = (val) => {
    setQuery(val);
    if (!val) {
      setTopMatches([]);
      setRest([]);
      setSearched(false);
    }
  };

  // Memory Graph Demo View
  if (viewMode === 'demo') {
    return (
      <div style={{ width: '100vw', height: '100vh', position: 'relative' }}>
        <MemoryGraph3D onBack={() => setViewMode('search')} />
        {/* Toggle back to search found in generic onBack or a specific button */}
        <button
          onClick={() => setViewMode('search')}
          style={{
            position: 'absolute', bottom: 20, left: 20, zIndex: 50,
            background: '#334155', color: 'white', border: 'none',
            padding: '8px 16px', borderRadius: '4px', cursor: 'pointer'
          }}
        >
          Switch to File Search
        </button>
      </div>
    );
  }

  // Graph view (File Search specific)
  // Now using MemoryGraph3D for selected files as well
  if (selectedFile) {
    return <MemoryGraph3D file={selectedFile} onBack={() => setSelectedFile(null)} />;
  }

  // Search view
  const hasResults = searched && (topMatches.length > 0 || rest.length > 0 || loading);

  return (
    <div className="spotlight-wrapper">
      <button
        onClick={() => setViewMode('demo')}
        style={{
          position: 'absolute', top: 20, right: 20, zIndex: 100,
          background: 'rgba(255,255,255,0.1)', color: 'white', border: 'none',
          padding: '8px 12px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem'
        }}
      >
        View 3D Memory Demo
      </button>

      <div className={`spotlight-container ${hasResults ? 'has-results' : ''}`}>
        <SearchBar
          value={query}
          onChange={handleClear}
          onSearch={handleSearch}
          loading={loading}
        />
        {searched && (
          <SearchResults
            topMatches={topMatches}
            rest={rest}
            query={query}
            loading={loading}
            onFileClick={setSelectedFile}
          />
        )}
      </div>
    </div>
  );
}

export default App;
