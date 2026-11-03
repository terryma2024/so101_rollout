"""Optional lossless diagnostics: bounded nonblocking enqueue, one disk writer.

No model sampling or hardware APIs. A missing/unclean status is incomplete.
Diagnostics are never a reason to stop or change robot control.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
import time


class InferenceRecorder:
    def __init__(self, path, *, max_items=256, max_bytes=128*1024*1024):
        if max_items<=0 or max_bytes<=0:raise ValueError('Positive recording limits required')
        self.path=Path(path);self.max_bytes=max_bytes
        self._queue=Queue(maxsize=max_items);self._lock=Lock();self._stop=Event()
        self._bytes=0;self._accepted=0;self._written=0;self._dropped=0
        self._owns_path=False;self._errors=[];self._closed=False;self._close_timeout=False;self._thread=None
        self._wall_origin=time.time();self._monotonic_origin=time.perf_counter()
        try:
            self.path.mkdir(parents=True,exist_ok=False)
            self._owns_path=True
            self._save_status() # crash before clean close remains incomplete
            self._thread=Thread(target=self._run,name='SmolVLA-diagnostics-writer',daemon=True)
            self._thread.start()
        except Exception as exc:self.error(exc)

    def error(self, exc):
        with self._lock:
            if len(self._errors)<20:self._errors.append(f'{type(exc).__name__}: {exc}')

    def submit(self, kind, metadata, arrays=None):
        """Ownership transfers to writer; callers must not mutate array payloads."""
        arrays=arrays or {};size=sum(x.nbytes for x in arrays.values())
        # Metadata is small on the control path (<=2 queues of horizon rows).
        size+=len(json.dumps(metadata,default=str).encode())
        with self._lock:
            if self._closed or self._thread is None or self._errors or self._bytes+size>self.max_bytes:
                self._dropped+=1;return False
            identifier=self._accepted
            try:self._queue.put_nowait((identifier,kind,metadata,arrays,size))
            except Full:self._dropped+=1;return False
            self._accepted+=1;self._bytes+=size
        return True

    def status(self):
        with self._lock:
            return dict(format_version=1,complete=bool(self._closed and not self._close_timeout and
                not self._errors and not self._dropped and self._accepted==self._written),
                closed=self._closed,accepted=self._accepted,written=self._written,dropped=self._dropped,
                errors=list(self._errors),pending_bytes=self._bytes,queue_items=self._queue.qsize(),
                max_bytes=self.max_bytes,max_items=self._queue.maxsize,close_timeout=self._close_timeout,
                wall_origin=self._wall_origin,monotonic_origin=self._monotonic_origin,
                timestamp_semantics='Host monotonic timestamps; observed_at is request dispatch time, not a measured camera exposure timestamp.')

    def _save_status(self):
        if not self._owns_path:return
        temporary=self.path/'status.json.tmp';temporary.write_text(json.dumps(self.status(),indent=2));temporary.replace(self.path/'status.json')

    def _write(self,item):
        import numpy as np
        identifier,kind,metadata,arrays,_=item
        filename=self.path/f'{identifier:08d}-{kind}.npz'
        with filename.open('wb') as f:np.savez_compressed(f,metadata=np.asarray(json.dumps(metadata,default=str)),**arrays)

    def _run(self):
        while not self._stop.is_set() or not self._queue.empty():
            try:item=self._queue.get(timeout=.05)
            except Empty:continue
            try:
                self._write(item)
                with self._lock:self._written+=1
            except Exception as exc:self.error(exc)
            finally:
                with self._lock:self._bytes-=item[4]
        try:self._save_status()
        except Exception as exc:self.error(exc)

    def close(self,timeout=5.):
        with self._lock:self._closed=True
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                with self._lock:self._close_timeout=True
        try:self._save_status()
        except Exception as exc:self.error(exc)


def array_tree(value, prefix='value'):
    """Freeze lossless numpy/torch tree into numeric arrays plus JSON schema.

    Called only on the inference worker. Tensors are stored as raw uint8 bytes
    so bfloat16 and bool remain lossless without numpy dtype conversion.
    """
    import numpy as np
    arrays={}
    def pack(x,key):
        if isinstance(x,dict):return dict(kind='dict',items={str(k):pack(v,key+'.'+str(k)) for k,v in x.items()})
        if isinstance(x,(list,tuple)):return dict(kind='tuple' if isinstance(x,tuple) else 'list',items=[pack(v,key+f'.{i}') for i,v in enumerate(x)])
        if hasattr(x,'detach'):
            tensor=x.detach().contiguous().cpu();arrays[key]=tensor.reshape(-1).view(__import__('torch').uint8).numpy().copy()
            return dict(kind='tensor',key=key,dtype=str(tensor.dtype).split('.')[-1],shape=list(tensor.shape))
        if isinstance(x,np.ndarray):
            arrays[key]=x.copy();return dict(kind='numpy',key=key,shape=list(x.shape),dtype=str(x.dtype))
        if isinstance(x,np.generic):x=x.item()
        if x is None or isinstance(x,(str,int,float,bool)):return dict(kind='scalar',value=x)
        raise TypeError(f'Unsupported recording value {key}: {type(x)}')
    return pack(value,prefix),arrays


def restore_tree(schema,archive,device='cpu'):
    """Decode without pickle; used by offline verification and replay."""
    kind=schema['kind']
    if kind=='dict':return {k:restore_tree(v,archive,device) for k,v in schema['items'].items()}
    if kind in ('list','tuple'):
        values=[restore_tree(v,archive,device) for v in schema['items']]
        return tuple(values) if kind=='tuple' else values
    if kind=='scalar':return schema['value']
    if kind=='numpy':return archive[schema['key']].copy()
    if kind=='tensor':
        import torch
        return torch.from_numpy(archive[schema['key']].copy()).view(getattr(torch,schema['dtype'])).reshape(schema['shape']).to(device)
    raise ValueError(f'Unknown schema kind {kind}')


def model_manifest(policy,parameters):
    from dataclasses import asdict,is_dataclass
    import inspect
    import sys
    import torch
    path=getattr(policy.config,'pretrained_path',None)
    root=Path(path).resolve() if path else None
    def digest(p):
        h=hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
        return h.hexdigest()
    code_paths=[Path(__file__),Path(__file__).with_name('async_engine.py'),Path(__file__).with_name('rollout.py'),Path(__file__).parents[3]/'scripts/rollout_smolvla.sh',Path(inspect.getfile(type(policy)))]
    return dict(argv=list(sys.argv),torch_version=torch.__version__,cuda_version=torch.version.cuda,model_path=str(root),model_files_sha256={q.name:digest(q) for q in root.iterdir() if q.is_file()} if root and root.is_dir() else {},config=asdict(policy.config) if is_dataclass(policy.config) else vars(policy.config),parameters=parameters,code_sha256={str(q.resolve()):digest(q) for q in code_paths if q.is_file()},control='hard replacement; unchanged model-owned random sampling')
