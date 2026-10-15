"""Report wording found in the 2026-10-14 real-browser acceptance: duplicated lead phrases, doubled punctuation, English limits."""
from research_agent.report_explain import limitation_cn, limits_html
from research_agent.research_report import _after, _clause, avg_count


def test_model_text_joins_without_duplicated_leads_or_doubled_punctuation():
    assert _clause('处于相对弱势的状态。；') == '处于相对弱势的状态'
    assert _after('该因子衡量：该因子衡量个股接近程度', '该因子衡量') == '该因子衡量个股接近程度'      # only one lead is removed
    assert _after('因子值高意味着股价接近高点', '高因子值意味着', '因子值高意味着') == '股价接近高点'
    joined = '；'.join(_clause(x) for x in ['短期反转效应。', '流动性溢价；', '风险补偿']) + '。'
    assert '。；' not in joined and '；；' not in joined and joined.endswith('风险补偿。')
    assert avg_count(3897.03531) == '3897.0' and avg_count(None) is None and avg_count(float('nan')) is None


def test_one_fact_check_note_per_relabelled_mechanism():
    from research_agent.research_report import _merged_notes
    notes = ['机制“锚定”标为作者观点但原文引用未能核对，已改标为Agent假设。', '机制“锚定”的表述涉及作者观点但没有核对过的原文引用，已在正文标注。',
             '机制“扩散”的表述涉及作者观点但没有核对过的原文引用，已在正文标注。', '方向理由引用了作者观点，但没有核对过的原文引用，已在正文标注。']
    assert _merged_notes(notes) == [notes[0], notes[2], notes[3]]          # only the redundant duplicate is dropped


def test_stored_english_limits_are_rendered_in_chinese_and_unknown_text_is_kept():
    assert limitation_cn('raw prices may distort returns across corporate actions').startswith('使用未复权价格')
    assert limitation_cn('labels overlap (h=10): ICIR not annualised; effective independent dates ~ n/10') == \
        '相邻信号日的10日持有期标签相互重叠；ICIR未年化；有效独立样本约为 n/10。'
    assert limitation_cn('valid: insufficient valid dates') == 'valid：有效评价日不足。'
    assert limitation_cn('a new limitation') == 'a new limitation'                              # never dropped or invented
    html, md = limits_html(['true limit A', 'true limit A'], ['true independent OOS'])
    assert html.count('true limit A') == 1 and '尚未支持（下一步）' in html and '真正独立的样本外检验' in md
