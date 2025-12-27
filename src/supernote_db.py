"""
Supernote Database Interface

Connects to the Supernote MariaDB database to read and write tasks.
Handles document link preservation and category management.

Security Architecture:
    SQL Injection Prevention:
    - All task/category IDs are validated via _validate_id() to allow only
      alphanumeric characters, hyphens, and underscores (UUID-safe characters)
    - User-controlled text (titles, notes) is escaped via _escape_sql() which
      handles backslashes, single quotes, and null bytes
    - SQL is executed via Docker exec to the MariaDB container, providing
      process isolation from the host system
    - The database user should have minimal required permissions

    Note: This architecture uses string escaping rather than parameterized queries
    due to the Docker exec interface. The combination of ID validation, text
    escaping, and container isolation provides defense in depth.
"""

import subprocess
import re
from datetime import datetime
from typing import Optional
import json

from .models import UnifiedTask, DocumentLink
from . import config


def _encode_emoji(text: str) -> str:
    """
    Encode emoji characters to [U+XXXX] format for Supernote compatibility.

    Supernote's MariaDB uses utf8 (3-byte) which can't store emoji (4-byte).
    This encoding preserves emoji in a reversible format.
    """
    if not text:
        return text

    result = []
    for char in text:
        # Check if character is outside BMP (Basic Multilingual Plane)
        # These are 4-byte UTF-8 characters including most emoji
        if ord(char) > 0xFFFF:
            result.append(f"[U+{ord(char):X}]")
        else:
            result.append(char)
    return "".join(result)


def _decode_emoji(text: str) -> str:
    """
    Decode [U+XXXX] format back to emoji characters.

    Reverses the encoding done by _encode_emoji().
    """
    if not text or "[U+" not in text:
        return text

    import re
    def replace_unicode(match):
        try:
            return chr(int(match.group(1), 16))
        except (ValueError, OverflowError):
            return match.group(0)  # Return original if invalid

    return re.sub(r'\[U\+([0-9A-Fa-f]+)\]', replace_unicode, text)


class SupernoteDB:
    """
    Interface to the Supernote MariaDB database running in Docker.

    The database stores tasks in the t_schedule_task table with:
    - task_id: Unique identifier (UUID-like string)
    - task_list_id: Category/list reference (NULL = Inbox)
    - title: Task title
    - detail: Notes/details
    - status: 'needsAction' or 'completed'
    - due_time: Unix timestamp in milliseconds
    - completed_time: Unix timestamp in milliseconds
    - last_modified: Unix timestamp in milliseconds
    - links: Base64-encoded JSON with document link
    - is_deleted: 'Y' or 'N' (soft delete)
    """

    def __init__(
        self,
        container_name: Optional[str] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Initialize database connection parameters.

        All parameters default to environment variables or config defaults.

        Args:
            container_name: Docker container name (env: SUPERNOTE_DOCKER_CONTAINER)
            database: Database name (env: SUPERNOTE_DB_NAME)
            user: MySQL user (env: SUPERNOTE_DB_USER)
            password: MySQL password (env: SUPERNOTE_DB_PASSWORD, required)
        """
        self.container_name = container_name or config.SUPERNOTE_DOCKER_CONTAINER
        self.database = database or config.SUPERNOTE_DB_NAME
        self.user = user or config.SUPERNOTE_DB_USER
        self.password = password or config.get_db_password()
        self._user_id: Optional[int] = None
        self._categories_cache: Optional[dict] = None

    @staticmethod
    def _escape_sql(value: str) -> str:
        """Escape a string value for safe SQL insertion."""
        if value is None:
            return "NULL"
        # Escape backslashes first, then single quotes
        escaped = value.replace("\\", "\\\\").replace("'", "''")
        # Remove any null bytes
        escaped = escaped.replace("\x00", "")
        return escaped

    @staticmethod
    def _validate_id(value: str) -> str:
        """Validate that a value is a safe ID (alphanumeric + hyphens only)."""
        if not value:
            raise ValueError("ID cannot be empty")
        if not re.match(r'^[a-zA-Z0-9_-]+$', value):
            raise ValueError(f"Invalid ID format: {value}")
        return value

    def _execute_sql(self, sql: str, fetch: bool = True) -> Optional[list[dict]]:
        """Execute SQL via Docker and return results as list of dicts."""
        cmd = [
            "docker", "exec", self.container_name,
            "mysql", "-u", self.user, f"-p{self.password}",
            self.database, "-e", sql, "--batch", "--raw"
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            if not fetch or not result.stdout.strip():
                return None

            lines = result.stdout.strip().split("\n")
            if len(lines) < 2:
                return []

            headers = lines[0].split("\t")
            rows = []
            for line in lines[1:]:
                values = line.split("\t")
                row = {}
                for i, header in enumerate(headers):
                    value = values[i] if i < len(values) else None
                    if value == "NULL":
                        value = None
                    row[header] = value
                rows.append(row)

            return rows

        except subprocess.CalledProcessError as e:
            print(f"SQL Error: {e.stderr}")
            raise

    def _get_user_id(self) -> int:
        """Get the user ID (assumes single user)."""
        if self._user_id is None:
            result = self._execute_sql(
                "SELECT DISTINCT user_id FROM t_schedule_task LIMIT 1;"
            )
            if result:
                self._user_id = int(result[0]["user_id"])
            else:
                # Default user ID if no tasks exist yet
                result = self._execute_sql("SELECT id FROM u_user LIMIT 1;")
                if result:
                    self._user_id = int(result[0]["id"])
                else:
                    self._user_id = 1
        return self._user_id

    def list_categories(self, refresh: bool = False) -> dict[str, str]:
        """
        Get all task categories/lists.

        Returns:
            Dict mapping task_list_id to title
        """
        if self._categories_cache is None or refresh:
            result = self._execute_sql(
                "SELECT task_list_id, title FROM t_schedule_task_group WHERE is_deleted='N';"
            )
            self._categories_cache = {
                row["task_list_id"]: row["title"]
                for row in (result or [])
            }
        return self._categories_cache

    def get_category_id(self, name: str) -> Optional[str]:
        """Get category ID by name."""
        categories = self.list_categories()
        for cat_id, cat_name in categories.items():
            if cat_name.lower() == name.lower():
                return cat_id
        return None

    def get_category_name(self, category_id: Optional[str]) -> str:
        """Get category name by ID. Returns 'Inbox' for NULL."""
        if not category_id:
            return "Inbox"
        categories = self.list_categories()
        return categories.get(category_id, "Inbox")

    def list_tasks(self, category: Optional[str] = None, include_completed: bool = True) -> list[UnifiedTask]:
        """
        Get all tasks, optionally filtered by category.

        Args:
            category: Category name to filter by (None = all)
            include_completed: Include completed tasks

        Returns:
            List of UnifiedTask objects
        """
        where_clauses = ["t.is_deleted='N'"]

        if category:
            cat_id = self.get_category_id(category)
            if cat_id:
                safe_cat_id = self._validate_id(cat_id)
                where_clauses.append(f"t.task_list_id='{safe_cat_id}'")
            elif category.lower() == "inbox":
                where_clauses.append("t.task_list_id IS NULL")

        if not include_completed:
            where_clauses.append("t.status='needsAction'")

        where = " AND ".join(where_clauses)

        # Replace newlines/tabs in text fields to prevent row parsing issues
        # MySQL --batch --raw doesn't escape these characters
        sql = f"""
        SELECT
            t.task_id,
            t.task_list_id,
            REPLACE(REPLACE(t.title, '\n', ' '), '\t', ' ') as title,
            REPLACE(REPLACE(t.detail, '\n', ' '), '\t', ' ') as detail,
            t.status,
            t.importance,
            t.due_time,
            t.completed_time,
            t.last_modified,
            REPLACE(REPLACE(t.links, '\n', ' '), '\t', ' ') as links,
            t.is_reminder_on,
            t.recurrence,
            COALESCE(g.title, 'Inbox') as category_name
        FROM t_schedule_task t
        LEFT JOIN t_schedule_task_group g ON t.task_list_id = g.task_list_id
        WHERE {where}
        ORDER BY t.last_modified DESC;
        """

        result = self._execute_sql(sql)
        tasks = []

        for row in (result or []):
            task = self._row_to_task(row)
            tasks.append(task)

        return tasks

    def get_task(self, task_id: str) -> Optional[UnifiedTask]:
        """Get a specific task by ID."""
        safe_id = self._validate_id(task_id)
        sql = f"""
        SELECT
            t.task_id,
            t.task_list_id,
            REPLACE(REPLACE(t.title, '\n', ' '), '\t', ' ') as title,
            REPLACE(REPLACE(t.detail, '\n', ' '), '\t', ' ') as detail,
            t.status,
            t.importance,
            t.due_time,
            t.completed_time,
            t.last_modified,
            REPLACE(REPLACE(t.links, '\n', ' '), '\t', ' ') as links,
            t.is_reminder_on,
            t.recurrence,
            COALESCE(g.title, 'Inbox') as category_name
        FROM t_schedule_task t
        LEFT JOIN t_schedule_task_group g ON t.task_list_id = g.task_list_id
        WHERE t.task_id='{safe_id}' AND t.is_deleted='N';
        """

        result = self._execute_sql(sql)
        if result:
            return self._row_to_task(result[0])
        return None

    def _row_to_task(self, row: dict) -> UnifiedTask:
        """Convert a database row to UnifiedTask."""
        # Parse document link from Base64
        doc_link = None
        if row.get("links"):
            doc_link = DocumentLink.from_base64(row["links"])

        # Parse timestamps (milliseconds to datetime)
        due_date = None
        if row.get("due_time") and int(row["due_time"]) > 0:
            due_date = datetime.fromtimestamp(int(row["due_time"]) / 1000)

        completion_date = None
        if row.get("completed_time") and int(row["completed_time"]) > 0:
            completion_date = datetime.fromtimestamp(int(row["completed_time"]) / 1000)

        modified_at = None
        if row.get("last_modified"):
            modified_at = datetime.fromtimestamp(int(row["last_modified"]) / 1000)

        # Decode emoji from [U+XXXX] format back to actual emoji
        return UnifiedTask(
            supernote_id=row["task_id"],
            title=_decode_emoji(row.get("title", "")),
            notes=_decode_emoji(row.get("detail") or ""),
            category=row.get("category_name", "Inbox"),
            completed=row.get("status") == "completed",
            status=row.get("status", "needsAction"),
            due_date=due_date,
            completion_date=completion_date,
            modified_at=modified_at,
            document_link=doc_link,
            priority=self._parse_importance(row.get("importance")),
        )

    def _parse_importance(self, importance: Optional[str]) -> int:
        """Parse Supernote importance to priority."""
        # Supernote importance values are not well documented
        # We'll map them as best we can
        if not importance:
            return 0
        try:
            return int(importance)
        except ValueError:
            return 0

    def create_task(self, task: UnifiedTask) -> str:
        """
        Create a new task in Supernote.

        Args:
            task: UnifiedTask to create

        Returns:
            The created task's ID
        """
        import uuid

        # Generate task ID if not provided
        if not task.supernote_id:
            task.supernote_id = uuid.uuid4().hex

        # Validate task ID
        safe_task_id = self._validate_id(task.supernote_id)

        # Get category ID
        category_id = "NULL"
        if task.category and task.category.lower() != "inbox":
            cat_id = self.get_category_id(task.category)
            if cat_id:
                safe_cat_id = self._validate_id(cat_id)
                category_id = f"'{safe_cat_id}'"
            else:
                # Create the category if it doesn't exist
                cat_id = self.create_category(task.category)
                safe_cat_id = self._validate_id(cat_id)
                category_id = f"'{safe_cat_id}'"

        # Prepare values with proper escaping
        # Encode emoji to [U+XXXX] format for Supernote compatibility
        user_id = self._get_user_id()
        now_ms = int(datetime.now().timestamp() * 1000)
        title = self._escape_sql(_encode_emoji(task.title))
        # Supernote detail column is varchar(255) - truncate AFTER encoding
        # because emoji expand from 1 char to ~10 chars (e.g. emoji -> [U+1F6B1])
        notes = _encode_emoji(task.notes or "")[:255]
        detail = self._escape_sql(notes)
        status = "completed" if task.completed else "needsAction"
        due_time = int(task.due_date.timestamp() * 1000) if task.due_date else 0
        completed_time = int(task.completion_date.timestamp() * 1000) if task.completion_date else 0

        # Encode document link if present (Base64 is safe)
        links = "NULL"
        if task.document_link:
            links = f"'{task.document_link.to_base64()}'"

        sql = f"""
        INSERT INTO t_schedule_task (
            task_id, task_list_id, user_id, title, detail,
            last_modified, is_reminder_on, status, importance,
            due_time, completed_time, links, is_deleted,
            sort, sort_completed, planer_sort, all_sort,
            all_sort_completed, sort_time, planer_sort_time, all_sort_time
        ) VALUES (
            '{safe_task_id}', {category_id}, {user_id}, '{title}', '{detail}',
            {now_ms}, 'N', '{status}', NULL,
            {due_time}, {completed_time}, {links}, 'N',
            NULL, NULL, NULL, NULL, NULL, {now_ms}, {now_ms}, {now_ms}
        );
        """

        self._execute_sql(sql, fetch=False)
        return task.supernote_id

    def update_task(self, task: UnifiedTask):
        """
        Update an existing task.

        IMPORTANT: Preserves document links from the original task.
        """
        if not task.supernote_id:
            raise ValueError("Cannot update task without supernote_id")

        # Validate task ID
        safe_task_id = self._validate_id(task.supernote_id)

        # Get existing task to preserve document link if not provided
        existing = self.get_task(task.supernote_id)
        if existing and existing.document_link and not task.document_link:
            task.document_link = existing.document_link

        # Get category ID
        category_id = "NULL"
        if task.category and task.category.lower() != "inbox":
            cat_id = self.get_category_id(task.category)
            if cat_id:
                safe_cat_id = self._validate_id(cat_id)
                category_id = f"'{safe_cat_id}'"

        # Encode emoji to [U+XXXX] format for Supernote compatibility
        now_ms = int(datetime.now().timestamp() * 1000)
        title = self._escape_sql(_encode_emoji(task.title))
        # Supernote detail column is varchar(255) - truncate AFTER encoding
        # because emoji expand from 1 char to ~10 chars (e.g. emoji -> [U+1F6B1])
        notes = _encode_emoji(task.notes or "")[:255]
        detail = self._escape_sql(notes)
        status = "completed" if task.completed else "needsAction"
        due_time = int(task.due_date.timestamp() * 1000) if task.due_date else 0
        completed_time = int(task.completion_date.timestamp() * 1000) if task.completion_date else 0

        # Encode document link (Base64 is safe)
        links = "NULL"
        if task.document_link:
            links = f"'{task.document_link.to_base64()}'"

        sql = f"""
        UPDATE t_schedule_task SET
            task_list_id = {category_id},
            title = '{title}',
            detail = '{detail}',
            status = '{status}',
            due_time = {due_time},
            completed_time = {completed_time},
            links = {links},
            last_modified = {now_ms}
        WHERE task_id = '{safe_task_id}';
        """

        self._execute_sql(sql, fetch=False)

    def delete_task(self, task_id: str, soft: bool = True):
        """
        Delete a task.

        Args:
            task_id: Task ID to delete
            soft: If True, marks as deleted. If False, actually removes.
        """
        safe_id = self._validate_id(task_id)

        if soft:
            now_ms = int(datetime.now().timestamp() * 1000)
            sql = f"""
            UPDATE t_schedule_task SET
                is_deleted = 'Y',
                last_modified = {now_ms}
            WHERE task_id = '{safe_id}';
            """
        else:
            sql = f"DELETE FROM t_schedule_task WHERE task_id = '{safe_id}';"

        self._execute_sql(sql, fetch=False)

    def create_category(self, name: str) -> str:
        """Create a new category/list."""
        import uuid

        cat_id = uuid.uuid4().hex
        user_id = self._get_user_id()
        now_ms = int(datetime.now().timestamp() * 1000)
        title = self._escape_sql(name)

        sql = f"""
        INSERT INTO t_schedule_task_group (
            task_list_id, user_id, title, last_modified, is_deleted, create_time
        ) VALUES (
            '{cat_id}', {user_id}, '{title}', {now_ms}, 'N', {now_ms}
        );
        """

        self._execute_sql(sql, fetch=False)
        self._categories_cache = None  # Invalidate cache
        return cat_id

    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            result = self._execute_sql("SELECT 1 as test;")
            return result is not None
        except Exception:
            return False
