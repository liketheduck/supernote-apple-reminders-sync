# Supernote ↔ Apple Reminders Sync

A bidirectional sync tool that synchronizes tasks between a Supernote device's to-do database (running in Docker/MariaDB) and Apple Reminders on macOS.

## Features

- **Bidirectional sync**: Changes in either system propagate to the other
- **Category rename tracking**: Renaming a category/list on either side automatically renames it on the other
- **Document link preservation**: Supernote note links are preserved during sync
- **Anti-loop architecture**: Content hashing prevents infinite sync loops
- **Conflict resolution**: Uses modification timestamps to resolve conflicts
- **Dry-run mode**: Preview changes before applying them
- **Backup/restore**: Snapshot Apple Reminders for safe recovery

## Prerequisites

- macOS (tested on Sonoma)
- Python 3.11+
- Docker (with Supernote MariaDB container running) OR remote MariaDB server
- Swift compiler (included with Xcode Command Line Tools)

## Installation

1. Clone this repository
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Install reminders-cli:
   ```bash
   cd /tmp
   git clone --depth 1 https://github.com/keith/reminders-cli.git
   cd reminders-cli && swift build -c release
   mkdir -p ~/.local/bin
   cp .build/release/reminders ~/.local/bin/
   ```
4. Compile the Swift helper:
   ```bash
   cd swift
   swiftc -O -o reminder-helper reminder-helper.swift
   ```
5. Grant Reminders access when prompted

## Quick Start

```bash
# Set database password (required)
export SUPERNOTE_DB_PASSWORD="your-password-here"

# Initialize the sync system (creates backup + tests connections)
python -m src.main init

# Preview what sync would do (ALWAYS do this first!)
python -m src.main sync --dry-run

# Run the actual sync
python -m src.main sync

# Check status
python -m src.main status
```

## Commands

### Sync Operations

```bash
# Preview changes without making them
python -m src.main sync --dry-run

# Execute the sync
python -m src.main sync

# Show sync status
python -m src.main status

# Show category mappings
python -m src.main categories
```

### Backup/Restore

```bash
# Create a snapshot of Apple Reminders
python -m src.main snapshot create

# List all snapshots
python -m src.main snapshot list

# Show snapshot details
python -m src.main snapshot info snapshots/apple_reminders_YYYYMMDD_HHMMSS.json

# Restore from snapshot (preview)
python -m src.main restore snapshots/apple_reminders_YYYYMMDD_HHMMSS.json

# Restore from snapshot (execute)
python -m src.main restore --execute snapshots/apple_reminders_YYYYMMDD_HHMMSS.json
```

### Diagnostics

```bash
# Test connections to both systems
python -m src.main test

# Show current configuration
python -m src.main config

# Clear sync state (debug only)
python -m src.main clear-state --yes
```

## How It Works

### Sync Algorithm

1. **Load tasks** from both Supernote (MariaDB) and Apple Reminders
2. **Match tasks** using the sync state database (falls back to title matching)
3. **Detect changes** using content hashing (title + notes + status + priority + category)
4. **Resolve conflicts** using modification timestamps (most recent wins)
5. **Apply changes** to the appropriate system

### Sync ID Storage

The sync tool maintains task relationships in a local SQLite database (`sync_state.db`):
- Maps Apple Reminder IDs (`apple_id`) to Supernote task IDs (`supernote_id`)
- Tracks content hashes for change detection
- Falls back to title-based matching for initial sync of existing tasks
- No metadata is added to your Apple Reminders notes

### Document Links

Supernote tasks can link to specific pages in notes. These are stored as Base64-encoded JSON in the `links` field and are preserved during sync. In Apple Reminders, they appear as:

```
📎 My Note.note (page 3)
```

## Project Structure

```
supernote-reminders-sync/
├── src/
│   ├── main.py              # CLI interface
│   ├── sync_engine.py       # Core sync logic
│   ├── supernote_db.py      # Supernote database interface
│   ├── apple_reminders.py   # Apple Reminders interface
│   ├── sync_state.py        # Sync state management
│   ├── models.py            # Data models
│   ├── snapshot.py          # Backup/restore
│   └── config.py            # Configuration management
├── swift/
│   └── reminder-helper.swift  # Swift helper for due date, priority, move
├── config/
│   ├── category_map.json    # Category mappings
│   └── settings.json        # Settings
├── docs/
│   ├── supernote_schema.md  # Database schema documentation
│   └── research_notes.md    # Research findings
├── snapshots/               # Apple Reminders backups
├── logs/                    # Sync logs
└── sync_state.db           # Sync tracking database
```

## Configuration

### Environment Variables

Copy the example files and configure your settings:

```bash
# Environment variables
cp .env.example .env

# Config files
cp config/settings.example.json config/settings.json
cp config/category_map.example.json config/category_map.json

# Edit with your values
```

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPERNOTE_DB_PASSWORD` | **(required)** | Password for the Supernote MariaDB database |
| `SUPERNOTE_DB_MODE` | `docker` | Connection mode: `docker` (local container) or `tcp` (remote server) |
| `SUPERNOTE_DB_HOST` | `localhost` | MariaDB host (only used if mode=tcp) |
| `SUPERNOTE_DB_PORT` | `3306` | MariaDB port (only used if mode=tcp) |
| `SUPERNOTE_DOCKER_CONTAINER` | `supernote-mariadb` | Docker container name (only used if mode=docker) |
| `SUPERNOTE_DB_NAME` | `supernotedb` | Database name |
| `SUPERNOTE_DB_USER` | `supernote` | Database user |
| `REMINDERS_CLI_PATH` | `~/.local/bin/reminders` | Path to reminders-cli binary |
| `SYNC_STATE_DB` | `./sync_state.db` | Path to sync state database |
| `SNAPSHOTS_DIR` | `./snapshots` | Directory for Apple Reminders backups |
| `LOGS_DIR` | `./logs` | Directory for log files |
| `SYNC_CONFLICT_RESOLUTION` | `prefer_recent` | Conflict strategy: `prefer_recent`, `prefer_apple`, `prefer_supernote` |
| `SYNC_CONFLICT_WINDOW` | `60` | Seconds to consider changes as simultaneous |
| `SYNC_COMPLETED_TASKS` | `true` | Whether to sync completed tasks |

### config/settings.json

```json
{
  "supernote": {
    "docker_container": "supernote-mariadb",
    "database": "supernotedb",
    "user": "supernote"
  },
  "sync": {
    "conflict_resolution": "prefer_recent",
    "conflict_window_seconds": 60,
    "preserve_document_links": true,
    "sync_completed_tasks": true
  }
}
```

### config/category_map.json

```json
{
  "mappings": [
    {"apple": "Inbox", "supernote": "Inbox"},
    {"apple": "Work", "supernote": "Work"}
  ],
  "defaults": {
    "apple": "Inbox",
    "supernote": "Inbox"
  },
  "auto_create_missing": true
}
```

## Emergency Recovery

If something goes wrong, restore from a snapshot:

```bash
# List available snapshots
python -m src.main snapshot list

# Preview restore
python -m src.main restore snapshots/apple_reminders_YYYYMMDD_HHMMSS.json

# Execute restore (requires typing "RESTORE" to confirm)
python -m src.main restore --execute snapshots/apple_reminders_YYYYMMDD_HHMMSS.json
```

## Automated Sync with launchd

To run sync automatically every 15 minutes:

1. Copy and configure the plist template:
   ```bash
   cp com.supernote.reminders-sync.example.plist com.supernote.reminders-sync.plist
   # Edit the plist with your actual paths and password
   ```

2. Install and load the launch agent:
   ```bash
   cp com.supernote.reminders-sync.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.supernote.reminders-sync.plist
   ```

3. Check status and logs:
   ```bash
   launchctl list | grep supernote
   tail -f logs/sync.log
   ```

To stop: `launchctl unload ~/Library/LaunchAgents/com.supernote.reminders-sync.plist`

## Permissions

### Reminders Access

On first run, macOS will prompt for Reminders access. You must grant access to:
- **Terminal** (if running manually)
- **Python** (the python3 binary)

If you accidentally deny access, re-enable it in:
**System Settings > Privacy & Security > Reminders**

### Full Disk Access for launchd

When running via launchd, the sync may fail silently if Python doesn't have Full Disk Access. To fix:

1. Go to **System Settings > Privacy & Security > Full Disk Access**
2. Click **+** and add `/opt/homebrew/bin/python3` (or your Python path)
3. Reload the launch agent

### Docker Access

The sync connects to MariaDB via `docker exec`. Ensure Docker Desktop is running and the Supernote container is started.

## Limitations

- **Supernote database access**: Requires the Supernote Cloud self-hosted MariaDB container
- **macOS only**: Uses macOS-specific tools (reminders-cli, Swift EventKit)
- **No recurrence sync**: Recurring tasks are not yet supported
- **No location sync**: Location-based reminders are not synced

## Technical Details

### Supernote Database

The Supernote to-do database is MariaDB. Supports two connection modes:
- **Docker mode** (default): Connects via `docker exec` to a local MariaDB container
- **TCP mode**: Connects directly via TCP to a remote MariaDB server (e.g., NAS via Tailscale)

Key tables:
- `t_schedule_task`: Main tasks table
- `t_schedule_task_group`: Categories/lists

See `docs/supernote_schema.md` for full schema documentation.

### Apple Reminders

Uses two Swift-based tools for fast native EventKit access:
- **reminders-cli**: For reading reminders (JSON output) and basic write operations (add, complete, uncomplete, delete, edit)
- **reminder-helper**: Custom Swift helper for operations reminders-cli doesn't support (set-due-date, set-priority, move, rename-list, delete-list)

### Category Sync

Categories are tracked by their internal IDs (not names) to detect renames:
- Supernote uses `task_list_id` (UUID)
- Apple uses `calendarIdentifier` (UUID)

When you rename a category on one system, the sync detects that the ID still exists but the name changed, and propagates the rename to the other system. This prevents orphaned tasks when categories are renamed.

## License

MIT License
