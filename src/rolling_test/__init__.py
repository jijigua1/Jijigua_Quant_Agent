"""ROLLING_EXPOSED_TEST: continuously exposed, automatically refreshed 2026 evaluation.

Three roles, three identities (Linux):
  broker    root parent of the CLI launcher; fixed operations only; never imports Agent code
  publisher quantpub; static (non-executing) pickle decode of the six daily_update fields
  evaluator quanteval; private snapshot -> aggregate statistics + HMAC receipt
The research Agent (quantagent) only sends "evaluate this completed study" and receives aggregates.
Synthetic mode runs the same functions in one process for tests; it is engineering evidence, not OS isolation.
"""
PROTOCOL = 'rolling-exposed-test/1'
CONTRACT = 'rolling-test-contract/1'
EVALUATION_TYPE = 'ROLLING_EXPOSED_TEST'
WARMUP_DAYS = 330          # pre-2026 observation rows in each snapshot (from the already exposed Validation span)
OVERLAP_DAYS = 60          # last Validation rows used for the history-consistency check
OVERLAP_PROJECTIONS = 3      # per-stock warm-up check: weighted sums with code-keyed weights (swap-sensitive)


def code_weights(codes, k=OVERLAP_PROJECTIONS):
    """(k, n) weights in [-1, 1) keyed by the bare stock code (exchange suffix dropped): independent of column order, so the
    evaluator's snapshot axis and the study's CSV header give the same weight to the same stock."""
    import hashlib
    import numpy as np
    out = np.empty((k, len(codes)))
    for j, c in enumerate(codes):
        h = hashlib.sha256(str(c).split('.')[0].encode('utf-8')).digest()
        for i in range(k):
            out[i, j] = int.from_bytes(h[4 * i:4 * i + 4], 'big') / 2 ** 31 - 1.0
    return out


MAX_WARMUP = 300           # factor warm-up the evaluator accepts (rows); leaves >=30 rows margin before the overlap
