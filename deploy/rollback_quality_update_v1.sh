#!/usr/bin/env bash
# Roll back deploy/apply_quality_update_v1.sh: restore the 11 replaced files and the previous release manifest from the
# backup, remove the 2 files the update added, and verify the 169-file production manifest again. Research runs, report
# revisions, receipts, ledgers, cron, broker and launcher are not touched (revisions rendered by the update stay as records).
#
# Usage: rollback_quality_update_v1.sh /root/v1_quality_backup_<stamp>
set -euo pipefail
BACKUP=${1:?backup directory required}
V1=${QUALITY_UPDATE_REHEARSAL_ROOT:-/opt/jijigua-quant-agent/v1beta}   # override only to rehearse on a throwaway copy
PROD_MANIFEST_SHA=342a78a95041803a8c00169495dbd6b8a87ca87fe6bc7fab4a5aaa924ccb4d9d
ADDED=(src/research_agent/report_explain.py src/research_agent/significance.py)
LOG=/root/v1_quality_rollback_$(date +%Y%m%d_%H%M%S).log
exec > >(tee -a "$LOG") 2>&1
[ "$(id -u)" = 0 ] || { echo "must run as root"; exit 2; }
[ -f "$BACKUP/BACKUP_SHA256.txt" ] || { echo "not a backup directory"; exit 2; }
(cd "$BACKUP" && sha256sum --quiet -c BACKUP_SHA256.txt)
[ "$(sha256sum "$BACKUP/release_v1_sha256.txt" | cut -d' ' -f1)" = "$PROD_MANIFEST_SHA" ] || { echo "backup manifest is not the pre-update one"; exit 3; }

echo "== restore replaced files"
(cd "$BACKUP" && find deploy src -type f) | while read -r f; do
    install -D -o root -g root -m 0644 "$BACKUP/$f" "$V1/$f"
done
for f in "${ADDED[@]}"; do
    [ -f "$BACKUP/$f" ] || rm -f "$V1/$f"           # only files the update added (absent from the backup)
done
install -o root -g root -m 0644 "$BACKUP/release_v1_sha256.txt" "$V1/docs/release_v1_sha256.txt"
find "$V1/src" -name __pycache__ -prune -exec rm -rf {} +

echo "== verify: production equals the pre-update 169-file manifest"
(cd "$V1" && sha256sum --quiet -c docs/release_v1_sha256.txt)
echo "rollback complete; log $LOG"
