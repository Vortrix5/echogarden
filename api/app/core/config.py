import os

EG_DATA_DIR: str = os.environ.get("EG_DATA_DIR", "/data")
EG_DB_PATH: str = os.environ.get("EG_DB_PATH", "/data/sqlite/echogarden.db")
QDRANT_URL: str = os.environ.get("QDRANT_URL", "http://qdrant:6333")
