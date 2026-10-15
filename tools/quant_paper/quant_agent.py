"""quant-agent (local client): start and follow research sessions on the shared server. Same core as quant-paper."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quant_paper import agent_main  # noqa: E402

if __name__ == '__main__':
    raise SystemExit(agent_main())
