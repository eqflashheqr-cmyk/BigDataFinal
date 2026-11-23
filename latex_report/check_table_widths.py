# -*- coding: utf-8 -*-
"""Measure every tabular's natural width and attribute it to the float
that contains it, using a single forward scan of the source.
"""
import io, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

src = io.open('report.tex', 'r', encoding='utf-8').read()
io.open('_orig_report.tex', 'w', encoding='utf-8', newline='\n').write(src)

# ---- forward scan: record, for each tabular, the enclosing float -----
FLOAT_RE = re.compile(r'\\begin\{(table\*?|figure\*?)\}')
TAB_RE = re.compile(r'\\begin\{tabular\}')
LABEL_RE = re.compile(r'\\label\{([^}]*)\}')

tab_info = []          # (tabular_index, float_label, is_full_width)
cur_float_label = None
cur_float_full = False
depth = 0
tab_i = 0
pos = 0

# Walk the float environments to know the label of each.
float_spans = []
for m in FLOAT_RE.finditer(src):
    kind = m.group(1)
    end = src.find('\\end{%s}' % kind, m.end())
    if end < 0:
        continue
    blk = src[m.end():end]
    lm = LABEL_RE.search(blk)
    float_spans.append((m.start(), end, lm.group(1) if lm else '?', kind.endswith('*')))

for m in TAB_RE.finditer(src):
    tab_i += 1
    lab, full = '?', False
    for (s, e, l, f) in float_spans:
        if s <= m.start() <= e:
            lab, full = l, f
            break
    tab_info.append((tab_i, lab, full))

# ---- instrument ------------------------------------------------------
inst = src
n = [0]


def tab_repl(m):
    n[0] += 1
    return '\\MEASURE{TBL%02d}\\begin{tabular}' % n[0]


inst = TAB_RE.sub(tab_repl, inst)

idx = [0]


def close_repl(m):
    lab = 'TBL%02d' % (idx[0] + 1)
    idx[0] += 1
    return '\\end{tabular}\\ENDMEASURE{%s}' % lab


inst = re.sub(r'\\end\{tabular\}', close_repl, inst)

PROLOGUE = r'''
\makeatletter
\newsavebox{\@MCTR@box}
\def\MEASURE#1{\setbox\@MCTR@box=\hbox\bgroup}
\def\ENDMEASURE#1{\egroup\typeout{WIDTH #1 = \the\wd\@MCTR@box}}
\makeatother
'''
inst = inst.replace('\\begin{document}', PROLOGUE + '\\begin{document}', 1)
io.open('_instr_report.tex', 'w', encoding='utf-8', newline='\n').write(inst)

env = dict(os.environ)
env['TEXINPUTS'] = '.;E:/Projects/BigDataFinal/latex_template;;'
subprocess.run(['pdflatex', '-interaction=nonstopmode', '_instr_report.tex'],
               capture_output=True, text=True, env=env)

log = open('_instr_report.log', encoding='utf-8', errors='replace').read()
widths = re.findall(r'WIDTH (TBL\d+) = ([\d.]+)pt', log)

COLW = 241.14
TEXTW = 505.87

print('%-6s %-22s %-8s %10s %10s  %s' %
      ('meas', 'label', 'kind', 'width', 'limit', 'status'))
print('-' * 80)
bad = []
for i, (mid, w) in enumerate(widths):
    w = float(w)
    ti = tab_info[i] if i < len(tab_info) else (0, '?', False)
    lab, full = ti[1], ti[2]
    limit = TEXTW if full else COLW
    over = w - limit
    status = 'ok'
    if over > 0.5:
        status = '*** OVER by %.2f pt' % over
        bad.append((mid, lab, 'table*' if full else 'table', w, over))
    print('%-6s %-22s %-8s %10.2f %10.2f  %s' %
          (mid, lab, 'table*' if full else 'table', w, limit, status))

print()
if bad:
    print('=== TABLES WIDER THAN THEIR COLUMN ===')
    for mid, lab, kind, w, over in bad:
        print('  %-6s %-22s (%s) %8.2f pt  over by %6.2f pt' % (mid, lab, kind, w, over))
else:
    print('=== EVERY TABLE FITS ===')
print()
print('measured %d of %d tabulars' % (len(widths), len(tab_info)))
