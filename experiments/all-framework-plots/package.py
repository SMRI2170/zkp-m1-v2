"""Bundle rendered figures, public tables, and report; full repo needed to regenerate."""
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[2]
files=list((ROOT/'week24/plots/all-frameworks').glob('*'))+list((ROOT/'week24/data/all-frameworks').glob('*'))
files+=[ROOT/'week24/12_全フレームワークの比較グラフ.md']
with zipfile.ZipFile(ROOT/'week24/plots/all-frameworks.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
    for p in sorted(files):
        if p.is_file():z.write(p,str(p.relative_to(ROOT)))
print('Created week24/plots/all-frameworks.zip (figures + public tables + report)')
