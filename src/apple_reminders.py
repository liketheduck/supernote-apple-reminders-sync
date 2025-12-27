"""
Apple Reminders Interface

Uses reminders-cli and reminder-helper (both Swift/EventKit) for all operations.

Swift tools are fast because they use native EventKit framework.

Tools used:
- reminders-cli: add, complete, uncomplete, delete, edit (title/notes), new-list
- reminder-helper: set-due-date, set-priority, move (custom Swift helper)
"""

import subprocess
import json
from datetime import datetime
from typing import Optional
from pathlib import Path

from .models import UnifiedTask
from . import config

# Path to Swift helper for due date, priority, move operations
SWIFT_HELPER = Path(__file__).resolve().parent.parent / "swift" / "reminder-helper"


def normalize_apple_id(apple_id: Optional[str]) -> Optional[str]:
    """
    Normalize Apple reminder ID to plain UUID format.

    Some sources return: x-apple-reminder://UUID
    reminders-cli returns: UUID
    We standardize on: UUID
    """
    if not apple_id:
        return None
    if apple_id.startswith("x-apple-reminder://"):
        return apple_id[len("x-apple-reminder://"):]
    return apple_id


class AppleReminders:
    """
    Interface to Apple Reminders using reminders-cli and reminder-helper (Swift).

    reminders-cli is used for reading and most write operations.
    reminder-helper (Swift) is used for due date, priority, and move operations.
    """

    def __init__(self, reminders_cli_path: Optional[str] = None):
        """
        Initialize the Apple Reminders interface.

        Args:
            reminders_cli_path: Path to reminders-cli binary (env: REMINDERS_CLI_PATH)
        """
        self.reminders_cli = reminders_cli_path or config.REMINDERS_CLI_PATH
        self._verify_reminders_cli()
        self._verify_swift_helper()

    def _verify_reminders_cli(self):
        """Verify reminders-cli is available."""
        import os
        if not os.path.exists(self.reminders_cli):
            raise FileNotFoundError(
                f"reminders-cli not found at {self.reminders_cli}. "
                "Please install from https://github.com/keith/reminders-cli "
                "or set REMINDERS_CLI_PATH environment variable."
            )

    def _verify_swift_helper(self):
        """Verify Swift helper is available."""
        import os
        if not os.path.exists(SWIFT_HELPER):
            raise FileNotFoundError(
                f"Swift helper not found at {SWIFT_HELPER}. "
                "Please compile it with: cd swift && swiftc -O -o reminder-helper reminder-helper.swift"
            )

    def _run_reminders_cli(self, *args: str) -> str:
        """Run reminders-cli and return output."""
        cmd = [self.reminders_cli] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout

    def _run_swift_helper(self, *args: str) -> None:
        """Run Swift helper for due date, priority, move operations."""
        cmd = [str(SWIFT_HELPER)] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Swift helper failed: {result.stderr}")

    def list_lists(self) -> list[str]:
        """Get all reminder list names."""
        output = self._run_reminders_cli("show-lists")
        return [line.strip() for line in output.strip().split("\n") if line.strip()]

    def get_all_reminders(self, include_completed: bool = True) -> list[UnifiedTask]:
        """
        Get all reminders from all lists.

        Returns:
            List of UnifiedTask objects
        """
        args = ["show-all", "--format", "json"]
        if include_completed:
            args.append("--include-completed")

        output = self._run_reminders_cli(*args)
        reminders = json.loads(output)

        return [self._reminder_to_task(r) for r in reminders]

    def get_reminders(self, list_name: str, include_completed: bool = True) -> list[UnifiedTask]:
        """
        Get reminders from a specific list.

        Args:
            list_name: Name of the reminder list
            include_completed: Include completed reminders

        Returns:
            List of UnifiedTask objects
        """
        args = ["show", list_name, "--format", "json"]
        if include_completed:
            args.append("--include-completed")

        try:
            output = self._run_reminders_cli(*args)
            reminders = json.loads(output)
            return [self._reminder_to_task(r) for r in reminders]
        except subprocess.CalledProcessError:
            return []

    def _reminder_to_task(self, reminder: dict) -> UnifiedTask:
        """Convert reminders-cli JSON to UnifiedTask."""
        # Parse dates
        due_date = None
        if reminder.get("dueDate"):
            due_date = datetime.fromisoformat(
                reminder["dueDate"].replace("Z", "+00:00")
            )

        created_at = None
        if reminder.get("creationDate"):
            created_at = datetime.fromisoformat(
                reminder["creationDate"].replace("Z", "+00:00")
            )

        modified_at = None
        if reminder.get("lastModified"):
            modified_at = datetime.fromisoformat(
                reminder["lastModified"].replace("Z", "+00:00")
            )

        completion_date = None
        if reminder.get("completionDate"):
            completion_date = datetime.fromisoformat(
                reminder["completionDate"].replace("Z", "+00:00")
            )

        # Extract sync ID from notes if present
        notes = reminder.get("notes", "") or ""
        sync_id = UnifiedTask.extract_sync_id(notes)
        clean_notes = UnifiedTask.strip_sync_metadata(notes)

        task = UnifiedTask(
            apple_id=reminder.get("externalId"),
            title=reminder.get("title", ""),
            notes=clean_notes,
            category=reminder.get("list", "Inbox"),
            completed=reminder.get("isCompleted", False),
            due_date=due_date,
            completion_date=completion_date,
            created_at=created_at,
            modified_at=modified_at,
            priority=UnifiedTask.map_priority_from_apple(reminder.get("priority", 0)),
            status="completed" if reminder.get("isCompleted") else "needsAction",
        )

        if sync_id:
            task.sync_id = sync_id

        return task

    def create_reminder(self, task: UnifiedTask) -> str:
        """
        Create a new reminder using reminders-cli.

        Args:
            task: UnifiedTask to create

        Returns:
            The created reminder's external ID
        """
        list_name = task.category or "Inbox"

        # Ensure list exists
        lists = self.list_lists()
        if list_name not in lists:
            self._run_reminders_cli("new-list", list_name)

        # Build reminders-cli add command
        args = ["add", list_name, task.title, "--format", "json"]

        # Add notes with sync ID
        notes = task.get_apple_notes()
        if notes:
            args.extend(["--notes", notes])

        # Add due date
        if task.due_date:
            args.extend(["--due-date", task.due_date.strftime("%Y-%m-%d %H:%M")])

        # Add priority (reminders-cli uses: none, low, medium, high)
        # Apple's numeric priority scale: 0=none, 1-4=high, 5=medium, 6-9=low
        priority = task.map_priority_to_apple()
        if priority > 0:
            if priority <= 4:
                args.extend(["--priority", "high"])   # 1-4 = high priority
            elif priority == 5:
                args.extend(["--priority", "medium"]) # 5 = medium priority
            else:
                args.extend(["--priority", "low"])    # 6-9 = low priority

        output = self._run_reminders_cli(*args)
        result = json.loads(output) if output.strip() else {}

        # Get the ID from the result
        apple_id = result.get("externalId", "")

        # Mark as completed if needed
        if task.completed and apple_id:
            self._run_reminders_cli("complete", list_name, apple_id)

        return normalize_apple_id(apple_id)

    def update_reminder(self, task: UnifiedTask):
        """
        Update an existing reminder.

        Uses reminders-cli for completion status and title/notes.
        Uses Swift helper for due date, priority, and move operations.

        Args:
            task: UnifiedTask with updates
        """
        if not task.apple_id:
            raise ValueError("Cannot update reminder without apple_id")

        # Get current reminder to find its list and current state
        all_reminders = self.get_all_reminders(include_completed=True)
        current = None
        for r in all_reminders:
            if r.apple_id == task.apple_id:
                current = r
                break

        if not current:
            raise ValueError(f"Reminder with ID {task.apple_id} not found")

        current_list = current.category

        # Update completion status first (most common operation) - FAST with reminders-cli
        if task.completed != current.completed:
            if task.completed:
                self._run_reminders_cli("complete", current_list, task.apple_id)
            else:
                self._run_reminders_cli("uncomplete", current_list, task.apple_id)

        # Update title and/or notes if changed - use reminders-cli edit
        title_changed = task.title != current.title
        notes = task.get_apple_notes()
        notes_changed = notes != (current.notes or "")

        if title_changed or notes_changed:
            args = ["edit", current_list, task.apple_id]
            if title_changed:
                args.append(task.title)
            if notes_changed:
                args.extend(["--notes", notes])
            self._run_reminders_cli(*args)

        # Update due date via Swift helper
        if task.due_date != current.due_date:
            date_str = task.due_date.isoformat() if task.due_date else "null"
            self._run_swift_helper("set-due-date", current_list, task.apple_id, date_str)

        # Update priority via Swift helper
        if task.priority != current.priority:
            self._run_swift_helper("set-priority", current_list, task.apple_id, str(task.map_priority_to_apple()))

        # Move to different list via Swift helper
        if task.category and task.category != current_list:
            lists = self.list_lists()
            if task.category not in lists:
                self._run_reminders_cli("new-list", task.category)
            self._run_swift_helper("move", current_list, task.apple_id, task.category)

    def delete_reminder(self, apple_id: str):
        """Delete a reminder by ID."""
        # Need to find the list first for reminders-cli
        all_reminders = self.get_all_reminders(include_completed=True)
        for r in all_reminders:
            if r.apple_id == apple_id:
                self._run_reminders_cli("delete", r.category, apple_id)
                return
        raise ValueError(f"Reminder with ID {apple_id} not found")

    def create_list(self, name: str) -> dict:
        """Create a new reminder list using reminders-cli."""
        self._run_reminders_cli("new-list", name)
        return {"name": name}

    def get_reminder_by_id(self, apple_id: str) -> Optional[UnifiedTask]:
        """Get a reminder by its external ID."""
        all_reminders = self.get_all_reminders(include_completed=True)
        for r in all_reminders:
            if r.apple_id == apple_id:
                return r
        return None

    def test_connection(self) -> bool:
        """Test connection to Apple Reminders."""
        try:
            self.list_lists()
            return True
        except Exception:
            return False
