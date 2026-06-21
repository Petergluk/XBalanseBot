#!/bin/bash

# Load environment variables from .env.prod
if [ -f .env.prod ]; then
    # Extract DATABASE_URL, ignoring comments and empty lines
    DATABASE_URL=$(grep -E "^DATABASE_URL=" .env.prod | cut -d'=' -f2-)
fi

# Fallback to .env if .env.prod doesn't have it
if [ -z "$DATABASE_URL" ] && [ -f .env ]; then
    DATABASE_URL=$(grep -E "^DATABASE_URL=" .env | cut -d'=' -f2-)
fi

if [ -z "$DATABASE_URL" ]; then
    echo "❌ Error: DATABASE_URL not found in .env.prod or .env"
    exit 1
fi

# Check if pg_dump is installed
if ! command -v pg_dump &> /dev/null; then
    echo "❌ Error: pg_dump is not installed."
    echo "💡 To install it on macOS, run: brew install libpq"
    echo "   Then link it: brew link --force libpq"
    exit 1
fi

BACKUP_DIR="data/backups"
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.sql"

echo "[+] Creating database backup from: ${DATABASE_URL%%@*}@..."
pg_dump "$DATABASE_URL" > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "✅ Backup successfully created at: $BACKUP_FILE"
    # Compress the file
    gzip "$BACKUP_FILE"
    echo "📦 Compressed backup: ${BACKUP_FILE}.gz"
else
    echo "❌ Error: pg_dump failed."
    rm -f "$BACKUP_FILE"
    exit 1
fi
