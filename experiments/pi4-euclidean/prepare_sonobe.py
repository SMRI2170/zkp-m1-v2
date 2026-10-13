"""Verify cached PR246+arkworks0.6 source; create missing source without overwriting."""
import hashlib,json,shutil,subprocess,tarfile,tempfile,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[2]
fixed=root/'.cache/week23/sources/sonobe-hypernova-fixed-v1'
original=root/'.cache/week23/sources/sonobe-hypernova-9c4e61f8'
head='9c4e61f8d1a5be87c00f28838a0ef657a3cf479f'
audit=json.loads((root/'week24/manifests/pr246-source-audit.json').read_text())['upstream_source_sha256']
def verify(path,files):
    for n,h in files.items():
        if hashlib.sha256((path/n).read_bytes()).hexdigest()!=h:
            raise RuntimeError(f'Source mismatch preserved: {n}')
if not fixed.exists():
    if not original.exists():
        original.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=original.parent) as tmp:
            archive=Path(tmp)/'source.tar.gz'
            urllib.request.urlretrieve(f'https://codeload.github.com/ethereum/sonobe/tar.gz/{head}',archive)
            with tarfile.open(archive) as tar:
                tar.extractall(tmp,filter='data')
            unpacked=Path(tmp)/f'sonobe-{head}'
            verify(unpacked,audit)
            shutil.move(str(unpacked),original)
    verify(original,audit)
    subprocess.run(['python3',root/'week23/poc/sonobe-current/prepare_hypernova.py'],check=True,cwd=root)
expected=json.loads(Path(__file__).with_name('sonobe').joinpath('source-sha256.json').read_text())
verify(fixed,expected)
print(json.dumps({'phase':'source-verified','head':head,'patched_files_verified':len(expected),'witness_or_keys_read':False}))
