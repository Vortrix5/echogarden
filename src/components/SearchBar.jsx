import { useEffect, useRef } from 'react';

export default function SearchBar({ value, onChange, onSearch, loading }) {
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && value.trim()) {
      onSearch();
    }
  };

  return (
    <div className="search-bar">
      <svg className="search-icon-left" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="11" cy="11" r="8" />
        <path d="M21 21l-4.35-4.35" />
      </svg>
      <input
        ref={inputRef}
        type="text"
        placeholder="Search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      {value && (
        <button className="clear-btn" onClick={() => onChange('')}>
          <svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18">
            <circle cx="12" cy="12" r="10" opacity="0.3" />
            <path d="M15.5 8.5l-7 7M8.5 8.5l7 7" stroke="currentColor" strokeWidth="1.5" fill="none" />
          </svg>
        </button>
      )}
      <button
        className={`search-btn ${loading ? 'searching' : ''}`}
        onClick={onSearch}
        disabled={!value.trim() || loading}
      >
        {loading ? (
          <div className="btn-loader">
            <span></span><span></span><span></span>
          </div>
        ) : (
          <>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <circle cx="11" cy="11" r="7" />
              <path d="M20 20l-3.5-3.5" />
            </svg>
            Search
          </>
        )}
      </button>
    </div>
  );
}
