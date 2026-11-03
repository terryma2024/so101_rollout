"""Bounded diagnostics must never change scheduler control semantics."""
import json
import threading
import time
import numpy as np
from so101_rollout.smolvla.recording import InferenceRecorder


def test_lossless_records_and_clean_close(tmp_path):
    r=InferenceRecorder(tmp_path/'log',max_items=8,max_bytes=1024)
    a=np.arange(24,dtype=np.uint8).reshape(2,4,3)
    assert r.submit('request',{'identifier':3},{'image':a})
    r.close()
    status=json.loads((tmp_path/'log/status.json').read_text())
    assert status['complete'] and status['accepted']==status['written']==1
    with np.load(tmp_path/'log/00000000-request.npz',allow_pickle=False) as z:
        np.testing.assert_array_equal(z['image'],a)
        assert json.loads(str(z['metadata']))['identifier']==3


def test_slow_writer_has_bounded_queue_and_explicit_loss(tmp_path):
    entered,release=threading.Event(),threading.Event()
    r=InferenceRecorder(tmp_path/'log',max_items=1,max_bytes=128)
    original=r._write
    def slow(item):
        entered.set();release.wait(2);original(item)
    r._write=slow
    try:
        assert r.submit('event',{}, {'a':np.zeros(4)})
        assert entered.wait(2)
        assert r.submit('event',{}, {'a':np.zeros(4)})
        start=time.perf_counter()
        assert not r.submit('event',{}, {'a':np.zeros(4)})
        assert time.perf_counter()-start<.05
        assert not r.status()['complete'] and r.status()['dropped']==1
    finally:release.set();r.close()
    assert not json.loads((tmp_path/'log/status.json').read_text())['complete']


def test_disk_failure_and_byte_limit_are_explicit_without_raising(tmp_path):
    r=InferenceRecorder(tmp_path/'log',max_items=8,max_bytes=32)
    assert not r.submit('oversize',{}, {'a':np.zeros(8)})
    def fail(item):raise OSError('disk full')
    r._write=fail
    assert r.submit('event',{})
    r.close()
    s=r.status()
    assert not s['complete'] and s['dropped']==1 and s['errors'] and 'disk full' in str(s['errors'])


def test_teardown_timeout_marks_incomplete_and_never_hangs_control(tmp_path):
    entered,release=threading.Event(),threading.Event()
    r=InferenceRecorder(tmp_path/'log')
    original=r._write
    def slow(item):entered.set();release.wait(2);original(item)
    r._write=slow;r.submit('event',{});assert entered.wait(2)
    start=time.perf_counter();r.close(timeout=.01)
    assert time.perf_counter()-start<.1
    assert r.status()['close_timeout'] and not r.status()['complete']
    release.set();r._thread.join(2)


def test_existing_log_is_never_overwritten(tmp_path):
    path=tmp_path/'log';path.mkdir();(path/'status.json').write_text('original')
    r=InferenceRecorder(path);assert not r.submit('event',{})
    r.close();assert (path/'status.json').read_text()=='original'
    assert not r.status()['complete']


def test_scheduler_recording_preserves_actions_and_reset_barrier(tmp_path):
    from so101_rollout.smolvla.async_engine import AsyncChunkScheduler
    def run(recorder):
        clock=[100.];entered=threading.Event();release=threading.Event()
        def infer(req):
            if req.observation.get('wait'):
                entered.set();assert release.wait(2)
            return [[req.observation['value']+i]*6 for i in range(8)]
        engine=AsyncChunkScheduler(infer,fps=20,horizon=8,prefetch=3,clock=lambda:clock[0],recorder=recorder)
        def ready():
            deadline=time.monotonic()+2
            while not engine.result_ready:
                assert time.monotonic()<deadline;time.sleep(.001)
        values=[];engine.start();engine.resume()
        try:
            assert engine.get_action({'value':1,'wait':True}) is None;assert entered.wait(2)
            engine.pause();engine.reset(task='new');engine.resume();release.set();ready()
            assert engine.get_action(None) is None
            assert engine.get_action({'value':100}) is None;ready()
            for i in range(5):
                values.append(engine.get_action({'value':200}));clock[0]+=.05
            assert engine.stats['stale_results']==1
        finally:release.set();engine.stop()
        return values
    plain=run(None);r=InferenceRecorder(tmp_path/'log');recorded=run(r)
    assert plain==recorded
    assert r.status()['complete']
    events=[]
    for f in sorted((tmp_path/'log').glob('*.npz')):
        with np.load(f) as z:events.append((f.name,json.loads(str(z['metadata']))))
    assert any('stale' in n for n,e in events)
    assert all(e['generation']==2 for n,e in events if 'output' in n)


def test_tensor_tree_roundtrip_is_lossless_including_bfloat_and_scalar():
    import pytest
    torch=pytest.importorskip('torch')
    from so101_rollout.smolvla.recording import array_tree,restore_tree
    original={'scalar':torch.tensor(3.),'bf':torch.arange(8,dtype=torch.bfloat16).reshape(2,4),'nested':[np.arange(3,dtype=np.uint8),'text',None]}
    schema,arrays=array_tree(original)
    restored=restore_tree(schema,arrays)
    assert torch.equal(original['scalar'],restored['scalar'])
    assert torch.equal(original['bf'],restored['bf']) and restored['bf'].dtype==torch.bfloat16
    np.testing.assert_array_equal(original['nested'][0],restored['nested'][0])
    assert restored['nested'][1:]==['text',None]


def test_diagnostic_failure_does_not_change_control_outputs(tmp_path):
    from so101_rollout.smolvla.async_engine import AsyncChunkScheduler
    r=InferenceRecorder(tmp_path/'log');r.error(OSError('diagnostic storage unavailable'))
    engine=AsyncChunkScheduler(lambda req:[[float(i)]*6 for i in range(8)],horizon=8,prefetch=3,recorder=r)
    engine.start();engine.resume()
    try:
        assert engine.get_action({}) is None
        deadline=time.monotonic()+2
        while not engine.result_ready:assert time.monotonic()<deadline;time.sleep(.001)
        assert engine.get_action({})==[0.]*6
        assert not engine.failed
    finally:engine.stop()
    assert not r.status()['complete'] and r.status()['dropped']>0


def test_slow_full_recorder_does_not_block_scheduler_ticks(tmp_path):
    from so101_rollout.smolvla.async_engine import AsyncChunkScheduler
    entered,release=threading.Event(),threading.Event();clock=[100.]
    r=InferenceRecorder(tmp_path/'log',max_items=1)
    original=r._write
    def slow(item):entered.set();release.wait(2);original(item)
    r._write=slow
    engine=AsyncChunkScheduler(lambda req:[[float(i)]*6 for i in range(8)],horizon=8,prefetch=3,clock=lambda:clock[0],recorder=r)
    engine.start();engine.resume()
    try:
        assert engine.get_action({}) is None;assert entered.wait(2)
        deadline=time.monotonic()+2
        while not engine.result_ready:assert time.monotonic()<deadline;time.sleep(.001)
        for i in range(5):
            start=time.perf_counter();a=engine.get_action({})
            assert time.perf_counter()-start<.05
            assert a==[float(i)]*6;clock[0]+=.05
        assert r.status()['dropped']>0 and not engine.failed
    finally:release.set();engine.stop()
    assert not r.status()['complete']
