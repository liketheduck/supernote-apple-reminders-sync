# Supernote Database Schema Documentation

## Overview

The Supernote Cloud uses MariaDB (not SQLite as initially expected). The database is accessed via Docker container `supernote-mariadb`.

**Database**: `supernotedb`
**Connection**: Docker container on port 3306

---

## Task-Related Tables

### t_schedule_task (Main Tasks Table)

| Field | Type | Null | Key | Default | Description |
|-------|------|------|-----|---------|-------------|
| task_id | varchar(255) | NO | PRI | NULL | Unique task identifier (UUID-like) |
| task_list_id | varchar(255) | YES | | NULL | Reference to category/list (NULL = Inbox) |
| user_id | bigint(20) | NO | | NULL | User identifier |
| title | varchar(600) | YES | | NULL | Task title |
| detail | varchar(255) | YES | | '' | Task notes/details |
| last_modified | bigint(20) | YES | | NULL | Unix timestamp in milliseconds |
| recurrence | varchar(255) | YES | | '' | Recurrence pattern |
| is_reminder_on | char(2) | NO | | 'N' | Reminder enabled (Y/N) |
| status | varchar(255) | YES | | | Task status |
| importance | varchar(255) | YES | | | Priority level |
| due_time | bigint(20) | NO | | NULL | Due date as Unix timestamp (ms) |
| completed_time | bigint(20) | YES | | NULL | Completion timestamp (ms) |
| links | varchar(5000) | YES | | NULL | **Base64-encoded JSON document links** |
| is_deleted | char(2) | NO | | 'N' | Soft delete flag (Y/N) |
| sort | int(11) | YES | | NULL | Sort order |
| sort_completed | int(11) | YES | | NULL | Completed tasks sort order |
| planer_sort | int(11) | YES | | NULL | Planner view sort |
| all_sort | int(11) | YES | | NULL | All tasks view sort |
| all_sort_completed | int(11) | YES | | NULL | All completed sort |
| sort_time | bigint(20) | YES | | NULL | Sort timestamp |
| planer_sort_time | bigint(20) | YES | | NULL | Planner sort timestamp |
| all_sort_time | bigint(20) | YES | | NULL | All sort timestamp |

**Status Values**:
- `needsAction` - Task is pending/active
- `completed` - Task is completed

### t_schedule_task_group (Categories/Lists)

| Field | Type | Null | Key | Default | Description |
|-------|------|------|-----|---------|-------------|
| task_list_id | varchar(255) | NO | PRI | NULL | Unique list identifier |
| user_id | bigint(20) | NO | | NULL | User identifier |
| title | varchar(255) | NO | | NULL | List/category name |
| last_modified | bigint(20) | NO | | NULL | Last modified timestamp (ms) |
| is_deleted | char(2) | NO | | 'N' | Soft delete flag |
| create_time | bigint(20) | YES | | NULL | Creation timestamp (ms) |

**Category Examples**:
- `143228bf9e315c4f89b0e34742f07685` → "Work"
- `a4ab6658a939c495de30736fa3a07b9d` → "Personal"
- `NULL` task_list_id → "Inbox" (default)

### t_schedule_recur_task (Recurring Tasks)

| Field | Type | Null | Key | Default | Description |
|-------|------|------|-----|---------|-------------|
| task_id | varchar(255) | NO | PRI | NULL | Unique identifier |
| recurrence_id | varchar(255) | YES | | NULL | Recurrence pattern ID |
| task_list_id | varchar(255) | YES | | NULL | Category reference |
| user_id | bigint(20) | NO | | NULL | User identifier |
| last_modified | bigint(20) | NO | | NULL | Timestamp (ms) |
| due_time | bigint(20) | YES | | NULL | Due timestamp |
| completed_time | bigint(20) | YES | | NULL | Completion timestamp |
| status | varchar(255) | YES | | NULL | Task status |
| is_deleted | char(2) | NO | | 'N' | Soft delete flag |
| sort* | int(11) | YES | | NULL | Various sort fields |

---

## Document Links Format

**CRITICAL**: The `links` field contains Base64-encoded JSON that must be preserved during sync.

### Encoded Format
```
eyJhcHBOYW1lIjoibm90ZSIsImZpbGVJZCI6IkYyMDI1MDEwODExMDMwMTU1MTk0OHV2bmJ5U29WVTVkWiIsImZpbGVQYXRoIjoiL3N0b3JhZ2UvZW11bGF0ZWQvMC9Ob3RlL1dvcmsvTWVldGluZyBOb3RlcyAtIDIwMjUwMTA4XzExMDIxNC5ub3RlIiwicGFnZSI6MSwicGFnZUlkIjoiUDIwMjUwMTA4MTEwMzAxNTc0OTAyMkxpbVVyVXJqUkd2In0=
```

### Decoded JSON Structure
```json
{
  "appName": "note",
  "fileId": "F20250108110301551948uvnbySoVU5dZ",
  "filePath": "/storage/emulated/0/Note/Work/Meeting Notes - 20250108_110214.note",
  "page": 1,
  "pageId": "P202501081103015749022LimUrUrjRGv"
}
```

### Fields:
- **appName**: Always "note" for document links
- **fileId**: Unique file identifier (timestamp + random suffix)
- **filePath**: Android path to the .note file on device
- **page**: Page number within the note (1-indexed)
- **pageId**: Unique page identifier

---

## Timestamp Format

All timestamps are **Unix epoch in milliseconds** (not seconds).

Example: `1736354437151` = 2025-01-08T15:20:37.151Z

To convert in Python:
```python
from datetime import datetime
timestamp_ms = 1736354437151
dt = datetime.fromtimestamp(timestamp_ms / 1000)
```

---

## Sample Queries

### Get all active tasks with their categories
```sql
SELECT
    t.task_id,
    t.title,
    t.status,
    t.links,
    COALESCE(g.title, 'Inbox') as category
FROM t_schedule_task t
LEFT JOIN t_schedule_task_group g ON t.task_list_id = g.task_list_id
WHERE t.is_deleted = 'N' AND t.status = 'needsAction';
```

### Get all categories
```sql
SELECT task_list_id, title
FROM t_schedule_task_group
WHERE is_deleted = 'N';
```

---

## Connection Details

```bash
# Docker container
docker exec supernote-mariadb mysql -u supernote -p"$SUPERNOTE_DB_PASSWORD" supernotedb -e "QUERY"

# Or via Python
import os
import mysql.connector
conn = mysql.connector.connect(
    host='localhost',
    port=3306,
    user='supernote',
    password=os.environ['SUPERNOTE_DB_PASSWORD'],
    database='supernotedb'
)
```

---

## Sync Considerations

1. **Inbox Mapping**: Tasks with `task_list_id = NULL` belong to Inbox
2. **Soft Deletes**: Always check `is_deleted = 'N'`
3. **Document Links**: Must decode, preserve, and re-encode the `links` field exactly
4. **Timestamps**: Use milliseconds, not seconds
5. **UUID Generation**: New task IDs should match pattern (32 hex chars, lowercase)
