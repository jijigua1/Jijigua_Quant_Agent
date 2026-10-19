"""LaTeX from validated executed definitions; offline Matplotlib mathtext SVG."""
import base64
import io
from .contracts import ContractError, fingerprint

VERSION='1.0.0'

def formula(definition, standardization='raw'):
    fields={'open':'O_{t,i}','high':'H_{t,i}','low':'L_{t,i}','close':'C_{t,i}','volume':'V_{t,i}'}
    if definition.get('kind') in ('approved_implementation','trusted_ir'):
        # LaTeX rendered by the trusted Factor-IR renderer from the frozen research definition, not by model text.
        latex=definition['latex'].removeprefix('f_{t,i}=')
        return 'f_{t,i}='+(r'\mathrm{ZCS}\left('+latex+r'\right)' if standardization=='zscore' else latex)
    if 'expression' in definition:
        from .factor_expression import inspect
        inspect(definition['expression'])
        rendered=[]
        for node in definition['expression']['nodes']:
            op=node['op'];args=[rendered[i] for i in node.get('args',[])];w=node.get('window')
            if op=='field':s=fields[node['field']]
            elif op=='constant':
                s=str(node['value'])
                if 'e' in s.lower():
                    coefficient,power=s.lower().split('e');s=coefficient+r'\times 10^{'+str(int(power))+'}'
            elif op=='neg':s=r'-\left('+args[0]+r'\right)'
            elif op=='abs':s=r'\left|'+args[0]+r'\right|'
            elif op in {'add','sub','mul'}:s=r'\left('+args[0]+{'add':'+','sub':'-','mul':r'\cdot '}[op]+args[1]+r'\right)'
            elif op=='div':s=r'\frac{'+args[0]+'}{'+args[1]+'}'
            elif op in {'min','max'}:s='\\'+op+r'\left('+','.join(args)+r'\right)'
            elif op=='returns':s=r'\left(\frac{'+args[0]+r'}{\mathrm{Delay}_{'+str(w)+r'}\left('+args[0]+r'\right)}-1\right)'
            elif op=='diff':s=r'\left('+args[0]+r'-\mathrm{Delay}_{'+str(w)+r'}\left('+args[0]+r'\right)\right)'
            else:
                names={'delay':'Delay','rolling_mean':'Mean','rolling_std':'Std','rolling_rank':'RankTS','rolling_corr':'CorrTS','cs_rank':'RankCS','cs_zscore':'ZCS'}
                if op not in names:raise ContractError('unsupported math operator')
                s=r'\mathrm{'+names[op]+'}'+('_{'+str(w)+'}' if w else '')+r'\left('+','.join(args)+r'\right)'
            rendered.append(s)
        latex=rendered[definition['expression']['output']]
    else:
        w=definition['lookback'];ret=r'\left(\frac{C_{t,i}}{C_{t-'+str(w)+r',i}}-1\right)'
        if definition['factor_id']=='reversal':latex='-'+ret
        elif definition['factor_id']=='volume_stall':
            latex=r'\max\left(\frac{V_{t,i}}{\frac{1}{'+str(w)+r'}\sum_{k=1}^{'+str(w)+r'}V_{t-k,i}}-1,0\right)\exp\left(-\frac{\left|'+ret+r'\right|}{0.02}\right)'
        else:raise ContractError('unsupported fixed math definition')
        standardization=definition['standardization']
    if standardization=='zscore':latex=r'\mathrm{ZCS}\left('+latex+r'\right)'
    elif standardization!='raw':raise ContractError('unsupported math standardization')
    return 'f_{t,i}='+latex

def render(definition,standardization='raw'):
    if definition.get('kind') == 'isolated_python':
        import html
        from paper_agent.algorithm_bundle import validate
        contract=validate(definition['bundle'])
        text=contract['formula']
        return dict(latex=text,definition_sha256=fingerprint(definition),renderer='Escaped confirmed algorithm contract',
            renderer_version='1',formula_version=VERSION,
            html='<pre class="algorithm-formula">'+html.escape(text)+'</pre><p>冻结 Python 算法 · SHA '+
                 html.escape(definition['bundle']['source_sha256'])+'</p>')
    from matplotlib.mathtext import math_to_image
    latex=formula(definition,standardization)
    b=io.BytesIO();math_to_image('$'+latex+'$',b,format='svg',dpi=144,color='#243342')
    return dict(latex=latex,definition_sha256=fingerprint(definition),renderer='Matplotlib mathtext / offline SVG',
        renderer_version=__import__('matplotlib').__version__,formula_version=VERSION,
        html='<img class="math-svg" alt="因子数学公式" src="data:image/svg+xml;base64,'+base64.b64encode(b.getvalue()).decode()+'">')
