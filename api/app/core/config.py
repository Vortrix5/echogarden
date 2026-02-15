import os

EG_DATA_DIR: str = os.environ.get("EG_DATA_DIR", "/data")
EG_DB_PATH: str = os.environ.get("EG_DB_PATH", "/data/sqlite/echogarden.db")
QDRANT_URL: str = os.environ.get("QDRANT_URL", "http://qdrant:6333")

# Phase 4
TIKA_URL: str = os.environ.get("TIKA_URL", "http://tika:9998")
EG_MODELS_DIR: str = os.environ.get("EG_MODELS_DIR", "/data/models")
EG_WHISPER_MODE: str = os.environ.get("EG_WHISPER_MODE", "local")
EG_OPENCLIP_MODE: str = os.environ.get("EG_OPENCLIP_MODE", "local")
EG_CAPTURE_API_KEY: str = os.environ.get("EG_CAPTURE_API_KEY", "")

# Phase 6 — Local LLM (Ollama)
EG_OLLAMA_URL: str = os.environ.get("EG_OLLAMA_URL", "http://host.docker.internal:11434")
EG_OLLAMA_MODEL: str = os.environ.get("EG_OLLAMA_MODEL", "phi3:mini")
