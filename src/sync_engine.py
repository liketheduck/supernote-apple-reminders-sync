"""
Sync Engine

Core bidirectional sync logic with anti-loop architecture.
Handles change detection, conflict resolution, and sync execution.
"""

from datetime import datetime, timedelta
from typing import Optional
import logging
import uuid

from .models import UnifiedTask, SyncRecord, SyncAction, SyncResult

# Only sync completed Apple tasks if completed within this many days
COMPLETED_TASK_MAX_AGE_DAYS = 180  # 6 months

# Deduplicate repeating tasks - only sync one instance per title
DEDUPE_REPEATING_TASKS = True
from .sync_state import SyncState
from .supernote_db import SupernoteDB
from .apple_reminders import AppleReminders, normalize_apple_id


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class SyncEngine:
    """
    Bidirectional sync engine between Supernote and Apple Reminders.

    Key features:
    - Content-hash based change detection (prevents loops)
    - Conflict resolution using modification timestamps
    - Document link preservation
    - Dry-run mode for previewing changes
    """

    def __init__(
        self,
        supernote: Optional[SupernoteDB] = None,
        apple: Optional[AppleReminders] = None,
        sync_state: Optional[SyncState] = None
    ):
        """
        Initialize the sync engine.

        Args:
            supernote: SupernoteDB instance (creates default if None)
            apple: AppleReminders instance (creates default if None)
            sync_state: SyncState instance (creates default if None)
        """
        self.supernote = supernote or SupernoteDB()
        self.apple = apple or AppleReminders()
        self.sync_state = sync_state or SyncState()

    def run_sync(self, dry_run: bool = False) -> SyncResult:
        """
        Execute a full bidirectional sync.

        Args:
            dry_run: If True, only show what would be done without making changes

        Returns:
            SyncResult with summary of operations
        """
        result = SyncResult(started_at=datetime.now())

        if dry_run:
            logger.info("=== DRY RUN MODE ===")

        try:
            # Sync categories first (handles renames)
            logger.info("Syncing categories...")
            category_changes = self._sync_categories(dry_run)
            if category_changes:
                for change in category_changes:
                    logger.info(f"  {change}")

            # Load all tasks from both systems
            logger.info("Loading tasks from Supernote...")
            supernote_tasks = self.supernote.list_tasks(include_completed=True)
            logger.info(f"  Found {len(supernote_tasks)} Supernote tasks")

            logger.info("Loading tasks from Apple Reminders...")
            apple_tasks_raw = self.apple.get_all_reminders(include_completed=True)
            logger.info(f"  Found {len(apple_tasks_raw)} Apple reminders")

            # Deduplicate repeating tasks (same title = keep latest instance)
            apple_tasks = self._dedupe_apple_tasks(apple_tasks_raw)

            # Index tasks by their system IDs
            supernote_by_id = self._index_by_system_id(supernote_tasks, "supernote")
            apple_by_id = self._index_by_system_id(apple_tasks, "apple")

            # Get all sync records
            sync_records = {r.sync_id: r for r in self.sync_state.get_all_records()}

            # Detect and apply changes
            actions = self._detect_changes(
                supernote_tasks,
                apple_tasks,
                supernote_by_id,
                apple_by_id,
                sync_records
            )

            logger.info(f"Detected {len(actions)} sync actions")

            # Execute actions
            for action in actions:
                if dry_run:
                    logger.info(f"  [DRY RUN] {action}")
                else:
                    self._execute_action(action, result)

            # Mark sync complete
            result.completed_at = datetime.now()

            if not dry_run:
                self.sync_state.log_action("sync_complete", details=result.to_dict())

            logger.info("\n" + result.summary())

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            result.errors.append(str(e))
            result.completed_at = datetime.now()

        return result

    def _sync_categories(self, dry_run: bool = False) -> list[str]:
        """
        Sync categories/lists between systems, detecting and propagating renames.

        Returns:
            List of change descriptions for logging
        """
        changes = []

        # Get current categories from both systems
        supernote_cats = {c["id"]: c["name"] for c in self.supernote.list_categories_with_ids()}
        apple_cats = {c["id"]: c["name"] for c in self.apple.list_lists_with_ids()}

        # Get stored category mappings
        stored_mappings = self.sync_state.get_all_categories()
        stored_by_supernote = {m["supernote_id"]: m for m in stored_mappings}
        stored_by_apple = {m["apple_id"]: m for m in stored_mappings}

        # Detect renames on Supernote side
        for sn_id, sn_name in supernote_cats.items():
            if sn_id in stored_by_supernote:
                mapping = stored_by_supernote[sn_id]
                old_name = mapping["name"]
                apple_id = mapping["apple_id"]

                if sn_name != old_name:
                    # Rename detected on Supernote
                    changes.append(f"Supernote renamed '{old_name}' → '{sn_name}'")

                    # Propagate to Apple if the old list exists there
                    if apple_id and apple_id in apple_cats:
                        apple_current_name = apple_cats[apple_id]
                        if apple_current_name == old_name:
                            if not dry_run:
                                self.apple.rename_list(old_name, sn_name)
                                self.sync_state.update_category_name(sn_id, apple_id, sn_name)
                            changes.append(f"  → Renamed Apple list '{old_name}' → '{sn_name}'")
                        else:
                            # Apple was also renamed - use most recent? For now, Supernote wins
                            if not dry_run:
                                self.apple.rename_list(apple_current_name, sn_name)
                                self.sync_state.update_category_name(sn_id, apple_id, sn_name)
                            changes.append(f"  → Renamed Apple list '{apple_current_name}' → '{sn_name}' (conflict)")
                    else:
                        # No Apple list linked yet - update mapping name
                        if not dry_run:
                            self.sync_state.update_category_name(sn_id, apple_id or "", sn_name)

        # Detect renames on Apple side
        for apple_id, apple_name in apple_cats.items():
            if apple_id in stored_by_apple:
                mapping = stored_by_apple[apple_id]
                old_name = mapping["name"]
                sn_id = mapping["supernote_id"]

                if apple_name != old_name and sn_id not in supernote_cats:
                    # Rename detected on Apple (and not already handled above)
                    changes.append(f"Apple renamed '{old_name}' → '{apple_name}'")

                    # Propagate to Supernote if the old category exists there
                    if sn_id and sn_id in supernote_cats:
                        sn_current_name = supernote_cats[sn_id]
                        if sn_current_name == old_name:
                            if not dry_run:
                                self.supernote.rename_category(sn_id, apple_name)
                                self.sync_state.update_category_name(sn_id, apple_id, apple_name)
                            changes.append(f"  → Renamed Supernote category '{old_name}' → '{apple_name}'")
                    else:
                        # No Supernote category linked yet - update mapping name
                        if not dry_run:
                            self.sync_state.update_category_name(sn_id or "", apple_id, apple_name)

        # Match new categories by name and store mappings
        for sn_id, sn_name in supernote_cats.items():
            if sn_id not in stored_by_supernote:
                # New Supernote category - find or create Apple match
                apple_match = None
                for apple_id, apple_name in apple_cats.items():
                    if apple_name.lower() == sn_name.lower() and apple_id not in stored_by_apple:
                        apple_match = apple_id
                        break

                if apple_match:
                    if not dry_run:
                        self.sync_state.upsert_category(sn_id, apple_match, sn_name)
                    changes.append(f"Linked category '{sn_name}' (Supernote ↔ Apple)")
                else:
                    # Create on Apple side
                    if not dry_run:
                        self.apple._run_reminders_cli("new-list", sn_name)
                        # Re-fetch to get the new ID
                        new_apple_cats = {c["id"]: c["name"] for c in self.apple.list_lists_with_ids()}
                        for aid, aname in new_apple_cats.items():
                            if aname == sn_name and aid not in stored_by_apple:
                                self.sync_state.upsert_category(sn_id, aid, sn_name)
                                break
                    changes.append(f"Created Apple list '{sn_name}' from Supernote")

        for apple_id, apple_name in apple_cats.items():
            if apple_id not in stored_by_apple:
                # Check if already matched above
                already_matched = any(
                    m.get("apple_id") == apple_id
                    for m in self.sync_state.get_all_categories()
                ) if not dry_run else False

                if not already_matched:
                    # New Apple category - find or create Supernote match
                    sn_match = None
                    for sn_id, sn_name in supernote_cats.items():
                        if sn_name.lower() == apple_name.lower():
                            # Check if already stored
                            existing = self.sync_state.get_category_by_supernote_id(sn_id) if not dry_run else None
                            if not existing:
                                sn_match = sn_id
                                break

                    if sn_match:
                        if not dry_run:
                            self.sync_state.upsert_category(sn_match, apple_id, apple_name)
                        # Already logged above if it was a new link
                    else:
                        # Create on Supernote side
                        if not dry_run:
                            new_sn_id = self.supernote.create_category(apple_name)
                            self.sync_state.upsert_category(new_sn_id, apple_id, apple_name)
                        changes.append(f"Created Supernote category '{apple_name}' from Apple")

        return changes

    def _dedupe_apple_tasks(self, tasks: list[UnifiedTask]) -> list[UnifiedTask]:
        """
        Deduplicate Apple tasks with the same title (repeating reminders).

        For tasks with identical titles, keep only the most relevant one:
        - Prefer incomplete over completed
        - Prefer most recent due date
        - Prefer most recent modification date

        This prevents syncing 9 copies of "Bread" to Supernote.
        """
        if not DEDUPE_REPEATING_TASKS:
            return tasks

        # Group by title
        by_title: dict[str, list[UnifiedTask]] = {}
        for task in tasks:
            title = task.title.strip()
            if title not in by_title:
                by_title[title] = []
            by_title[title].append(task)

        # Select best instance for each title
        deduped = []
        duplicates_removed = 0

        for title, group in by_title.items():
            if len(group) == 1:
                deduped.append(group[0])
            else:
                # Select the best instance using priority order:
                # 1. Prefer incomplete tasks over completed
                # 2. Among same-status tasks, prefer the one with the latest date
                #    (using due_date, or modified_at as fallback)
                def sort_key(t):
                    # Lower rank = higher priority (sorts first in ascending order)
                    # Incomplete (0) sorts before Completed (1)
                    completed_rank = 0 if not t.completed else 1

                    # For date: we want later dates to have higher priority
                    # Use negative timestamp so larger (later) dates sort first
                    date = t.due_date or t.modified_at
                    if date:
                        if hasattr(date, 'replace'):
                            date = date.replace(tzinfo=None)
                        date_key = -date.timestamp()
                    else:
                        # No date = lowest priority (large positive sorts last)
                        date_key = float('inf')

                    return (completed_rank, date_key)

                group.sort(key=sort_key)
                # First item is the best: incomplete with latest date,
                # or if all completed, the one with latest date
                best = group[0]
                deduped.append(best)
                duplicates_removed += len(group) - 1

        if duplicates_removed > 0:
            logger.info(f"  Deduped {duplicates_removed} repeating task instances")

        return deduped

    def _should_skip_old_completed_task(
        self,
        task: UnifiedTask,
        has_sync_record: bool
    ) -> bool:
        """
        Check if a completed Apple task should be skipped due to age.

        We skip completed tasks older than COMPLETED_TASK_MAX_AGE_DAYS
        UNLESS they already have a sync record (already linked to Supernote).

        This prevents importing years of old completed reminders.
        """
        if not task.completed:
            return False  # Not completed, don't skip

        if has_sync_record:
            return False  # Already linked, don't skip

        # Check completion date age
        if task.completion_date:
            cutoff = datetime.now(task.completion_date.tzinfo) - timedelta(days=COMPLETED_TASK_MAX_AGE_DAYS)
            if task.completion_date < cutoff:
                return True  # Too old, skip

        return False

    def _index_by_system_id(
        self,
        tasks: list[UnifiedTask],
        source: str
    ) -> dict[str, UnifiedTask]:
        """
        Index tasks by their system-specific ID (apple_id or supernote_id).

        Also looks up sync records to associate sync_ids for matched tasks.
        """
        indexed = {}

        for task in tasks:
            if source == "supernote" and task.supernote_id:
                # Look up by supernote_id to find linked apple task
                record = self.sync_state.get_by_supernote_id(task.supernote_id)
                if record:
                    task.sync_id = record.sync_id
                indexed[task.supernote_id] = task

            elif source == "apple" and task.apple_id:
                # Normalize apple_id for consistent lookup
                normalized_id = normalize_apple_id(task.apple_id)
                # Look up by apple_id to find linked supernote task
                record = self.sync_state.get_by_apple_id(normalized_id)
                if record:
                    task.sync_id = record.sync_id
                indexed[normalized_id] = task

        return indexed

    def _match_by_title(
        self,
        supernote_tasks: list[UnifiedTask],
        apple_tasks: list[UnifiedTask]
    ) -> dict[str, str]:
        """
        Match tasks by title when sync_ids don't match.
        Returns mapping of supernote_id -> apple_id for matched tasks.
        """
        matches = {}

        # Build title index for Apple tasks
        apple_by_title = {}
        for task in apple_tasks:
            title = task.title.strip().lower()
            if title not in apple_by_title:
                apple_by_title[title] = []
            apple_by_title[title].append(task)

        # Try to match Supernote tasks by title
        for sn_task in supernote_tasks:
            title = sn_task.title.strip().lower()
            if title in apple_by_title and len(apple_by_title[title]) == 1:
                # Unique title match
                apple_task = apple_by_title[title][0]
                matches[sn_task.supernote_id] = apple_task.apple_id

        return matches

    def _detect_changes(
        self,
        supernote_tasks: list[UnifiedTask],
        apple_tasks: list[UnifiedTask],
        supernote_by_id: dict[str, UnifiedTask],
        apple_by_id: dict[str, UnifiedTask],
        sync_records: dict[str, SyncRecord]
    ) -> list[SyncAction]:
        """
        Detect all required sync actions using database-based matching.

        Matching strategy:
        1. Use sync_state database to find existing apple_id <-> supernote_id pairings
        2. For unmatched tasks, use title-based matching to link them
        3. For completely new tasks, create them in the other system

        Logic after matching:
        - Matched pairs: compare hashes, resolve conflicts if different
        - Unmatched Apple tasks: check if previously synced (deleted from Supernote) or new
        - Unmatched Supernote tasks: check if previously synced (deleted from Apple) or new
        """
        actions = []

        # Build lookup of sync records by system ID
        records_by_apple_id = {}
        records_by_supernote_id = {}
        for record in sync_records.values():
            if record.apple_id:
                records_by_apple_id[record.apple_id] = record
            if record.supernote_id:
                records_by_supernote_id[record.supernote_id] = record

        # Track matched tasks
        matched_apple_ids = set()
        matched_supernote_ids = set()

        # Step 1: Match via existing sync records (database)
        for record in sync_records.values():
            apple_task = apple_by_id.get(record.apple_id) if record.apple_id else None
            supernote_task = supernote_by_id.get(record.supernote_id) if record.supernote_id else None

            if apple_task and supernote_task:
                # Both exist - check for changes
                apple_task.sync_id = record.sync_id
                supernote_task.sync_id = record.sync_id
                matched_apple_ids.add(record.apple_id)
                matched_supernote_ids.add(record.supernote_id)

                action = self._resolve_conflict(apple_task, supernote_task, record)
                if action:
                    actions.append(action)

            elif apple_task and not supernote_task:
                # Apple exists but Supernote was deleted
                matched_apple_ids.add(record.apple_id)
                actions.append(SyncAction(
                    action="delete",
                    target_system="apple",
                    task=apple_task,
                    reason="Deleted from Supernote"
                ))

            elif supernote_task and not apple_task:
                # Supernote exists but Apple was deleted
                matched_supernote_ids.add(record.supernote_id)
                actions.append(SyncAction(
                    action="delete",
                    target_system="supernote",
                    task=supernote_task,
                    reason="Deleted from Apple Reminders"
                ))

        # Step 2: Title-based matching for unmatched tasks (initial sync)
        unmatched_apple = [t for t in apple_tasks if t.apple_id not in matched_apple_ids]
        unmatched_supernote = [t for t in supernote_tasks if t.supernote_id not in matched_supernote_ids]

        title_matches = self._match_by_title(unmatched_supernote, unmatched_apple)

        for supernote_id, apple_id in title_matches.items():
            supernote_task = supernote_by_id[supernote_id]
            apple_task = apple_by_id[apple_id]

            # Generate a new sync_id for this pairing
            sync_id = str(uuid.uuid4())
            supernote_task.sync_id = sync_id
            apple_task.sync_id = sync_id

            matched_apple_ids.add(apple_id)
            matched_supernote_ids.add(supernote_id)

            # Check for changes (use empty record since newly matched)
            action = self._resolve_conflict(apple_task, supernote_task, None)
            if action:
                actions.append(action)
            else:
                # Even if no action needed, create sync record for this pairing
                record = SyncRecord(
                    sync_id=sync_id,
                    apple_id=apple_id,
                    supernote_id=supernote_id,
                    last_synced_hash=supernote_task.content_hash(),
                    last_sync_time=int(datetime.now().timestamp()),
                    source_system="both"
                )
                self.sync_state.upsert_record(record)
                logger.info(f"  Linked by title: '{supernote_task.title}'")

        # Step 3: Remaining unmatched tasks are new
        skipped_old_completed = 0
        for task in apple_tasks:
            if task.apple_id not in matched_apple_ids:
                # Skip old completed tasks (no sync record = not linked)
                if self._should_skip_old_completed_task(task, has_sync_record=False):
                    skipped_old_completed += 1
                    continue

                task.sync_id = str(uuid.uuid4())
                actions.append(SyncAction(
                    action="create",
                    target_system="supernote",
                    task=task,
                    reason="New in Apple Reminders"
                ))

        if skipped_old_completed > 0:
            logger.info(f"  Skipped {skipped_old_completed} old completed tasks (>6 months)")

        for task in supernote_tasks:
            if task.supernote_id not in matched_supernote_ids:
                task.sync_id = str(uuid.uuid4())
                actions.append(SyncAction(
                    action="create",
                    target_system="apple",
                    task=task,
                    reason="New in Supernote"
                ))

        return actions

    def _resolve_conflict(
        self,
        apple_task: UnifiedTask,
        supernote_task: UnifiedTask,
        record: Optional[SyncRecord]
    ) -> Optional[SyncAction]:
        """
        Resolve conflict when task exists in both systems.

        Returns None if no sync needed, otherwise returns appropriate action.
        """
        # Calculate current hashes
        apple_hash = apple_task.content_hash()
        supernote_hash = supernote_task.content_hash()

        # Get last synced hash
        last_hash = record.last_synced_hash if record else ""

        # If both match each other, no sync needed
        if apple_hash == supernote_hash:
            return None

        # If neither changed from last sync, no action (shouldn't happen)
        if apple_hash == last_hash and supernote_hash == last_hash:
            return None

        # Determine which changed
        apple_changed = apple_hash != last_hash
        supernote_changed = supernote_hash != last_hash

        if apple_changed and not supernote_changed:
            # Only Apple changed -> update Supernote
            # Transfer sync metadata
            supernote_task.sync_id = apple_task.sync_id
            supernote_task.apple_id = apple_task.apple_id  # Preserve link for sync record
            supernote_task.title = apple_task.title
            supernote_task.notes = apple_task.notes
            supernote_task.completed = apple_task.completed
            supernote_task.due_date = apple_task.due_date
            supernote_task.priority = apple_task.priority
            supernote_task.category = apple_task.category
            # Preserve document link from Supernote
            return SyncAction(
                action="update",
                target_system="supernote",
                task=supernote_task,
                reason="Changed in Apple Reminders"
            )

        if supernote_changed and not apple_changed:
            # Only Supernote changed -> update Apple
            apple_task.sync_id = supernote_task.sync_id
            apple_task.supernote_id = supernote_task.supernote_id  # Preserve link for sync record
            apple_task.title = supernote_task.title
            apple_task.notes = supernote_task.notes
            apple_task.completed = supernote_task.completed
            apple_task.due_date = supernote_task.due_date
            apple_task.priority = supernote_task.priority
            apple_task.category = supernote_task.category
            apple_task.document_link = supernote_task.document_link
            return SyncAction(
                action="update",
                target_system="apple",
                task=apple_task,
                reason="Changed in Supernote"
            )

        # Both changed -> conflict resolution
        # Use modification timestamp, prefer most recent
        # Strip timezone info for comparison (normalize to naive UTC)
        apple_mod = apple_task.modified_at.replace(tzinfo=None) if apple_task.modified_at else datetime.min
        supernote_mod = supernote_task.modified_at.replace(tzinfo=None) if supernote_task.modified_at else datetime.min

        # If timestamps are within 60 seconds, prefer Apple (configurable default)
        time_diff = abs((apple_mod - supernote_mod).total_seconds())

        if time_diff < 60 or apple_mod >= supernote_mod:
            # Apple wins
            supernote_task.sync_id = apple_task.sync_id
            supernote_task.apple_id = apple_task.apple_id  # Preserve link for sync record
            supernote_task.title = apple_task.title
            supernote_task.notes = apple_task.notes
            supernote_task.completed = apple_task.completed
            supernote_task.due_date = apple_task.due_date
            supernote_task.priority = apple_task.priority
            supernote_task.category = apple_task.category
            logger.info(f"  Conflict resolved: Apple wins for '{apple_task.title}'")
            return SyncAction(
                action="update",
                target_system="supernote",
                task=supernote_task,
                reason="Conflict: Apple Reminders wins (more recent)"
            )
        else:
            # Supernote wins
            apple_task.sync_id = supernote_task.sync_id
            apple_task.supernote_id = supernote_task.supernote_id  # Preserve link for sync record
            apple_task.title = supernote_task.title
            apple_task.notes = supernote_task.notes
            apple_task.completed = supernote_task.completed
            apple_task.due_date = supernote_task.due_date
            apple_task.priority = supernote_task.priority
            apple_task.category = supernote_task.category
            apple_task.document_link = supernote_task.document_link
            logger.info(f"  Conflict resolved: Supernote wins for '{supernote_task.title}'")
            return SyncAction(
                action="update",
                target_system="apple",
                task=apple_task,
                reason="Conflict: Supernote wins (more recent)"
            )

    def _execute_action(self, action: SyncAction, result: SyncResult):
        """Execute a single sync action and update the result."""
        try:
            if action.target_system == "supernote":
                self._execute_supernote_action(action, result)
            else:
                self._execute_apple_action(action, result)

            # Update sync state
            self._update_sync_record(action)

            logger.info(f"  ✓ {action}")

        except Exception as e:
            logger.error(f"  ✗ {action}: {e}")
            result.errors.append(str(e))

    def _execute_supernote_action(self, action: SyncAction, result: SyncResult):
        """Execute an action targeting Supernote."""
        if action.action == "create":
            self.supernote.create_task(action.task)
            result.apple_to_supernote_created += 1

        elif action.action == "update":
            self.supernote.update_task(action.task)
            result.apple_to_supernote_updated += 1
            if "Conflict" in action.reason:
                result.conflicts_resolved += 1

        elif action.action == "delete":
            if action.task.supernote_id:
                self.supernote.delete_task(action.task.supernote_id)
            result.apple_to_supernote_deleted += 1

    def _execute_apple_action(self, action: SyncAction, result: SyncResult):
        """Execute an action targeting Apple Reminders."""
        if action.action == "create":
            apple_id = self.apple.create_reminder(action.task)
            action.task.apple_id = apple_id
            result.supernote_to_apple_created += 1

        elif action.action == "update":
            self.apple.update_reminder(action.task)
            result.supernote_to_apple_updated += 1
            if "Conflict" in action.reason:
                result.conflicts_resolved += 1

        elif action.action == "delete":
            if action.task.apple_id:
                self.apple.delete_reminder(action.task.apple_id)
            result.supernote_to_apple_deleted += 1

    def _update_sync_record(self, action: SyncAction):
        """Update sync state after an action."""
        task = action.task

        if action.action == "delete":
            self.sync_state.delete_record(task.sync_id)
        else:
            record = SyncRecord(
                sync_id=task.sync_id,
                apple_id=normalize_apple_id(task.apple_id),
                supernote_id=task.supernote_id,
                last_synced_hash=task.content_hash(),
                last_sync_time=int(datetime.now().timestamp()),
                source_system="both"
            )
            self.sync_state.upsert_record(record)

    def get_status(self) -> dict:
        """Get current sync status."""
        stats = self.sync_state.get_stats()

        # Count tasks in each system
        try:
            supernote_count = len(self.supernote.list_tasks())
        except Exception:
            supernote_count = -1

        try:
            apple_count = len(self.apple.get_all_reminders())
        except Exception:
            apple_count = -1

        return {
            "sync_state": stats,
            "supernote_tasks": supernote_count,
            "apple_reminders": apple_count,
            "last_logs": self.sync_state.get_recent_logs(5)
        }
