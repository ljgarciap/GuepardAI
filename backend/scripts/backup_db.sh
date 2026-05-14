#!/bin/bash
# ─────────────────────────────────────────────────────
# GuepardAI - Automated Database Backup Script (v1.0)
# ─────────────────────────────────────────────────────

# Variables
BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
CONTAINER_NAME="guepard_db"
DB_NAME="guepard"
DB_USER="postgres"

# Create backup directory if it doesn't exist
mkdir -p $BACKUP_DIR

echo "--- Starting Backup for $DB_NAME ($TIMESTAMP) ---"

# Run pg_dump inside the docker container
docker exec $CONTAINER_NAME pg_dump -U $DB_USER $DB_NAME > $BACKUP_DIR/backup_$TIMESTAMP.sql

if [ $? -eq 0 ]; then
    echo "✔ Backup successful: $BACKUP_DIR/backup_$TIMESTAMP.sql"
    # Keep only the last 7 days of backups
    find $BACKUP_DIR -type f -name "*.sql" -mtime +7 -delete
    echo "✔ Cleaned up backups older than 7 days."
else
    echo "✘ ERROR: Backup failed."
    exit 1
fi

echo "--- Process Completed ---"
