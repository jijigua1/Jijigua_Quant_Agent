"""Isolated-deployment runner (quantagent): put the candidate source on sys.path, then run the Agent CLI."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'src' / 'rolling_test' / 'vendor')]
from research_agent.cli import main  # noqa: E402

sys.exit(main(sys.argv[1:]))
