const categoryIcons = {
  image: '🖼️',
  video: '🎬',
  audio: '🎵',
  document: '📄',
  code: '💻',
  data: '📊',
  archive: '📦',
  folder: '📁',
  other: '📎',
};

const categoryColors = {
  image: '#ff6b9d',
  video: '#c084fc',
  audio: '#f97316',
  document: '#3b82f6',
  code: '#10b981',
  data: '#eab308',
  archive: '#6366f1',
  folder: '#06b6d4',
  other: '#94a3b8',
};

function formatSize(bytes) {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
}

export default function SearchResults({ topMatches, rest, query, loading, onFileClick }) {
  if (loading) {
    return (
      <div className="results-panel">
        <div className="results-loading">
          <div className="loading-dots">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>
    );
  }

  if (topMatches.length === 0 && rest.length === 0) {
    return (
      <div className="results-panel">
        <div className="no-results">No results found</div>
      </div>
    );
  }

  return (
    <div className="results-panel">
      {/* Best Matches */}
      {topMatches.length > 0 && (
        <div className="result-section">
          <div className="section-label best-label">
            <span>BEST MATCHES</span>
            <span className="match-count">{topMatches.length}</span>
          </div>
          {topMatches.map((file, i) => (
            <ResultCard file={file} key={`top-${i}`} rank={i + 1} isBest onClick={() => onFileClick?.(file)} />
          ))}
        </div>
      )}

      {/* All Other Files */}
      {rest.length > 0 && (
        <div className="result-section">
          <div className="section-label">
            <span>ALL FILES</span>
            <span className="match-count">{rest.length}</span>
          </div>
          <div className="all-files-list">
            {rest.map((file, i) => (
              <ResultCard file={file} key={`rest-${i}`} onClick={() => onFileClick?.(file)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ResultCard({ file, rank, isBest, onClick }) {
  const color = categoryColors[file.category] || categoryColors.other;
  const icon = categoryIcons[file.category] || categoryIcons.other;

  return (
    <div className={`result-card ${isBest ? 'best-match' : ''}`} onClick={onClick}>
      {isBest && <div className="rank-badge">#{rank}</div>}
      <div className="result-icon" style={{ backgroundColor: color + '22', color }}>
        <span>{icon}</span>
      </div>
      <div className="result-info">
        <div className="result-name">{file.name}</div>
        <div className="result-description">{file.description}</div>
        {isBest && (
          <div className="result-meta">
            <span className="result-category-badge" style={{ backgroundColor: color + '22', color }}>
              {file.category}
            </span>
            <span className="result-size">{file.isDirectory ? 'Folder' : formatSize(file.size)}</span>
            <span className="result-path" title={file.path}>{file.path}</span>
          </div>
        )}
      </div>
      {!isBest && (
        <span className="result-size-inline">{file.isDirectory ? 'Folder' : formatSize(file.size)}</span>
      )}
    </div>
  );
}
