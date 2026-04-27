import sys
import os

print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")

modules = [
    "llama_index.core",
    "llama_index.core.agent.workflow",
    "llama_index.core.workflow",
    "google.cloud.storage",
    "qdrant_client",
    "streamlit",
    "fastapi",
    "uvicorn"
]

for mod in modules:
    try:
        __import__(mod)
        print(f"[OK] {mod}")
    except ImportError as e:
        print(f"[FAIL] {mod}: {e}")
    except Exception as e:
        print(f"[ERROR] {mod}: {type(e).__name__}: {e}")

try:
    from llama_index.core import Settings
    print(f"[OK] Settings imported from llama_index.core")
except ImportError:
    print(f"[FAIL] Settings from llama_index.core")

try:
    import config
    print(f"[OK] config imported")
    print(f"config.Settings: {getattr(config, 'Settings', 'NOT FOUND')}")
except Exception as e:
    print(f"[FAIL] config import: {e}")
