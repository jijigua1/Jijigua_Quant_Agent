"""What the user may and may not get about 2026, stated by the program from the trusted broker configuration.

The model used to infer this on its own and told users that the 2026 rolling Test "still needs approval" while the
rolling channel was authorized and running (production audit 2026-10-14, P1). Four different things are kept apart:
raw 2026 market data (never readable by the Agent), the automatic rolling evaluation statistics (ROLLING_EXPOSED_TEST,
authorized or not by root configuration), the one-time independent test (its own approval contract) and algorithms the
evaluator does not run (model-written code -> UNSUPPORTED_STUDY).
"""
from __future__ import annotations

COMMON = ("2026原始行情和未来标签任何时候都不能由Agent读取，这一点与是否授权滚动评价无关。"
          "一次性独立测试（严格未见样本的单次Holdout）有单独的审批合同，与滚动评价不是一回事。"
          "滚动评价只运行受控评价器能重算的定义（固定因子、白名单DSL、可信IR）；经你审核的模型代码算法不会被评价器运行，"
          "这类研究的2026显示UNSUPPORTED_STUDY。标签未成熟的最近交易日显示N/A，不是缺数据。")


def describe(status):
    """status: the broker's side-effect-free status answer, or None when this process has no broker."""
    if not status or status.get('status') != 'OK':
        state = 'EVALUATOR_UNAVAILABLE'
        text = ("本会话没有连接2026滚动评价器（例如通过非chat命令或测试环境启动），因此本会话不能产生新的2026统计；"
                "已有报告中的2026结果仍可读取。" + COMMON)
    elif status.get('authorized'):
        state = 'ROLLING_AUTHORIZED'
        text = ("2026滚动Test已经授权并自动执行：新研究完成Train和Validation并交付已验证PKL后，若定义属于评价器可重算范围，"
                "程序会自动请求独立评价器计算2026滚动统计（ROLLING_EXPOSED_TEST，持续曝光，不是盲测），无需用户逐项再授权；"
                "统计按新的报告版本发布，签名回执可核验。" + COMMON)
    else:
        state = 'ROLLING_NOT_AUTHORIZED'
        text = ("本环境（例如预发布环境）的2026滚动评价未授权，研究的Test会显示NOT_AUTHORIZED；这不代表正式生产环境没有部署滚动Test。"
                + COMMON)
    if status and status.get('synthetic'):
        text = "【合成测试环境】" + text
    return {'state': state, 'text': text, 'contract': (status or {}).get('contract')}
