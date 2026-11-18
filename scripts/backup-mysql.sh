#!/usr/bin/env bash
# Back up the production FarmMarket MySQL database.
#
# Usage (from the repo root, with the prod stack running):
#   ./scripts/backup-mysql.sh
#
# Writes a timestamped, gzipped dump to ./backups/ and deletes dumps older
# than 7 days. Safe to run repeatedly. The password is never read or printed
# by this script: mysqldump runs inside the db container, where
# MYSQL_ROOT_PASSWORD is already set as an environment variable.
#
# Restore (mysqldump output drops each table before recreating it, so this
# overwrites the current database — use with care):
#   gunzip -c backups/farmmarket-<timestamp>.sql.gz | docker compose -f docker-compose.prod.yml exec -T db sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" farmmarket_db'
#
# Suggested cron (daily at 03:00, from the repo root):
#   0 3 * * * cd /srv/farmmarket && ./scripts/backup-mysql.sh >> backups/backup.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="./backups"
mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
FILE="$BACKUP_DIR/farmmarket-$TIMESTAMP.sql.gz"

docker compose -f docker-compose.prod.yml exec -T db sh -c \
  'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction farmmarket_db' \
  | gzip > "$FILE"

# Keep the last 7 days of dumps.
find "$BACKUP_DIR" -name 'farmmarket-*.sql.gz' -mtime +7 -delete

echo "Backup written to $FILE"
