"""Stage 2 F (2026-10-15): trusted-IR numerical semantics are versioned and honoured; the warm-up overlap check is per stock."""
import numpy as np
import pandas as pd
import pytest

SIGN_MA = r"F_{i,t} = \operatorname{sign}(\operatorname{mean}_{k=0}^{19}(close_{i,t-k}) - \operatorname{mean}_{k=0}^{29}(close_{i,t-k}))"


def flat_panel():
    rng = np.random.default_rng(3)
    close = pd.DataFrame(10 * np.exp(np.cumsum(rng.normal(0, 0.02, (160, 4)), axis=0)), columns=['A.SZ', 'B.SZ', 'C.SH', 'D.SH'])
    close.iloc[60:100, 1] = 7.13                                        # a suspended stock: MA20 == MA30 in theory
    return {'close': close}


def test_each_definition_is_computed_under_its_own_semantics():
    from paper_agent import trusted_ir
    from paper_research.factor_ir import IR_SEMANTICS, LEGACY_SEMANTICS, evaluate, parse_formula, semantics_of
    ir = parse_formula(SIGN_MA)['ir']
    panels = flat_panel()
    new = trusted_ir.evaluate(ir, panels, {'close': 'close'})
    old = trusted_ir.evaluate(ir, panels, {'close': 'close'}, semantics=LEGACY_SEMANTICS)
    ref_old = evaluate(ir, panels, {'close': 'close'}, semantics=LEGACY_SEMANTICS)
    assert (new.iloc[89:100, 1] == 0).all()                              # version 2: numerical zero
    assert old.isna().equals(ref_old.isna())                              # version 1 is still computable exactly
    assert semantics_of({}) == LEGACY_SEMANTICS and semantics_of({'ir_semantics': IR_SEMANTICS}) == IR_SEMANTICS
    with pytest.raises(Exception):
        semantics_of({'ir_semantics': 'trusted-ir-semantics/99'})


def test_freezing_keeps_old_definition_hashes_and_records_new_versions():
    from paper_research.factor_ir import IR_SEMANTICS, parse_formula
    from rolling_test.factors import frozen_from_study
    ir = parse_formula(SIGN_MA)['ir']
    analysis = {'parameters': {'horizon': 1, 'n_groups': 5, 'standardization': 'raw'}, 'delivery_status': 'VERIFIED',
                'mode': 'real_data', 'study_id': 'a' * 32 + ':' + 'b' * 16, 'definition_sha256': 'c' * 64, 'data_sha256': 'd' * 64}
    legacy = {'kind': 'trusted_ir', 'ir': ir, 'symbols': {'close': 'close'}, 'warmup_observations': 30, 'executor_sha256': 'e' * 64}
    current = dict(legacy, ir_semantics=IR_SEMANTICS)
    a, b = frozen_from_study(analysis, legacy), frozen_from_study(analysis, current)
    assert 'ir_semantics' not in a['definition'] and b['definition']['ir_semantics'] == IR_SEMANTICS
    assert a['definition_sha256'] != b['definition_sha256']             # never reuses a receipt across semantics
    again = frozen_from_study(analysis, dict(legacy))
    assert again['definition_sha256'] == a['definition_sha256']         # a pre-versioning study keeps its SHA and receipts


def test_the_evaluator_recomputes_under_the_frozen_version():
    from paper_research.factor_ir import IR_SEMANTICS, LEGACY_SEMANTICS, parse_formula
    from rolling_test.factors import compute
    ir = parse_formula(SIGN_MA)['ir']
    base = dict(kind='ir', ir=ir, symbols={'close': 'close'}, warmup=30, standardization='raw')
    p = flat_panel()
    old, new = compute(base, p), compute(dict(base, ir_semantics=IR_SEMANTICS), p)
    from paper_agent import trusted_ir
    assert old.equals(trusted_ir.evaluate(ir, p, {'close': 'close'}, semantics=LEGACY_SEMANTICS).astype(float))
    assert (new.iloc[89:100, 1] == 0).all()


def test_the_warm_up_check_is_per_stock_not_only_count_and_sum():
    """Production audit P2: count/sum/sum_sq are unchanged when two stocks' values are swapped."""
    from rolling_test import code_weights
    codes = ['000001.SZ', '000002.SZ', '600000.SH']
    bare = [c.split('.')[0] for c in codes]
    row = np.array([0.5, -1.25, 2.0])
    swapped = row[[1, 0, 2]]
    assert len(row) == len(swapped) and row.sum() == swapped.sum() and (row ** 2).sum() == (swapped ** 2).sum()
    w_eval, w_study = code_weights(codes), code_weights(bare)
    assert np.array_equal(w_eval, w_study)                               # the same stock gets the same weight
    assert not np.allclose(w_eval @ row, w_study @ swapped)               # a swap is detected
    assert np.allclose(w_eval @ row, w_study @ row)


def test_a_crlf_study_file_gives_the_same_codes_to_the_warm_up_check(tmp_path):
    """Found 2026-10-15: on a CRLF factor_values.csv the last header code kept '\r', so that stock got another weight."""
    from rolling_test import code_weights
    from rolling_test.broker import Broker
    (tmp_path / 'f.csv').write_bytes(b'date,600000,600001\r\n2025-10-03,0.5,-1.25\r\n')
    codes, rows = Broker._tail_rows(None, tmp_path, 'f.csv', ['2025-10-03'])
    assert codes == ['600000', '600001'] and rows['2025-10-03'] == [0.5, -1.25]
    assert np.array_equal(code_weights(codes), code_weights(['600000.SH', '600001.SH']))
