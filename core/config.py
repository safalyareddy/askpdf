import os
import yaml
import logging
from typing import Dict, Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("documind.config")


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Loads application configuration with sensible defaults and environment overrides."""
    config: Dict[str, Any] = {
        "llm_provider": "ollama",
        "llm_model": "llama3",
        "llm_base_url": "http://localhost:11434",
        "llm_api_key": "",
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "ollama_base_url": "http://localhost:11434",
        "pdf_dir": "./data/",
        "chunk_size": 600,
        "chunk_overlap": 120,
        "persist_dir": "./db",
        "history_length": 5,
        "use_gpu": False,
        "max_upload_size_mb": 20,
        "ollama_timeout_seconds": 90,
        "ollama_num_ctx": 4096,
        "rate_limit_per_minute": 30
    }

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if loaded and isinstance(loaded, dict):
                    config.update(loaded)
        except Exception as e:
            logger.warning(f"Error loading {config_path}: {e}. Utilizing fallback defaults.")

    # Environment variable overrides
    if os.getenv("LLM_PROVIDER"):
        config["llm_provider"] = os.getenv("LLM_PROVIDER")
    if os.getenv("LLM_MODEL"):
        config["llm_model"] = os.getenv("LLM_MODEL")
    if os.getenv("LLM_BASE_URL"):
        config["llm_base_url"] = os.getenv("LLM_BASE_URL")
    if os.getenv("LLM_API_KEY"):
        config["llm_api_key"] = os.getenv("LLM_API_KEY")
    if os.getenv("EMBEDDING_MODEL"):
        config["embedding_model"] = os.getenv("EMBEDDING_MODEL")
    if os.getenv("OLLAMA_BASE_URL"):
        config["ollama_base_url"] = os.getenv("OLLAMA_BASE_URL")
    storage_dir = os.getenv("STORAGE_DIR", "").strip()
    if storage_dir:
        config["pdf_dir"] = os.path.join(storage_dir, "data")
        config["persist_dir"] = os.path.join(storage_dir, "db")
    if os.getenv("PDF_DIR"):
        config["pdf_dir"] = os.getenv("PDF_DIR")
    if os.getenv("PERSIST_DIR"):
        config["persist_dir"] = os.getenv("PERSIST_DIR")
    if os.getenv("MAX_UPLOAD_SIZE_MB"):
        try:
            config["max_upload_size_mb"] = int(os.getenv("MAX_UPLOAD_SIZE_MB", "20"))
        except ValueError:
            pass

    # Seamlessly adapt container paths and endpoints when running natively on host machine
    if str(config.get("pdf_dir", "")).startswith("/app") and not os.path.exists("/app"):
        config["pdf_dir"] = "./data/"
    if str(config.get("persist_dir", "")).startswith("/app") and not os.path.exists("/app"):
        config["persist_dir"] = "./db"
    if "host.docker.internal" in str(config.get("ollama_base_url", "")) and not os.path.exists("/.dockerenv"):
        config["ollama_base_url"] = config["ollama_base_url"].replace("host.docker.internal", "localhost")

    return config
