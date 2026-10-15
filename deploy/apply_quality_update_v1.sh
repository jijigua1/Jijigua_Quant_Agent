#!/usr/bin/env bash
# v1.0 Beta quality update (paper autonomy, Economic Rationale, significance, G0–G4 explanation, HTML readability).
# Run as root ONLY after Kevin's explicit approval of docs/v1beta/QUALITY_UPDATE_APPROVAL_CN.md.
# Copies exactly 13 files (11 changed + 2 new) from the reviewed staging copy v1rc into production v1beta, after checking
# every SHA; backs up the 11 replaced files and the release manifest first. No cron, broker, launcher entry, user,
# permission, ledger, receipt, snapshot or Codex directory is touched. Rollback: deploy/rollback_quality_update_v1.sh <backup>.
#
# Usage: apply_quality_update_v1.sh APPROVAL_REF
set -euo pipefail
APPROVAL_REF=${1:?approval reference required}
V1=${QUALITY_UPDATE_REHEARSAL_ROOT:-/opt/jijigua-quant-agent/v1beta}   # override only to rehearse on a throwaway copy
VENV=/opt/jijigua-quant-agent/v1beta/.venv
RC=/opt/jijigua-quant-agent/v1rc
PROD_MANIFEST_SHA=342a78a95041803a8c00169495dbd6b8a87ca87fe6bc7fab4a5aaa924ccb4d9d     # current production release_v1_sha256.txt
CANDIDATE_MANIFEST_SHA=f3b8205954e99fb27458d5d8bf8510ad2d70d7c49e25385c998d98744046ca8b # docs/release_v1_sha256_candidate4.txt
FILES=(deploy/configure_v1.py deploy/launcher_v1.py src/paper_research/candidate.py src/research_agent/conversation.py
       src/research_agent/economic_rationale.py src/research_agent/evidence.py src/research_agent/interactive_report.py
       src/research_agent/paper_library.py src/research_agent/paper_tools.py src/research_agent/report_test_figures.py
       src/research_agent/research_report.py src/research_agent/report_explain.py src/research_agent/significance.py)
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP=/root/v1_quality_backup_$STAMP
LOG=/root/v1_quality_update_$STAMP.log
exec > >(tee -a "$LOG") 2>&1
step() { echo; echo "== [$(date '+%F %T')] $*"; }
[ "$(id -u)" = 0 ] || { echo "must run as root"; exit 2; }
[[ "$APPROVAL_REF" =~ ^[A-Za-z0-9._-]{8,80}$ ]] || { echo "bad approval reference"; exit 2; }

step "0 preflight: production equals its manifest; candidate manifest and staging files equal the reviewed SHAs"
[ "$(sha256sum "$V1/docs/release_v1_sha256.txt" | cut -d' ' -f1)" = "$PROD_MANIFEST_SHA" ] || { echo "production manifest changed: stop"; exit 3; }
(cd "$V1" && sha256sum --quiet -c docs/release_v1_sha256.txt)
[ "$(sha256sum "$RC/docs/release_v1_sha256_candidate4.txt" | cut -d' ' -f1)" = "$CANDIDATE_MANIFEST_SHA" ] || { echo "candidate manifest mismatch: stop"; exit 3; }
for f in "${FILES[@]}"; do
    want=$(awk -v p="$f" '$2==p{print $1}' "$RC/docs/release_v1_sha256_candidate4.txt")
    [ -n "$want" ] && [ "$(sha256sum "$RC/$f" | cut -d' ' -f1)" = "$want" ] || { echo "staging file not the reviewed version: $f"; exit 3; }
done
grep -q '"authorized": *true' "$V1/deploy/rolling/broker.json" || { echo "broker state unexpected: stop"; exit 3; }
! grep -q test_fault_injection "$V1/deploy/host.json" 2>/dev/null || { echo "production host.json has a test flag: stop"; exit 3; }

step "1 backup of every file that will be replaced, plus both manifests"
install -d -m 0700 "$BACKUP"
for f in "${FILES[@]}"; do
    [ -f "$V1/$f" ] && install -D -m 0644 "$V1/$f" "$BACKUP/$f"
done
cp -p "$V1/docs/release_v1_sha256.txt" "$BACKUP/release_v1_sha256.txt"
echo "$APPROVAL_REF" > "$BACKUP/APPROVAL_REF"
SUMS=$(cd "$BACKUP" && find . -type f -exec sha256sum {} + | sort -k2)    # listed before the list file exists
printf '%s\n' "$SUMS" > "$BACKUP/BACKUP_SHA256.txt"

step "2 install the 13 reviewed files (root:root 0644) and the new release manifest"
for f in "${FILES[@]}"; do
    install -D -o root -g root -m 0644 "$RC/$f" "$V1/$f.new.$STAMP"
    mv -f "$V1/$f.new.$STAMP" "$V1/$f"
done
cp -p "$V1/docs/release_v1_sha256.txt" "$V1/docs/release_v1_sha256.deploy3.txt"
install -o root -g root -m 0644 "$RC/docs/release_v1_sha256_candidate4.txt" "$V1/docs/release_v1_sha256.txt"
find "$V1/src" -name __pycache__ -prune -exec rm -rf {} +

step "3 post-check: all 171 release files equal the approved manifest"
(cd "$V1" && sha256sum --quiet -c docs/release_v1_sha256.txt)

step "4 smoke: imports with the production venv, then the synthetic OS-level rolling self-test"
SMOKE="import sys; sys.path[:0]=['$V1/src','$V1/src/rolling_test/vendor']
import research_agent.conversation, research_agent.research_report, research_agent.report_explain, research_agent.significance, paper_research.candidate
print('imports ok as', __import__('os').geteuid())"
if [ "$V1" = /opt/jijigua-quant-agent/v1beta ]; then
    runuser -u quantagent -- env -i HOME=/tmp PATH=/usr/bin:/bin "$VENV/bin/python" -I -B -c "$SMOKE"   # -I ignores PYTHONPATH: path set inline
else
    "$VENV/bin/python" -I -B -c "$SMOKE"                                                             # rehearsal copy under /root
fi
if [ "$V1" = /opt/jijigua-quant-agent/v1beta ]; then
    "$VENV/bin/python" -I "$V1/deploy/selftest_rolling.py"
else
    echo "rehearsal copy: OS-level rolling self-test skipped (it is pinned to the production path)"
fi

step "5 summary"
echo "approval $APPROVAL_REF; backup $BACKUP; log $LOG"
echo "rollback: $V1/deploy/rollback_quality_update_v1.sh $BACKUP"
