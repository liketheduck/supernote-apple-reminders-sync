"""
Data Models for Supernote-Apple Reminders Sync

Defines the UnifiedTask model and related data structures for
bidirectional sync between Supernote and Apple Reminders.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib
import json
import re
import uuid
import base64


@dataclass
class DocumentLink:
    """Represents a Supernote document link."""
    app_name: str  # Usually "note"
    file_id: str
    file_path: str
    page: int
    page_id: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "appName": self.app_name,
            "fileId": self.file_id,
            "filePath": self.file_path,
            "page": self.page,
            "pageId": self.page_id
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentLink":
        """Create from dictionary."""
        return cls(
            app_name=data.get("appName", "note"),
            file_id=data["fileId"],
            file_path=data["filePath"],
            page=data["page"],
            page_id=data["pageId"]
        )

    @classmethod
    def from_base64(cls, encoded: str) -> Optional["DocumentLink"]:
        """Decode from Base64-encoded JSON string."""
        if not encoded:
            return None
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
            data = json.loads(decoded)
            return cls.from_dict(data)
        except Exception:
            return None

    def to_base64(self) -> str:
        """Encode to Base64 JSON string for storage."""
        json_str = json.dumps(self.to_dict())
        return base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

    def to_readable_string(self) -> str:
        """Convert to human-readable string for Apple Reminders notes."""
        # Extract just the filename from the path
        filename = self.file_path.split("/")[-1]
        return f"📎 {filename} (page {self.page})"


@dataclass
class UnifiedTask:
    """
    A normalized task representation that works for both systems.

    This is the core data structure used for sync operations.
    """
    # Sync identification
    sync_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Core task data
    title: str = ""
    notes: str = ""
    category: str = "Inbox"
    completed: bool = False
    completion_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    priority: int = 0  # 0=none, 1=low, 5=medium, 9=high

    # Timestamps
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None

    # System-specific IDs
    supernote_id: Optional[str] = None
    apple_id: Optional[str] = None

    # Document links (Supernote-specific, must be preserved)
    document_link: Optional[DocumentLink] = None

    # Status for sync tracking
    status: str = "needsAction"  # "needsAction" or "completed"

    def __post_init__(self):
        """Ensure dates are datetime objects."""
        if isinstance(self.completion_date, str):
            self.completion_date = datetime.fromisoformat(self.completion_date.replace("Z", "+00:00"))
        if isinstance(self.due_date, str):
            self.due_date = datetime.fromisoformat(self.due_date.replace("Z", "+00:00"))
        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        if isinstance(self.modified_at, str):
            self.modified_at = datetime.fromisoformat(self.modified_at.replace("Z", "+00:00"))

    def content_hash(self) -> str:
        """
        Generate a hash of the task's content for change detection.

        Only includes fields that matter for sync (not IDs or timestamps).
        Excludes due_date as it causes timezone comparison issues and is handled separately.
        """
        content = {
            "title": self.title,
            "notes": self.notes,
            "category": self.category,
            "completed": self.completed,
            "priority": self.priority,
        }
        content_str = json.dumps(content, sort_keys=True)
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "sync_id": self.sync_id,
            "title": self.title,
            "notes": self.notes,
            "category": self.category,
            "completed": self.completed,
            "completion_date": self.completion_date.isoformat() if self.completion_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "priority": self.priority,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "supernote_id": self.supernote_id,
            "apple_id": self.apple_id,
            "document_link": self.document_link.to_dict() if self.document_link else None,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UnifiedTask":
        """Create from dictionary."""
        doc_link = None
        if data.get("document_link"):
            doc_link = DocumentLink.from_dict(data["document_link"])

        return cls(
            sync_id=data.get("sync_id", str(uuid.uuid4())),
            title=data.get("title", ""),
            notes=data.get("notes", ""),
            category=data.get("category", "Inbox"),
            completed=data.get("completed", False),
            completion_date=data.get("completion_date"),
            due_date=data.get("due_date"),
            priority=data.get("priority", 0),
            created_at=data.get("created_at"),
            modified_at=data.get("modified_at"),
            supernote_id=data.get("supernote_id"),
            apple_id=data.get("apple_id"),
            document_link=doc_link,
            status=data.get("status", "needsAction"),
        )

    def get_apple_notes(self) -> str:
        """
        Generate the notes field for Apple Reminders.

        Includes:
        - Original notes
        - Document link (readable format)

        Note: Sync matching is done via the database (apple_id <-> supernote_id),
        not via embedded IDs in notes, keeping Apple notes clean.
        """
        parts = []

        if self.notes:
            parts.append(self.notes)

        if self.document_link:
            parts.append(f"\n{self.document_link.to_readable_string()}")

        return "".join(parts).strip()

    @staticmethod
    def extract_sync_id(notes: str) -> Optional[str]:
        """Extract sync ID from Apple Reminders notes field."""
        if not notes:
            return None

        match = re.search(r"\[sync:([a-f0-9-]+)\]", notes)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def strip_sync_metadata(notes: str) -> str:
        """Remove sync metadata from notes, leaving only user content."""
        if not notes:
            return ""

        # Remove sync ID
        cleaned = re.sub(r"\n*\[sync:[a-f0-9-]+\]", "", notes)
        # Remove document link indicator (we'll reconstruct it from the actual link)
        cleaned = re.sub(r"\n*📎 [^\n]+", "", cleaned)
        return cleaned.strip()

    def map_priority_to_apple(self) -> int:
        """
        Map priority to Apple Reminders format.

        Apple uses: 0=none, 1-4=high, 5=medium, 6-9=low
        We normalize to: 0=none, 1=low, 5=medium, 9=high
        """
        if self.priority == 0:
            return 0
        elif self.priority <= 3:
            return 9  # Low -> Apple low
        elif self.priority <= 6:
            return 5  # Medium -> Apple medium
        else:
            return 1  # High -> Apple high

    @staticmethod
    def map_priority_from_apple(apple_priority: int) -> int:
        """Map Apple Reminders priority to our format."""
        if apple_priority == 0:
            return 0
        elif apple_priority >= 6:
            return 1  # Apple low -> our low
        elif apple_priority == 5:
            return 5  # Apple medium -> our medium
        else:
            return 9  # Apple high -> our high


@dataclass
class SyncRecord:
    """
    Tracks the sync state of a task.

    Stored in sync_state.db to detect changes and prevent loops.
    """
    sync_id: str
    apple_id: Optional[str] = None
    supernote_id: Optional[str] = None
    last_synced_hash: str = ""
    last_sync_time: int = 0  # Unix timestamp
    source_system: str = "both"  # 'apple', 'supernote', or 'both'

    def to_dict(self) -> dict:
        return {
            "sync_id": self.sync_id,
            "apple_id": self.apple_id,
            "supernote_id": self.supernote_id,
            "last_synced_hash": self.last_synced_hash,
            "last_sync_time": self.last_sync_time,
            "source_system": self.source_system,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SyncRecord":
        return cls(
            sync_id=data["sync_id"],
            apple_id=data.get("apple_id"),
            supernote_id=data.get("supernote_id"),
            last_synced_hash=data.get("last_synced_hash", ""),
            last_sync_time=data.get("last_sync_time", 0),
            source_system=data.get("source_system", "both"),
        )


@dataclass
class CategoryMapping:
    """Maps category names between Apple Reminders and Supernote."""
    apple_name: str
    supernote_name: str

    def to_dict(self) -> dict:
        return {"apple": self.apple_name, "supernote": self.supernote_name}

    @classmethod
    def from_dict(cls, data: dict) -> "CategoryMapping":
        return cls(apple_name=data["apple"], supernote_name=data["supernote"])


@dataclass
class SyncAction:
    """Represents a single sync action to be performed."""
    action: str  # 'create', 'update', 'delete'
    target_system: str  # 'apple', 'supernote'
    task: UnifiedTask
    reason: str = ""

    def __str__(self) -> str:
        return f"{self.action} in {self.target_system}: {self.task.title} ({self.reason})"


@dataclass
class SyncResult:
    """Summary of a sync operation."""
    started_at: datetime
    completed_at: Optional[datetime] = None
    apple_to_supernote_created: int = 0
    apple_to_supernote_updated: int = 0
    apple_to_supernote_deleted: int = 0
    supernote_to_apple_created: int = 0
    supernote_to_apple_updated: int = 0
    supernote_to_apple_deleted: int = 0
    conflicts_resolved: int = 0
    no_change: int = 0
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "apple_to_supernote": {
                "created": self.apple_to_supernote_created,
                "updated": self.apple_to_supernote_updated,
                "deleted": self.apple_to_supernote_deleted,
            },
            "supernote_to_apple": {
                "created": self.supernote_to_apple_created,
                "updated": self.supernote_to_apple_updated,
                "deleted": self.supernote_to_apple_deleted,
            },
            "conflicts_resolved": self.conflicts_resolved,
            "no_change": self.no_change,
            "errors": self.errors,
        }

    def summary(self) -> str:
        """Generate a human-readable summary."""
        lines = [
            f"Sync completed at {self.completed_at}",
            f"Apple → Supernote: {self.apple_to_supernote_created} created, "
            f"{self.apple_to_supernote_updated} updated, {self.apple_to_supernote_deleted} deleted",
            f"Supernote → Apple: {self.supernote_to_apple_created} created, "
            f"{self.supernote_to_apple_updated} updated, {self.supernote_to_apple_deleted} deleted",
            f"Conflicts resolved: {self.conflicts_resolved}",
            f"No-op (unchanged): {self.no_change}",
        ]
        if self.errors:
            lines.append(f"Errors: {len(self.errors)}")
        return "\n".join(lines)
