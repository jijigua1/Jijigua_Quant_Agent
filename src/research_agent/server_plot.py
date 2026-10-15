"""Reviewed font selection and final GeorgeResearch notebook plot helpers; no engine I/O."""
from pathlib import Path
from matplotlib import font_manager
from matplotlib.ft2font import FT2Font

def annotate_group_returns(axis,bars,values):
    """Adapted from core_backtest.plotting.plot_final_result (d2b5a374...dd52)."""
    import numpy as np
    for bar,value in zip(bars,values):
        if np.isfinite(value):
            axis.annotate(f'{value:.2%}',(bar.get_x()+bar.get_width()/2,value),
                xytext=(0,4 if value>=0 else -12),textcoords='offset points',ha='center',fontsize=9)

def configure_chinese_font(font_path=None):
    """Find a real CJK font, including fonts installed after this kernel started."""
    required_characters = set(
        "单仓位回测表现净值策略全等权初始相对超额逐日双边换手率买卖绝金额之和组合价值持股票数目最大占比票上限（）："
    )
    if font_path is not None:
        candidates = [str(Path(font_path))]
    else:
        candidates = sorted(
            set(font_manager.findSystemFonts())
            | {font.fname for font in font_manager.fontManager.ttflist},
            key=lambda path: ("NotoSansCJK" not in path, "Regular" not in path, path),
        )
    for path in candidates:
        if not Path(path).is_file():
            continue
        try:
            charmap = FT2Font(path).get_charmap()
            if not all(ord(character) in charmap for character in required_characters):
                continue
            font_manager.fontManager.addfont(path)
            return font_manager.FontProperties(fname=path)
        except (OSError, RuntimeError):
            continue
    raise RuntimeError(
        "No font covers the Chinese chart labels. Install fonts-noto-cjk "
        "(apt-get install fonts-noto-cjk), or pass font_path to a CJK font file."
    )
