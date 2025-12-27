"""
Configuration Management

Centralizes all configurable settings with environment variable overrides.
"""

import os
from pathlib import Path
from typing import Optional

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # dotenv not installed, rely on environment variables


def _get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def get_env(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """Get environment variable with optional default."""
    value = os.environ.get(key, default)
    if required and not value:
        raise ValueError(
            f"Required environment variable {key} is not set. "
            f"Set it with: export {key}='your-value'"
        )
    return value


# =============================================================================
# Database Configuration
# =============================================================================

# Connection mode: "docker" (docker exec) or "tcp" (direct connection)
SUPERNOTE_DB_MODE = get_env("SUPERNOTE_DB_MODE", "docker")

# Docker container name running MariaDB (only used if mode=docker)
SUPERNOTE_DOCKER_CONTAINER = get_env("SUPERNOTE_DOCKER_CONTAINER", "supernote-mariadb")

# Database host (only used if mode=tcp)
SUPERNOTE_DB_HOST = get_env("SUPERNOTE_DB_HOST", "localhost")

# Database port (only used if mode=tcp)
SUPERNOTE_DB_PORT = int(get_env("SUPERNOTE_DB_PORT", "3306"))

# Database name
SUPERNOTE_DB_NAME = get_env("SUPERNOTE_DB_NAME", "supernotedb")

# Database user
SUPERNOTE_DB_USER = get_env("SUPERNOTE_DB_USER", "supernote")

# Database password (required, no default for security)
def get_db_password() -> str:
    """Get database password from environment."""
    return get_env("SUPERNOTE_DB_PASSWORD", required=True)


# =============================================================================
# Apple Reminders Configuration
# =============================================================================

# Path to reminders-cli binary
REMINDERS_CLI_PATH = os.path.expanduser(
    get_env("REMINDERS_CLI_PATH", "~/.local/bin/reminders")
)


# =============================================================================
# Data Paths
# =============================================================================

# Project root for relative paths
PROJECT_ROOT = _get_project_root()

# Sync state database path
SYNC_STATE_DB = Path(
    get_env("SYNC_STATE_DB", str(PROJECT_ROOT / "sync_state.db"))
)

# Snapshots directory
SNAPSHOTS_DIR = Path(
    get_env("SNAPSHOTS_DIR", str(PROJECT_ROOT / "snapshots"))
)

# Logs directory
LOGS_DIR = Path(
    get_env("LOGS_DIR", str(PROJECT_ROOT / "logs"))
)


# =============================================================================
# Sync Configuration
# =============================================================================

# Conflict resolution: "prefer_recent" or "prefer_apple" or "prefer_supernote"
CONFLICT_RESOLUTION = get_env("SYNC_CONFLICT_RESOLUTION", "prefer_recent")

# Time window (seconds) for considering changes as simultaneous
CONFLICT_WINDOW_SECONDS = int(get_env("SYNC_CONFLICT_WINDOW", "60"))

# Whether to sync completed tasks
SYNC_COMPLETED_TASKS = get_env("SYNC_COMPLETED_TASKS", "true").lower() == "true"


# =============================================================================
# Helper to print current configuration
# =============================================================================

def print_config():
    """Print current configuration (for debugging)."""
    print("Current Configuration:")
    print(f"  SUPERNOTE_DB_MODE: {SUPERNOTE_DB_MODE}")
    if SUPERNOTE_DB_MODE == "docker":
        print(f"  SUPERNOTE_DOCKER_CONTAINER: {SUPERNOTE_DOCKER_CONTAINER}")
    else:
        print(f"  SUPERNOTE_DB_HOST: {SUPERNOTE_DB_HOST}")
        print(f"  SUPERNOTE_DB_PORT: {SUPERNOTE_DB_PORT}")
    print(f"  SUPERNOTE_DB_NAME: {SUPERNOTE_DB_NAME}")
    print(f"  SUPERNOTE_DB_USER: {SUPERNOTE_DB_USER}")
    print(f"  SUPERNOTE_DB_PASSWORD: {'*' * 8} (set)" if os.environ.get("SUPERNOTE_DB_PASSWORD") else "  SUPERNOTE_DB_PASSWORD: NOT SET")
    print(f"  REMINDERS_CLI_PATH: {REMINDERS_CLI_PATH}")
    print(f"  SYNC_STATE_DB: {SYNC_STATE_DB}")
    print(f"  SNAPSHOTS_DIR: {SNAPSHOTS_DIR}")
    print(f"  LOGS_DIR: {LOGS_DIR}")
    print(f"  CONFLICT_RESOLUTION: {CONFLICT_RESOLUTION}")
    print(f"  SYNC_COMPLETED_TASKS: {SYNC_COMPLETED_TASKS}")
