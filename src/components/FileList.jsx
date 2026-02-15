import FileIcon from './FileIcon';

function formatSize(bytes) {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
}

function formatDate(dateStr) {
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function highlightMatch(text, query) {
  if (!query) return text;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark>{text.slice(idx, idx + query.length)}</mark>
      {text.slice(idx + query.length)}
    </>
  );
}

export default function FileList({ files, query, loading }) {
  if (loading) {
    return <div className="status-message">Searching...</div>;
  }

  if (files.length === 0) {
    return (
      <div className="status-message">
        {query ? 'No files found matching your search.' : 'Type to search files...'}
      </div>
    );
  }

  return (
    <div className="file-list">
      <div className="file-header">
        <span className="col-icon"></span>
        <span className="col-name">Name</span>
        <span className="col-path">Path</span>
        <span className="col-size">Size</span>
        <span className="col-date">Modified</span>
      </div>
      {files.map((file, i) => (
        <div key={i} className={`file-row ${file.isDirectory ? 'is-dir' : ''}`}>
          <span className="col-icon">
            <FileIcon extension={file.extension} isDirectory={file.isDirectory} />
          </span>
          <span className="col-name">{highlightMatch(file.name, query)}</span>
          <span className="col-path" title={file.path}>{file.path}</span>
          <span className="col-size">{file.isDirectory ? '—' : formatSize(file.size)}</span>
          <span className="col-date">{formatDate(file.modified)}</span>
        </div>
      ))}
    </div>
  );
}
