#!/usr/bin/env bash
# One-shot production enablement of Research Agent v1.0 Beta + daily market-data recovery + automatic 2026 rolling Test.
# Run as root ONLY after Kevin's explicit approval of docs/v1beta/PRODUCTION_ENABLEMENT_CN.md. Each step is idempotent and
# logged; any failed check stops the script before the next step. Rollback: deploy/rollback_production_v1.sh.
#
# Usage: enable_production_v1.sh APPROVAL_REF BACKFILL_DATE... (each BACKFILL_DATE is YYYYMMDD[:no-email])
# Example: enable_production_v1.sh KEVIN-20261013-V1-PROD 20261012:no-email 20261013
set -euo pipefail
APPROVAL_REF=${1:?approval reference required}; shift
V1=/opt/jijigua-quant-agent/v1beta
LAUNCHER=/usr/local/bin/quant-agent
LAUNCHER_V082_SHA=b3655e36fd676677a46745a8d95a4d2034857b6206a78dceadaaa518cf6ec009
BROKER=$V1/deploy/rolling/broker.json
CRON_CONF=/etc/supervisor/conf.d/cron.conf
LOG=/root/v1_enable_$(date +%Y%m%d_%H%M%S).log
exec > >(tee -a "$LOG") 2>&1
step() { echo; echo "== [$(date '+%F %T')] $*"; }
[ "$(id -u)" = 0 ] || { echo "must run as root"; exit 2; }
[[ "$APPROVAL_REF" =~ ^[A-Za-z0-9._-]{8,80}$ ]] || { echo "bad approval reference"; exit 2; }

step "0 preflight: release code SHA, v0.8.2 launcher unchanged, identities present"
(cd "$V1" && sha256sum --quiet -c docs/release_v1_sha256.txt)
current=$(sha256sum "$LAUNCHER" | cut -d' ' -f1)
if [ "$current" != "$LAUNCHER_V082_SHA" ] && ! grep -q "launcher_v1.py" "$LAUNCHER"; then
    echo "quant-agent is neither v0.8.2 nor v1: stop"; exit 3; fi
for u in quantagent quantpub quanteval; do id "$u" >/dev/null; done
[ "$(stat -c '%U:%G %a' /srv/jijigua-quant-agent/v1beta_rolling/rolling.key)" = "root:quanteval 440" ]
[ "$(stat -c '%U:%G %a' /srv/jijigua-quant-agent/v1beta_rolling/snapshots)" = "root:quanteval 750" ]
[ "$(stat -c '%U:%G %a' /srv/jijigua-quant-agent/v1beta_rolling/receipts)" = "root:quantagent 750" ]
test -d /srv/jijigua-quant-agent/test_evaluator/phase3c_v1        # Codex one-time evaluation: present and never touched below

step "1 daily market data: run cron under supervisord (restarts with the container); real_time_product untouched"
if [ ! -f "$CRON_CONF" ]; then
    printf '%s\n' '[program:cron]' 'command=/usr/sbin/cron -f' 'autorestart=true' 'redirect_stderr=true' \
        'stdout_logfile=/dev/stdout' 'stdout_logfile_maxbytes=0' > "$CRON_CONF"
    chmod 0644 "$CRON_CONF"
fi
pgrep -x cron >/dev/null && ! supervisorctl status cron 2>/dev/null | grep -q RUNNING && { echo "an unmanaged cron is running: stop"; exit 4; }
supervisorctl reread
supervisorctl update cron
sleep 2
supervisorctl status cron | grep -q RUNNING
crontab -l | grep -q '^0 19 \* \* \* /home/real_time_product/scripts/run_daily_pipeline.sh'

step "2 backfill missed trading days with the product's own entry point (its flock prevents overlap)"
for spec in "$@"; do
    d=${spec%%:*}; [[ "$d" =~ ^2026[0-9]{4}$ ]] || { echo "bad date $spec"; exit 5; }
    extra=(); [ "${spec#*:}" = "no-email" ] && extra=(--no-email)
    /home/real_time_product/scripts/run_daily_pipeline.sh --date "$d" "${extra[@]}" >> /hy-tmp/logs/daily_pipeline/cron.log 2>&1
    tail -n 3 /hy-tmp/logs/daily_pipeline/cron.log
    grep -q "PIPELINE_DONE target_date=$d status=success\|PIPELINE_SKIPPED.*$d" /hy-tmp/logs/daily_pipeline/cron.log
done
# the product's own interpreter (numpy 2 pickles); the last day must cover >= 90% of the prior-20-day median, as the publisher requires
/usr/local/bin/python -I -c "
import pandas as pd
c = pd.read_pickle('/hy-tmp/data/daily_update/close.pkl'); n = c.notna().sum(axis=1); ratio = n.iloc[-1] / n.iloc[-21:-1].median()
print('daily_update close last date:', c.index.max(), 'codes', int(n.iloc[-1]), 'coverage vs prior-20 median', round(float(ratio), 4))
assert ratio >= 0.9, 'last day incomplete'"

step "3 production entry: quant-agent -> v1.0 Beta (v0.8.2 kept as quant-agent-v082 for rollback)"
[ -f /usr/local/bin/quant-agent-v082 ] || cp -p "$LAUNCHER" /usr/local/bin/quant-agent-v082
printf '%s\n' '#!/bin/sh' '# Research Agent v1.0 Beta (approved '"$APPROVAL_REF"'); v0.8.2: /usr/local/bin/quant-agent-v082' \
    "exec /usr/bin/python3 -I $V1/deploy/launcher_v1.py \"\$@\"" > "$LAUNCHER.new"
chmod 0755 "$LAUNCHER.new"; chown root:root "$LAUNCHER.new"; mv -f "$LAUNCHER.new" "$LAUNCHER"

step "4 2026 rolling Test: authorize the reviewed broker (ROLLING_EXPOSED_TEST; one-time phase3c ledger not used)"
/usr/bin/python3 -I - "$BROKER" "$APPROVAL_REF" <<'PY'
import json, os, sys
path, ref = sys.argv[1], sys.argv[2]
c = json.load(open(path))
assert c['synthetic'] is False and c['source_root'] == '/hy-tmp/data/daily_update'
c.update(authorized=True, approval_ref=ref)
tmp = path + '.new'
with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
    json.dump(c, f, indent=1)
os.replace(tmp, path)
print('broker authorized', ref)
PY

step "5 summary"
supervisorctl status cron
head -3 "$LAUNCHER"
echo "log: $LOG"
echo "next: first real evaluation (docs/v1beta/PRODUCTION_ENABLEMENT_CN.md section 5)"
