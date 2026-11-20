"""Stage the installed Ollama CPU runtime and an already pulled model for Docker."""
import hashlib
import json
import shutil
from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--models', type=Path, required=True)
parser.add_argument('--runtime', type=Path, default=Path('/usr/local'))
args = parser.parse_args()
out = Path('packaging/local-embeddings')
out.mkdir(parents=True, exist_ok=True)
shutil.copytree(args.runtime / 'lib/ollama', out / 'lib/ollama',
    ignore=shutil.ignore_patterns('cuda*', 'vulkan'), dirs_exist_ok=True)
(out/'bin').mkdir(exist_ok=True)
shutil.copy2(args.runtime/'bin/ollama',out/'bin/ollama')
manifest = Path('manifests/registry.ollama.ai/library/embeddinggemma/300m')
source = args.models / manifest
if hashlib.sha256(source.read_bytes()).hexdigest() != '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1':
    raise RuntimeError('EmbeddingGemma manifest differs from the packaged revision')
content = json.loads(source.read_text())
for entry in [content['config'], *content['layers']]:
    digest = entry['digest'].replace(':','-')
    target = out/'models/blobs'/digest
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.models/'blobs'/digest,target)
    if hashlib.sha256(target.read_bytes()).hexdigest() != entry['digest'].split(':')[1]:
        raise RuntimeError('Model blob checksum mismatch')
(out/'models'/manifest).parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(source,out/'models'/manifest)
files=sorted(p for p in out.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
(out/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n' for p in files))
print('Staged CPU runtime and model; manifest SHA256:',hashlib.sha256(source.read_bytes()).hexdigest())
