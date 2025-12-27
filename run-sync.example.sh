#!/bin/bash
# Wrapper script for launchd to run sync with proper environment
#
# Copy this file to run-sync.sh and fill in your values:
#   cp run-sync.example.sh run-sync.sh
#   chmod +x run-sync.sh

cd /path/to/supernote-apple-reminders-sync

export SUPERNOTE_DB_USER='supernote'
export SUPERNOTE_DB_PASSWORD='your-password-here'
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# Run sync
exec /opt/homebrew/bin/python3 -m src.main sync
