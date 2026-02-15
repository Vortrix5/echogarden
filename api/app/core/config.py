import os

# Storage
EG_DATA_DIR: str = os.environ.get("EG_DATA_DIR", "/data")
EG_DB_PATH: str = os.environ.get("EG_DB_PATH", "/data/sqlite/echogarden.db")
EG_MODELS_DIR: str = os.environ.get("EG_MODELS_DIR", "/data/models")
EG_THUMB_DIR: str = os.environ.get("EG_THUMB_DIR", "/data/thumbs")

# Services
QDRANT_URL: str = os.environ.get("QDRANT_URL", "http://qdrant:6333")
TIKA_URL: str = os.environ.get("TIKA_URL", "http://tika:9998")

# Local LLM
EG_OLLAMA_URL: str = os.environ.get("EG_OLLAMA_URL", "http://host.docker.internal:11434")
EG_OLLAMA_MODEL: str = os.environ.get("EG_OLLAMA_MODEL", "phi3:mini")
EG_OLLAMA_TIMEOUT: float = float(os.environ.get("EG_OLLAMA_TIMEOUT", "180"))

# Models. "stub" skips the model download and returns placeholder output.
EG_WHISPER_MODE: str = os.environ.get("EG_WHISPER_MODE", "local")
EG_WHISPER_MODEL: str = os.environ.get("EG_WHISPER_MODEL", "base")
EG_OPENCLIP_MODE: str = os.environ.get("EG_OPENCLIP_MODE", "local")
EG_TEXT_EMBED_MODEL: str = os.environ.get("EG_TEXT_EMBED_MODEL", "all-MiniLM-L6-v2")

# Mounts the /debug inspection endpoints, which expose raw tables without auth.
EG_DEBUG: bool = os.environ.get("EG_DEBUG", "").lower() in ("1", "true", "yes")

# Browser capture. Empty disables the /capture/browser endpoints.
EG_CAPTURE_API_KEY: str = os.environ.get("EG_CAPTURE_API_KEY", "")

# Folder capture
EG_WATCH_ROOTS: list[str] = [
    r.strip() for r in os.environ.get("EG_WATCH_ROOTS", "/host_watch").split(",") if r.strip()
]
EG_POLL_INTERVAL: float = float(os.environ.get("EG_POLL_INTERVAL", "2"))
# Larger files still get a blob and a placeholder card, but their content is not read.
EG_MAX_FILE_MB: float = float(os.environ.get("EG_MAX_FILE_MB", "20"))
EG_MAX_FILE_BYTES: int = int(EG_MAX_FILE_MB * 1024 * 1024)
TEXT_EXTENSIONS: frozenset[str] = frozenset({".txt", ".md", ".json", ".csv", ".log"})
