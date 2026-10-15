#!/usr/bin/env bash
# Rollback of enable_production_v1.sh. Restores the v0.8.2 entry and closes the rolling channel. Research results, snapshots,
# receipts, ledgers and audit logs are KEPT (evidence); nothing in real_time_product or the raw data is touched.
# Usage: rollback_production_v1.sh [--keep-cron]   (default: cron is also returned to the pre-change state)
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "must run as root"; exit 2; }
V1=/opt/jijigua-quant-agent/v1beta
LOG=/root/v1_rollback_$(date +%Y%m%d_%H%M%S).log
exec > >(tee -a "$LOG") 2>&1

echo "== close the 2026 rolling channel"
/usr/bin/python3 -I - "$V1/deploy/rolling/broker.json" <<'PY'
import json, os, sys
path = sys.argv[1]; c = json.load(open(path)); c['authorized'] = False
tmp = path + '.new'
with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
    json.dump(c, f, indent=1)
os.replace(tmp, path); print('broker authorized=False')
PY

echo "== restore the v0.8.2 production entry"
if [ -f /usr/local/bin/quant-agent-v082 ]; then
    cp -p /usr/local/bin/quant-agent-v082 /usr/local/bin/quant-agent
    sha256sum /usr/local/bin/quant-agent
fi

if [ "${1:-}" != "--keep-cron" ] && [ -f /etc/supervisor/conf.d/cron.conf ]; then
    echo "== remove the supervisord cron program (the daily 19:00 job stops again)"
    supervisorctl stop cron || true
    rm -f /etc/supervisor/conf.d/cron.conf
    supervisorctl reread; supervisorctl update
fi
echo "rollback log: $LOG"
