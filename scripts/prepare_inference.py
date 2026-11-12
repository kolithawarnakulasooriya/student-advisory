"""Download public pinned model artifacts; never download models during a student request."""
import hashlib
import json
import os
import secrets
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'local-data/inference'
IMAGE = 'ollama/ollama@sha256:910d0d8107b538fb0894e63163eb195de0cc7aefcbc666dc62d3b18f71124592'
MODELS = ['qwen3:0.6b','nomic-embed-text:v1.5']
REPOS = {'chat':'Qwen/Qwen3-0.6B','embedding':'nomic-ai/nomic-embed-text-v1.5',
         'reranker':'cross-encoder/ms-marco-MiniLM-L6-v2'}


def command(*args):
    return subprocess.check_output(list(args),text=True).strip()


def download(url,path):
    if path.exists(): return
    with urllib.request.urlopen(url,timeout=120) as response:
        path.write_bytes(response.read())


def main():
    CACHE.mkdir(parents=True,mode=0o755,exist_ok=True)
    CACHE.chmod(0o755)  # Public model artifacts; the credential files themselves remain 0600.
    key=CACHE/'gateway-token'
    if not key.exists():
        descriptor=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'w') as stream: stream.write(secrets.token_hex(32))
    env=CACHE/'inference.env'
    descriptor=os.open(env,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(descriptor,'w') as stream:
        stream.write('INFERENCE_GATEWAY_TOKEN='+key.read_text().strip()+'\n')
    lockpath=ROOT/'infra/inference/models.lock.json'
    previous=json.loads(lockpath.read_text()) if lockpath.exists() else {}
    model_manifest={'schema_version':1,'ollama_image':IMAGE,'models':{},'artifacts':{},'repositories':{}}
    # A short-lived bootstrap server has network for downloads, no published ports or student data.
    subprocess.run(['docker','run','-d','--name','advisory-model-bootstrap','--memory=2g',
        '-e','OLLAMA_NO_CLOUD=1','-v','advisory-models:/root/.ollama',IMAGE],check=True,stdout=subprocess.DEVNULL)
    try:
        import time
        for _ in range(60):
            status=subprocess.run(['docker','exec','advisory-model-bootstrap','ollama','list'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if status.returncode==0: break
            time.sleep(1)
        for name in MODELS:
            subprocess.run(['docker','exec','advisory-model-bootstrap','ollama','pull',name],
                           check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        tags=json.loads(command('docker','run','--rm','--network','container:advisory-model-bootstrap',
            'python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b',
            'python','-c',
            "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:11434/api/tags').read().decode())"))
        model_manifest['models']={m['name']:m['digest'] for m in tags['models'] if m['name'] in MODELS}
        model_manifest['ollama_version']=command('docker','exec','advisory-model-bootstrap','ollama','--version')
    finally:
        subprocess.run(['docker','rm','-f','advisory-model-bootstrap'],check=True,stdout=subprocess.DEVNULL)
    for role,repo in REPOS.items():
        old=previous.get('repositories',{}).get(role,{})
        if old.get('repo')==repo:
            revision=old['revision']
        else:
            with urllib.request.urlopen(f'https://huggingface.co/api/models/{repo}',timeout=30) as response:
                revision=json.load(response)['sha']
        model_manifest['repositories'][role]={'repo':repo,'revision':revision,
            'model_card':f'https://huggingface.co/{repo}/blob/{revision}/README.md',
            'license':'Apache-2.0','license_reference':f'https://huggingface.co/{repo}/blob/{revision}/README.md'}
        files=['tokenizer.json','tokenizer_config.json','config.json','README.md']
        if role=='reranker': files+=['onnx/model.onnx','special_tokens_map.json']
        for name in files:
            path=CACHE/role/name;path.parent.mkdir(parents=True,exist_ok=True)
            download(f'https://huggingface.co/{repo}/resolve/{revision}/{name}',path)
            model_manifest['artifacts'][f'{role}/{name}']=hashlib.sha256(path.read_bytes()).hexdigest()
        print('Prepared public model artifacts:',role,revision)
    if previous and model_manifest != previous:
        raise SystemExit('Prepared models differ from models.lock.json; runtime remains fail-closed. Review an explicit model release before changing the lock.')
    if not previous:
        lockpath.write_text(json.dumps(model_manifest,indent=2,sort_keys=True)+'\n')
    print('Inference manifest prepared; local gateway credentials were not printed.')


if __name__=='__main__': main()
