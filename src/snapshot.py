#!/usr/bin/env python3
"""
Apple Reminders Snapshot Tool

Creates and restores backups of Apple Reminders data.
Uses reminders-cli for all operations.
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
import sys

from . import config


def run_reminders_cli(*args: str) -> str:
    """Run reminders-cli command and return output."""
    cmd = [config.REMINDERS_CLI_PATH] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running reminders-cli: {e.stderr}", file=sys.stderr)
        raise


def get_all_lists() -> list[str]:
    """Get all reminder list names."""
    output = run_reminders_cli("show-lists")
    return [line.strip() for line in output.strip().split("\n") if line.strip()]


def get_all_reminders() -> list[dict]:
    """Get all reminders from all lists with full metadata."""
    output = run_reminders_cli("show-all", "--format", "json", "--include-completed")
    return json.loads(output)


def create_snapshot() -> Path:
    """
    Create a full snapshot of all Apple Reminders.

    Returns:
        Path to the created snapshot file.
    """
    config.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_path = config.SNAPSHOTS_DIR / f"apple_reminders_{timestamp}.json"

    print("Creating Apple Reminders snapshot...")

    # Get all lists
    lists = get_all_lists()
    print(f"  Found {len(lists)} lists: {', '.join(lists)}")

    # Get all reminders
    reminders = get_all_reminders()
    print(f"  Found {len(reminders)} total reminders")

    # Create snapshot data
    snapshot = {
        "created_at": datetime.now().isoformat(),
        "version": "1.0",
        "lists": lists,
        "reminders": reminders,
        "metadata": {
            "total_reminders": len(reminders),
            "total_lists": len(lists),
            "completed_count": sum(1 for r in reminders if r.get("isCompleted", False)),
            "incomplete_count": sum(1 for r in reminders if not r.get("isCompleted", False))
        }
    }

    # Write snapshot
    with open(snapshot_path, "w") as f:
        json.dump(snapshot, f, indent=2, default=str)

    print(f"  Snapshot saved to: {snapshot_path}")
    print(f"  Total size: {snapshot_path.stat().st_size:,} bytes")

    return snapshot_path


def list_snapshots() -> list[Path]:
    """List all available snapshots."""
    if not config.SNAPSHOTS_DIR.exists():
        return []

    snapshots = sorted(
        config.SNAPSHOTS_DIR.glob("apple_reminders_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    return snapshots


def load_snapshot(snapshot_path: Path) -> dict:
    """Load a snapshot file."""
    with open(snapshot_path) as f:
        return json.load(f)


def restore_snapshot(
    snapshot_path: Path,
    dry_run: bool = True,
    confirm: bool = True
) -> None:
    """
    Restore Apple Reminders from a snapshot.

    WARNING: This will DELETE ALL current reminders and recreate them from the snapshot!

    Args:
        snapshot_path: Path to the snapshot file.
        dry_run: If True, only show what would be done without making changes.
        confirm: If True, prompt for confirmation before proceeding.
    """
    snapshot = load_snapshot(snapshot_path)

    print(f"\nRestore Plan:")
    print(f"  Snapshot: {snapshot_path.name}")
    print(f"  Created: {snapshot['created_at']}")
    print(f"  Lists to restore: {len(snapshot['lists'])}")
    print(f"  Reminders to restore: {len(snapshot['reminders'])}")

    # Get current state
    current_lists = get_all_lists()
    current_reminders = get_all_reminders()

    print(f"\nCurrent State:")
    print(f"  Lists: {len(current_lists)}")
    print(f"  Reminders: {len(current_reminders)}")

    if dry_run:
        print("\n[DRY RUN] The following actions would be taken:")
        print(f"  1. Delete {len(current_reminders)} current reminders")
        print(f"  2. Create missing lists from snapshot")
        print(f"  3. Recreate {len(snapshot['reminders'])} reminders")
        print("\nRun with --no-dry-run to actually perform the restore.")
        return

    if confirm:
        print("\n" + "=" * 60)
        print("WARNING: This will DELETE ALL current reminders!")
        print("=" * 60)
        response = input("Type 'RESTORE' to confirm: ").strip()
        if response != "RESTORE":
            print("Restore cancelled.")
            return

    print("\nPerforming restore...")

    # Step 1: Delete all current reminders
    print(f"  Deleting {len(current_reminders)} current reminders...")
    deleted_count = 0
    for reminder in current_reminders:
        reminder_id = reminder.get("externalId")
        list_name = reminder.get("list", "Reminders")
        title = reminder.get("title", "Unknown")[:40]
        if reminder_id:
            try:
                run_reminders_cli("delete", list_name, reminder_id)
                deleted_count += 1
                print(f"    Deleted: {title}")
            except Exception as e:
                print(f"    FAILED: {title} - {e}")
    print(f"  Deleted {deleted_count}/{len(current_reminders)} reminders")

    # Step 2: Create missing lists
    print("  Creating lists...")
    for list_name in snapshot["lists"]:
        if list_name not in current_lists:
            try:
                run_reminders_cli("new-list", list_name)
                print(f"    Created list: {list_name}")
            except Exception as e:
                print(f"    Warning: Could not create list {list_name}: {e}")

    # Step 3: Recreate reminders
    print("  Creating reminders...")
    for reminder in snapshot["reminders"]:
        try:
            list_name = reminder.get("list", "Reminders")
            title = reminder.get("title", "")
            notes = reminder.get("notes", "")
            due_date = reminder.get("dueDate", "")
            priority = reminder.get("priority", 0)

            # Build the add command
            args = ["add", list_name, title, "--format", "json"]
            if notes:
                args.extend(["--notes", notes])
            if due_date:
                args.extend(["--due-date", due_date])
            if priority > 0:
                # Map Apple priority (1-9) to reminders-cli format
                # Apple: 1-4 = high, 5 = medium, 6-9 = low
                if priority <= 4:
                    args.extend(["--priority", "high"])
                elif priority == 5:
                    args.extend(["--priority", "medium"])
                else:
                    args.extend(["--priority", "low"])

            output = run_reminders_cli(*args)
            result = json.loads(output) if output.strip() else {}
            new_id = result.get("externalId")

            # Mark as completed if needed
            if reminder.get("isCompleted", False) and new_id:
                try:
                    run_reminders_cli("complete", list_name, new_id)
                except Exception as e:
                    print(f"    Warning: Could not mark as completed: {title} - {e}")

            print(f"    Created: {title}")
        except Exception as e:
            print(f"    Warning: Could not create reminder {reminder.get('title')}: {e}")

    print("\nRestore complete!")

    # Verify
    new_reminders = get_all_reminders()
    print(f"  Restored {len(new_reminders)} reminders (expected {len(snapshot['reminders'])})")


def print_snapshot_info(snapshot_path: Path) -> None:
    """Print detailed information about a snapshot."""
    snapshot = load_snapshot(snapshot_path)

    print(f"\nSnapshot: {snapshot_path.name}")
    print(f"Created: {snapshot['created_at']}")
    print(f"Version: {snapshot.get('version', 'unknown')}")
    print(f"\nMetadata:")
    metadata = snapshot.get("metadata", {})
    print(f"  Total lists: {metadata.get('total_lists', len(snapshot['lists']))}")
    print(f"  Total reminders: {metadata.get('total_reminders', len(snapshot['reminders']))}")
    print(f"  Completed: {metadata.get('completed_count', 'N/A')}")
    print(f"  Incomplete: {metadata.get('incomplete_count', 'N/A')}")

    print(f"\nLists:")
    for list_name in snapshot["lists"]:
        count = sum(1 for r in snapshot["reminders"] if r.get("list") == list_name)
        print(f"  - {list_name}: {count} reminders")

    print(f"\nSample reminders (first 5):")
    for reminder in snapshot["reminders"][:5]:
        status = "✓" if reminder.get("isCompleted") else "○"
        print(f"  {status} [{reminder.get('list', 'Unknown')}] {reminder.get('title', 'Untitled')}")


def main():
    """CLI interface for snapshot operations."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Apple Reminders Snapshot Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Create a snapshot:
    python snapshot.py create

  List all snapshots:
    python snapshot.py list

  Show snapshot details:
    python snapshot.py info snapshots/apple_reminders_20250101_120000.json

  Dry-run restore:
    python snapshot.py restore snapshots/apple_reminders_20250101_120000.json

  Actually restore (DANGEROUS):
    python snapshot.py restore --no-dry-run snapshots/apple_reminders_20250101_120000.json
"""
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Create subcommand
    subparsers.add_parser("create", help="Create a new snapshot")

    # List subcommand
    subparsers.add_parser("list", help="List all snapshots")

    # Info subcommand
    info_parser = subparsers.add_parser("info", help="Show snapshot details")
    info_parser.add_argument("snapshot", type=Path, help="Path to snapshot file")

    # Restore subcommand
    restore_parser = subparsers.add_parser("restore", help="Restore from a snapshot")
    restore_parser.add_argument("snapshot", type=Path, help="Path to snapshot file")
    restore_parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Actually perform the restore (DANGEROUS)"
    )
    restore_parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip confirmation prompt"
    )

    args = parser.parse_args()

    if args.command == "create":
        create_snapshot()

    elif args.command == "list":
        snapshots = list_snapshots()
        if not snapshots:
            print("No snapshots found.")
        else:
            print(f"Found {len(snapshots)} snapshot(s):\n")
            for path in snapshots:
                snapshot = load_snapshot(path)
                meta = snapshot.get("metadata", {})
                print(f"  {path.name}")
                print(f"    Created: {snapshot['created_at']}")
                print(f"    Reminders: {meta.get('total_reminders', 'N/A')}")
                print()

    elif args.command == "info":
        if not args.snapshot.exists():
            print(f"Error: Snapshot not found: {args.snapshot}")
            sys.exit(1)
        print_snapshot_info(args.snapshot)

    elif args.command == "restore":
        if not args.snapshot.exists():
            print(f"Error: Snapshot not found: {args.snapshot}")
            sys.exit(1)
        restore_snapshot(
            args.snapshot,
            dry_run=not args.no_dry_run,
            confirm=not args.no_confirm
        )


if __name__ == "__main__":
    main()
