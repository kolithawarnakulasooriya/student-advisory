"""Verify pinned inputs, start private models, and check authenticated readiness.

--build explicitly constructs and records a local image from hash-checked inputs.
Subsequent starts reject changes to that image. No credentials are printed.
"""
import argparse
import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def command(*args):
    return subprocess.check_output(args,cwd=ROOT,text=True).strip()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',action='store_true')
    args=parser.parse_args()
    runtime=json.loads((ROOT/'infra/inference/runtime.lock.json').read_text())
    for name,expected in runtime['sources'].items():
        if hashlib.sha256((ROOT/'infra/inference'/name).read_bytes()).hexdigest()!=expected:
            raise SystemExit('Inference runtime source drift: '+name)
    local=ROOT/'local-data/inference/runtime-observed.json'
    if args.build:
        subprocess.run(['docker','compose','--profile','inference','build','inference-gateway'],cwd=ROOT,check=True)
        actual=json.loads(command('docker','image','inspect','advisory-inference:0.4'))[0]
        local.write_text(json.dumps({'image_id':actual['Id'],'platform':actual['Os']+'/'+actual['Architecture'],'sources':runtime['sources']},indent=2)+'\n')
    if not local.exists():
        raise SystemExit('Build the pinned local runtime once with --build before starting.')
    observed=json.loads(local.read_text())
    actual=json.loads(command('docker','image','inspect','advisory-inference:0.4'))[0]
    if observed['image_id']!=actual['Id'] or observed['sources']!=runtime['sources']:
        raise SystemExit('Local runtime image drift; review the pinned build before rebuilding.')
    subprocess.run(['docker','compose','--profile','inference','up','-d','ollama'],cwd=ROOT,check=True)
    subprocess.run(['docker','compose','--profile','inference','up','-d','--force-recreate','inference-gateway'],cwd=ROOT,check=True)
    secret=(ROOT/'local-data/inference/gateway-token').read_text().strip()
    request=urllib.request.Request('http://127.0.0.1:11435/health',headers={'Authorization':'Bearer '+secret})
    manifest=json.loads((ROOT/'infra/inference/models.lock.json').read_text())
    expected=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
    for _ in range(30):
        try:
            with urllib.request.urlopen(request,timeout=2) as response:data=json.load(response)
            if data.get('fingerprint')!=expected or data.get('dimension')!=768:
                raise SystemExit('Model manifest mismatch')
            print('Private inference ready:',observed['platform'],observed['image_id'])
            return
        except (urllib.error.URLError,TimeoutError,OSError):time.sleep(1)
    raise SystemExit('Private inference unavailable; no mock fallback was selected.')


if __name__=='__main__':main()
