#!/usr/bin/env bash
# Install the ISOLATED v1.0 Beta candidate from /root/v1beta_bundle.tgz. Production is never touched.
set -euo pipefail
umask 022
test -f /root/v1beta_bundle.tgz
if [ -e /opt/jijigua-quant-agent/v1beta ]; then
  printf '%s\n' 'Existing deployment: use the reviewed release_tool transaction; bootstrap made no change.' >&2
  exit 3
fi
mkdir /opt/jijigua-quant-agent/v1beta
tar xzf /root/v1beta_bundle.tgz -C /opt/jijigua-quant-agent/v1beta --no-same-owner --no-same-permissions
rm -f /root/v1beta_bundle.tgz
/usr/local/bin/python3 -m venv --without-pip /opt/jijigua-quant-agent/v1beta/.venv
/usr/local/bin/python3 -m pip --python /opt/jijigua-quant-agent/v1beta/.venv/bin/python install --quiet --no-cache-dir \
  -r /opt/jijigua-quant-agent/v1beta/requirements.lock -r /opt/jijigua-quant-agent/v1beta/requirements-research.lock pymupdf==1.24.14
chown -R root:root /opt/jijigua-quant-agent/v1beta
chmod -R u=rwX,go=rX /opt/jijigua-quant-agent/v1beta
/usr/bin/python3 -I /opt/jijigua-quant-agent/v1beta/deploy/configure_v1.py
/opt/jijigua-quant-agent/v1beta/.venv/bin/python -c "import fitz, numpy, pandas, matplotlib, jsonschema; print('venv ok', fitz.VersionBind, numpy.__version__, pandas.__version__)"
