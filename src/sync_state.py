"""
Sync State Management

Maintains a SQLite database to track which tasks have been synced
and their last known state, enabling change detection and preventing loops.
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional
import json

from .models import SyncRecord
from . import config


class SyncState:
    """
    Manages sync state persistence in a SQLite database.

    Schema:
    - sync_records: Maps sync IDs to system-specific IDs and tracks last sync state
    - sync_log: Audit log of all sync operations
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize sync state database.

        Args:
            db_path: Path to the SQLite database (env: SYNC_STATE_DB)
        """
        if db_path is None:
            db_path = config.SYNC_STATE_DB

        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self):
        """Create database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_records (
                    sync_id TEXT PRIMARY KEY,
                    apple_id TEXT,
                    supernote_id TEXT,
                    last_synced_hash TEXT,
                    last_sync_time INTEGER,
                    source_system TEXT DEFAULT 'both'
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    sync_id TEXT,
                    details TEXT
                )
            """)

            # Create indices for faster lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_apple_id
                ON sync_records(apple_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_supernote_id
                ON sync_records(supernote_id)
            """)

            conn.commit()

    def get_record(self, sync_id: str) -> Optional[SyncRecord]:
        """Get a sync record by sync ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM sync_records WHERE sync_id = ?",
                (sync_id,)
            )
            row = cursor.fetchone()
            if row:
                return SyncRecord(
                    sync_id=row["sync_id"],
                    apple_id=row["apple_id"],
                    supernote_id=row["supernote_id"],
                    last_synced_hash=row["last_synced_hash"] or "",
                    last_sync_time=row["last_sync_time"] or 0,
                    source_system=row["source_system"] or "both",
                )
        return None

    def get_by_apple_id(self, apple_id: str) -> Optional[SyncRecord]:
        """Find a sync record by Apple Reminders ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM sync_records WHERE apple_id = ?",
                (apple_id,)
            )
            row = cursor.fetchone()
            if row:
                return SyncRecord(
                    sync_id=row["sync_id"],
                    apple_id=row["apple_id"],
                    supernote_id=row["supernote_id"],
                    last_synced_hash=row["last_synced_hash"] or "",
                    last_sync_time=row["last_sync_time"] or 0,
                    source_system=row["source_system"] or "both",
                )
        return None

    def get_by_supernote_id(self, supernote_id: str) -> Optional[SyncRecord]:
        """Find a sync record by Supernote task ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM sync_records WHERE supernote_id = ?",
                (supernote_id,)
            )
            row = cursor.fetchone()
            if row:
                return SyncRecord(
                    sync_id=row["sync_id"],
                    apple_id=row["apple_id"],
                    supernote_id=row["supernote_id"],
                    last_synced_hash=row["last_synced_hash"] or "",
                    last_sync_time=row["last_sync_time"] or 0,
                    source_system=row["source_system"] or "both",
                )
        return None

    def get_all_records(self) -> list[SyncRecord]:
        """Get all sync records."""
        records = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM sync_records")
            for row in cursor:
                records.append(SyncRecord(
                    sync_id=row["sync_id"],
                    apple_id=row["apple_id"],
                    supernote_id=row["supernote_id"],
                    last_synced_hash=row["last_synced_hash"] or "",
                    last_sync_time=row["last_sync_time"] or 0,
                    source_system=row["source_system"] or "both",
                ))
        return records

    def upsert_record(self, record: SyncRecord):
        """Insert or update a sync record."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sync_records
                (sync_id, apple_id, supernote_id, last_synced_hash, last_sync_time, source_system)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                record.sync_id,
                record.apple_id,
                record.supernote_id,
                record.last_synced_hash,
                record.last_sync_time,
                record.source_system,
            ))
            conn.commit()

    def delete_record(self, sync_id: str):
        """Delete a sync record."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM sync_records WHERE sync_id = ?",
                (sync_id,)
            )
            conn.commit()

    def log_action(self, action: str, sync_id: Optional[str] = None, details: Optional[dict] = None):
        """Log a sync action for auditing."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO sync_log (timestamp, action, sync_id, details)
                VALUES (?, ?, ?, ?)
            """, (
                int(datetime.now().timestamp()),
                action,
                sync_id,
                json.dumps(details) if details else None,
            ))
            conn.commit()

    def get_recent_logs(self, limit: int = 100) -> list[dict]:
        """Get recent sync log entries."""
        logs = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM sync_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            for row in cursor:
                logs.append({
                    "id": row["id"],
                    "timestamp": datetime.fromtimestamp(row["timestamp"]),
                    "action": row["action"],
                    "sync_id": row["sync_id"],
                    "details": json.loads(row["details"]) if row["details"] else None,
                })
        return logs

    def clear_all(self):
        """Clear all sync records. Use with caution!"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM sync_records")
            conn.commit()

    def get_stats(self) -> dict:
        """Get sync state statistics."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM sync_records").fetchone()[0]
            apple_only = conn.execute(
                "SELECT COUNT(*) FROM sync_records WHERE apple_id IS NOT NULL AND supernote_id IS NULL"
            ).fetchone()[0]
            supernote_only = conn.execute(
                "SELECT COUNT(*) FROM sync_records WHERE supernote_id IS NOT NULL AND apple_id IS NULL"
            ).fetchone()[0]
            both = conn.execute(
                "SELECT COUNT(*) FROM sync_records WHERE apple_id IS NOT NULL AND supernote_id IS NOT NULL"
            ).fetchone()[0]

            return {
                "total_records": total,
                "apple_only": apple_only,
                "supernote_only": supernote_only,
                "synced_both": both,
            }
