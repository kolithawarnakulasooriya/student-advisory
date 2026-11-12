"""Authenticated local inference only. No database, tools, cloud fallback or prompt logging."""
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path

import httpx
import numpy as np
import onnxruntime as ort
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from tokenizers import Tokenizer

ROOT=Path('/models')
LOCK=json.loads(Path('/app/models.lock.json').read_text())
for name,digest in LOCK['artifacts'].items():
    if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
        raise RuntimeError('Model artifact drift')
MODEL_SLOT=asyncio.Semaphore(1)
TOKEN=os.environ['INFERENCE_GATEWAY_TOKEN']
if len(TOKEN)<32: raise RuntimeError('Gateway token required')
OPTIONS=ort.SessionOptions(); OPTIONS.intra_op_num_threads=2; OPTIONS.inter_op_num_threads=1
RANKER=ort.InferenceSession(str(ROOT/'reranker/onnx/model.onnx'),OPTIONS,providers=['CPUExecutionProvider'])
TOKENIZER=Tokenizer.from_file(str(ROOT/'reranker/tokenizer.json'))
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)


def authenticate(authorization: str=Header(default='')):
    if not hmac.compare_digest(authorization,'Bearer '+TOKEN): raise HTTPException(401,'Unauthorized')


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')


class Embed(Input):
    texts:list[str]=Field(min_length=1,max_length=32)


class Chat(Input):
    messages:list[dict[str,str]]=Field(min_length=1,max_length=8)
    schema_definition:dict


class Rank(Input):
    query:str=Field(max_length=4000)
    documents:list[str]=Field(max_length=30)


async def ollama(path,payload=None):
    try:
        async with httpx.AsyncClient(timeout=180,trust_env=False) as client:
            r=await client.get('http://ollama:11434'+path) if payload is None else await client.post('http://ollama:11434'+path,json=payload)
            r.raise_for_status()
            return r.json()
    except Exception:
        raise HTTPException(503,'Local model unavailable') from None


async def one_model():
    async with MODEL_SLOT:
        yield


async def verify_models():
    data=await ollama('/api/tags')
    found={m['name']:m['digest'] for m in data['models']}
    if any(found.get(name)!=digest for name,digest in LOCK['models'].items()):
        raise HTTPException(503,'Model revision mismatch')


@app.get('/health',dependencies=[Depends(authenticate)])
async def health():
    await verify_models()
    return {'fingerprint':hashlib.sha256(json.dumps(LOCK,sort_keys=True).encode()).hexdigest(),
            'models':LOCK['models'],'dimension':768}


@app.post('/embed',dependencies=[Depends(authenticate),Depends(one_model)])
async def embed(body:Embed):
    await verify_models()
    if any(len(t)>16000 for t in body.texts): raise HTTPException(413,'Input too long')
    data=await ollama('/api/embed',{'model':'nomic-embed-text:v1.5','input':body.texts,
        'truncate':False,'keep_alive':0})
    vectors=data['embeddings']
    if len(vectors)!=len(body.texts) or any(len(v)!=768 or not all(np.isfinite(v)) for v in vectors):
        raise HTTPException(503,'Invalid embedding dimension')
    return {'embeddings':vectors}


@app.post('/chat',dependencies=[Depends(authenticate),Depends(one_model)])
async def chat(body:Chat):
    await verify_models()
    if any(set(m)-{'role','content'} or m.get('role') not in {'system','user','assistant'} or len(m.get('content',''))>24000 for m in body.messages):
        raise HTTPException(422,'Invalid messages')
    data=await ollama('/api/chat',{'model':'qwen3:0.6b','messages':body.messages,
        'format':body.schema_definition,'stream':False,'think':False,'keep_alive':0,
        'options':{'temperature':0,'num_ctx':4096,'num_predict':512,'seed':7}})
    return {'content':data['message']['content']}


@app.post('/rerank',dependencies=[Depends(authenticate),Depends(one_model)])
def rank(body:Rank):
    scores=[]
    for document in body.documents:
        encoding=TOKENIZER.encode(body.query,document)
        if len(encoding.ids)>512: raise HTTPException(413,'Reranker token budget exceeded')
        inputs={'input_ids':np.array([encoding.ids],dtype=np.int64),
                'attention_mask':np.array([encoding.attention_mask],dtype=np.int64),
                'token_type_ids':np.array([encoding.type_ids],dtype=np.int64)}
        output=RANKER.run(None,{i.name:inputs[i.name] for i in RANKER.get_inputs()})[0]
        scores.append(float(output.reshape(-1)[0]))
    return {'scores':scores}
