#!/usr/bin/env python3
"""
Supernote ↔ Apple Reminders Sync CLI

Main command-line interface for the sync tool.
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime

from .sync_engine import SyncEngine
from .supernote_db import SupernoteDB
from .apple_reminders import AppleReminders
from .sync_state import SyncState
from .snapshot import create_snapshot, list_snapshots, restore_snapshot, print_snapshot_info
from . import config


def cmd_sync(args):
    """Run the sync."""
    engine = SyncEngine()

    print("Starting sync...")
    result = engine.run_sync(dry_run=args.dry_run)

    if args.dry_run:
        print("\n[DRY RUN] No changes were made.")

    return 0 if not result.errors else 1


def cmd_status(args):
    """Show sync status."""
    engine = SyncEngine()
    status = engine.get_status()

    print("\n=== Sync Status ===\n")
    print(f"Supernote tasks: {status['supernote_tasks']}")
    print(f"Apple reminders: {status['apple_reminders']}")
    print()
    print("Sync State:")
    for key, value in status["sync_state"].items():
        print(f"  {key}: {value}")

    if status["last_logs"]:
        print("\nRecent Activity:")
        for log in status["last_logs"]:
            print(f"  [{log['timestamp']}] {log['action']}")

    return 0


def cmd_snapshot(args):
    """Manage snapshots."""
    if args.action == "create":
        create_snapshot()
    elif args.action == "list":
        snapshots = list_snapshots()
        if not snapshots:
            print("No snapshots found.")
        else:
            print(f"Found {len(snapshots)} snapshot(s):\n")
            for path in snapshots:
                with open(path) as f:
                    data = json.load(f)
                meta = data.get("metadata", {})
                print(f"  {path.name}")
                print(f"    Created: {data['created_at']}")
                print(f"    Reminders: {meta.get('total_reminders', 'N/A')}")
                print()
    elif args.action == "info" and args.path:
        print_snapshot_info(Path(args.path))
    return 0


def cmd_restore(args):
    """Restore from snapshot."""
    snapshot_path = Path(args.snapshot)
    if not snapshot_path.exists():
        print(f"Error: Snapshot not found: {snapshot_path}")
        return 1

    restore_snapshot(
        snapshot_path,
        dry_run=not args.execute,
        confirm=not args.yes
    )
    return 0


def cmd_categories(args):
    """Show category mappings."""
    supernote = SupernoteDB()
    apple = AppleReminders()

    print("\n=== Categories ===\n")

    print("Supernote Lists:")
    for cat_id, cat_name in supernote.list_categories().items():
        print(f"  - {cat_name} ({cat_id[:8]}...)")
    print("  - Inbox (default)")

    print("\nApple Reminder Lists:")
    for list_name in apple.list_lists():
        print(f"  - {list_name}")

    return 0


def cmd_test(args):
    """Test connections to both systems."""
    print("\n=== Connection Test ===\n")

    # Test Supernote
    print("Testing Supernote database...")
    try:
        supernote = SupernoteDB()
        if supernote.test_connection():
            tasks = supernote.list_tasks()
            print(f"  ✓ Connected. Found {len(tasks)} tasks.")
        else:
            print("  ✗ Connection failed.")
    except Exception as e:
        print(f"  ✗ Error: {e}")

    # Test Apple Reminders
    print("\nTesting Apple Reminders...")
    try:
        apple = AppleReminders()
        if apple.test_connection():
            reminders = apple.get_all_reminders()
            print(f"  ✓ Connected. Found {len(reminders)} reminders.")
        else:
            print("  ✗ Connection failed.")
    except Exception as e:
        print(f"  ✗ Error: {e}")

    return 0


def cmd_init(args):
    """Initialize the sync system."""
    print("\n=== Initializing Sync System ===\n")

    # Create sync state database
    sync_state = SyncState()
    print(f"✓ Created sync state database at: {sync_state.db_path}")

    # Test connections
    print("\nTesting connections...")
    cmd_test(args)

    # Create initial snapshot
    print("\nCreating initial Apple Reminders snapshot...")
    snapshot_path = create_snapshot()
    print(f"✓ Snapshot saved to: {snapshot_path}")

    print("\n=== Initialization Complete ===")
    print("\nNext steps:")
    print("  1. Review your settings in config/")
    print("  2. Run 'sync --dry-run' to preview changes")
    print("  3. Run 'sync' to perform the actual sync")

    return 0


def cmd_clear_state(args):
    """Clear all sync state (for debugging)."""
    if not args.yes:
        response = input("This will clear all sync state. Type 'CLEAR' to confirm: ")
        if response != "CLEAR":
            print("Cancelled.")
            return 1

    sync_state = SyncState()
    sync_state.clear_all()
    print("Sync state cleared.")
    return 0


def cmd_config(args):
    """Show current configuration."""
    config.print_config()
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Supernote ↔ Apple Reminders Sync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize the sync system
  python -m src.main init

  # Preview what sync would do
  python -m src.main sync --dry-run

  # Run the actual sync
  python -m src.main sync

  # Check sync status
  python -m src.main status

  # Create a backup
  python -m src.main snapshot create

  # List backups
  python -m src.main snapshot list

  # Restore from backup (preview)
  python -m src.main restore snapshots/apple_reminders_20250101_120000.json

  # Restore from backup (execute)
  python -m src.main restore --execute snapshots/apple_reminders_20250101_120000.json
"""
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init command
    subparsers.add_parser("init", help="Initialize the sync system")

    # sync command
    sync_parser = subparsers.add_parser("sync", help="Run the sync")
    sync_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview changes without making them"
    )

    # status command
    subparsers.add_parser("status", help="Show sync status")

    # snapshot command
    snapshot_parser = subparsers.add_parser("snapshot", help="Manage Apple Reminders snapshots")
    snapshot_parser.add_argument(
        "action",
        choices=["create", "list", "info"],
        help="Snapshot action"
    )
    snapshot_parser.add_argument(
        "path",
        nargs="?",
        help="Path to snapshot (for 'info' action)"
    )

    # restore command
    restore_parser = subparsers.add_parser("restore", help="Restore from snapshot")
    restore_parser.add_argument("snapshot", help="Path to snapshot file")
    restore_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the restore (default is dry-run)"
    )
    restore_parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt"
    )

    # categories command
    subparsers.add_parser("categories", help="Show category mappings")

    # test command
    subparsers.add_parser("test", help="Test connections to both systems")

    # clear-state command (hidden/debug)
    clear_parser = subparsers.add_parser("clear-state", help="Clear sync state (debug)")
    clear_parser.add_argument("--yes", "-y", action="store_true")

    # config command
    subparsers.add_parser("config", help="Show current configuration")

    args = parser.parse_args()

    # Dispatch to command handler
    commands = {
        "init": cmd_init,
        "sync": cmd_sync,
        "status": cmd_status,
        "snapshot": cmd_snapshot,
        "restore": cmd_restore,
        "categories": cmd_categories,
        "test": cmd_test,
        "clear-state": cmd_clear_state,
        "config": cmd_config,
    }

    handler = commands.get(args.command)
    if handler:
        sys.exit(handler(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
