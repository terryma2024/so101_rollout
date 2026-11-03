from types import SimpleNamespace
import pytest
from so101_rollout.smolvla.persistent_session import ModelCache, validate_resume

class Resettable:
    def __init__(self): self.resets=0
    def reset(self): self.resets+=1


def test_terminal_listener_cleanup_without_thread_interface():
    from lerobot.utils.keyboard_input import TerminalKeyListener
    from so101_rollout.smolvla.persistent_session import stop_keyboard_listener
    listener = TerminalKeyListener(lambda key: None)
    assert not hasattr(listener, 'ident')
    stop_keyboard_listener(listener)
    stop_keyboard_listener(listener)


@pytest.mark.parametrize('wrapped', [False, True])
def test_listener_cleanup_waits_for_real_thread(wrapped):
    import threading
    from so101_rollout.smolvla.persistent_session import stop_keyboard_listener
    stopped = threading.Event()
    class Listener(threading.Thread):
        def run(self): stopped.wait(1)
        def stop(self): stopped.set()
    thread = Listener()
    thread.start()
    if wrapped:
        class Terminal:
            _thread = thread
            def stop(self):
                stopped.set()
                self._thread = None
        listener = Terminal()
    else:
        listener = thread
    stop_keyboard_listener(listener, thread)
    assert not thread.is_alive()

def test_cache_loads_once_and_resets_between_tasks():
    loads=[]; processors=[]
    cache=ModelCache()
    def load(cfg): loads.append(cfg); return Resettable()
    def make(**kw): processors.append(kw); return Resettable(),Resettable()
    cfg=SimpleNamespace(pretrained_path='/model',type='smolvla')
    p=cache.policy(load,cfg)
    a,b=cache.processors(make,policy_cfg=cfg,pretrained_path='/model',dataset_stats={},preprocessor_overrides={'device':'cpu'})
    cache.reset()
    assert cache.policy(load,cfg) is p
    assert cache.processors(make,policy_cfg=cfg,pretrained_path='/model',dataset_stats={},preprocessor_overrides={'device':'cpu'})==(a,b)
    cache.reset()
    assert len(loads)==len(processors)==1
    assert [p.resets,a.resets,b.resets]==[2,2,2]

def test_resume_requires_completed_receipts_and_fresh_remaining(tmp_path):
    trials=[dict(id=i,dataset_path=str(tmp_path/f'ds{i}'),recording_path=str(tmp_path/f'rec{i}')) for i in [1,2]]
    with pytest.raises(ValueError,match='receipt'): validate_resume(trials,tmp_path,2)
    import json
    (tmp_path/'trial-01-execution.json').write_text(json.dumps(dict(id=1,dataset=None,recording_path=trials[0]['recording_path'],complete=True)))
    (tmp_path/'rec1').mkdir()
    (tmp_path/'rec1/status.json').write_text(json.dumps(dict(complete=True)))
    (tmp_path/'ds1/meta').mkdir(parents=True)
    (tmp_path/'ds1/meta/info.json').write_text(json.dumps(dict(total_episodes=1)))
    (tmp_path/'terminal-logs').mkdir()
    (tmp_path/'terminal-logs/trial-01.log').write_text('complete')
    validate_resume(trials,tmp_path,2)
    (tmp_path/'rec2').mkdir()
    with pytest.raises(ValueError,match='Fresh'): validate_resume(trials,tmp_path,2)

@pytest.mark.parametrize("operator_stop,tail_failure", [(False,False),(True,False),(False,True)])
def test_native_cases_stop_worker_disconnect_and_reset(monkeypatch, operator_stop, tail_failure):
    import sys, types, threading, time
    from so101_rollout.smolvla.async_engine import AsyncChunkScheduler
    from so101_rollout.smolvla.persistent_session import run_native_case
    records=[]; devices=[]; engines=[]; loads=[]
    cache=ModelCache()
    context=types.SimpleNamespace()
    def load(cfg): loads.append(1); return Resettable()
    context._load_pretrained_policy=load
    context.make_pre_post_processors=lambda **kw:(Resettable(),Resettable())
    class Device:
        is_connected=False
        def disconnect(self): self.is_connected=False
    def robot(config):
        d=Device(); devices.append(d); return d
    context.make_robot_from_config=robot
    context.make_teleoperator_from_config=robot
    def build(cfg,event):
        p=context._load_pretrained_policy(SimpleNamespace(type='smolvla'))
        a,b=context.make_pre_post_processors(policy_cfg=SimpleNamespace(type='smolvla'))
        d=context.make_robot_from_config(None);d.is_connected=True
        engine=AsyncChunkScheduler(lambda req:[[1.0] for _ in range(50)],task=cfg.task)
        engines.append(engine)
        return SimpleNamespace(policy=SimpleNamespace(inference=engine),data=SimpleNamespace(dataset=SimpleNamespace(num_episodes=1)),device=d)
    context.build_rollout_context=build
    class Strategy:
        _events={"stop_recording":operator_stop}
        def __init__(self):
            from lerobot.utils.keyboard_input import TerminalKeyListener
            self._listener = TerminalKeyListener(lambda key: None)
        def setup(self,ctx): ctx.policy.inference.start();ctx.policy.inference.resume()
        def run(self,ctx):
            e=ctx.policy.inference
            while e.get_action({'task':e.task}) is None:time.sleep(.001)
            records.append((e.task,e._next_id,e.stats['actions']))
            if tail_failure:
                from concurrent.futures import Future
                e._future=Future()
                e._future.set_exception(ValueError('final inference failed'))
        def teardown(self,ctx): ctx.policy.inference.stop();ctx.device.disconnect()
    monkeypatch.setitem(sys.modules,'lerobot.rollout',types.SimpleNamespace(context=context,create_strategy=lambda c:Strategy()))
    monkeypatch.setitem(sys.modules,'lerobot.utils.visualization_utils',types.SimpleNamespace(init_visualization=lambda *a,**k:None,shutdown_visualization=lambda *a:None))
    with cache.bind(context):
        for task in ['green','red']:
            if operator_stop or tail_failure:
                expected='Operator requested stop' if operator_stop else 'Final in-flight inference failed'
                with pytest.raises(RuntimeError,match=expected):
                    run_native_case(SimpleNamespace(strategy=None,display_data=False,task=task),cache,threading.Event())
                assert cache.loaded.resets==0
                assert not engines[-1]._thread.is_alive()
                assert not devices[-1].is_connected
                return
            run_native_case(SimpleNamespace(strategy=None,display_data=False,task=task),cache,threading.Event())
    assert len(loads)==1
    assert records==[('green',1,1),('red',1,1)]
    assert engines[0] is not engines[1]
    assert all(not e._thread.is_alive() and not e._queue for e in engines)
    assert all(not d.is_connected for d in devices)
    assert cache.loaded.resets==2

def test_changed_processor_configuration_is_rejected():
    cache=ModelCache()
    cache.processors(lambda **kw:(Resettable(),Resettable()),postprocessor_overrides={})
    with pytest.raises(ValueError,match='configuration changed'):
        cache.processors(lambda **kw:None,postprocessor_overrides={'different':True})

def test_build_failure_disconnects_already_created_devices(monkeypatch):
    import sys, types, threading
    from so101_rollout.smolvla.persistent_session import run_native_case
    class Device:
        is_connected=True
        def disconnect(self): self.is_connected=False
    device=Device()
    context=types.SimpleNamespace(make_robot_from_config=lambda cfg:device,make_teleoperator_from_config=lambda cfg:device)
    def fail(cfg,event):
        context.make_robot_from_config(None)
        raise ValueError('dataset failed')
    context.build_rollout_context=fail
    monkeypatch.setitem(sys.modules,'lerobot.rollout',types.SimpleNamespace(context=context,create_strategy=lambda c:None))
    monkeypatch.setitem(sys.modules,'lerobot.utils.visualization_utils',types.SimpleNamespace(init_visualization=lambda *a,**k:None,shutdown_visualization=lambda *a:None))
    with pytest.raises(ValueError,match='dataset failed'):
        run_native_case(SimpleNamespace(strategy=None,display_data=False),ModelCache(),threading.Event())
    assert not device.is_connected


def test_resume_rejects_wrong_plan_and_incomplete_recording(tmp_path):
    import json
    t=dict(id=1,dataset='one',dataset_path=str(tmp_path/'ds1'),recording_path=str(tmp_path/'rec1'))
    next_t=dict(id=2,dataset='two',dataset_path=str(tmp_path/'ds2'),recording_path=str(tmp_path/'rec2'))
    (tmp_path/'trial-01-execution.json').write_text(json.dumps(dict(id=1,dataset='one',recording_path=t['recording_path'],complete=True,plan_sha256='wrong')))
    with pytest.raises(ValueError,match='mismatched'):
        validate_resume([t,next_t],tmp_path,2,'expected')

def test_teardown_failure_stops_worker_without_resetting_cache(monkeypatch):
    import sys, types, threading
    from so101_rollout.smolvla.async_engine import AsyncChunkScheduler
    from so101_rollout.smolvla.persistent_session import run_native_case
    class Device:
        is_connected=True
        def disconnect(self): self.is_connected=False
    device=Device()
    engine=AsyncChunkScheduler(lambda req:[[0.] for _ in range(50)])
    ctx=SimpleNamespace(policy=SimpleNamespace(inference=engine),data=SimpleNamespace(dataset=SimpleNamespace(num_episodes=1)))
    context=SimpleNamespace(make_robot_from_config=lambda cfg:device,make_teleoperator_from_config=lambda cfg:device)
    def build(cfg,event):context.make_robot_from_config(None);return ctx
    context.build_rollout_context=build
    class Strategy:
        def setup(self,ctx):engine.start()
        def run(self,ctx):pass
        def teardown(self,ctx):raise ValueError('dataset finalize failed')
    monkeypatch.setitem(sys.modules,'lerobot.rollout',SimpleNamespace(context=context,create_strategy=lambda cfg:Strategy()))
    monkeypatch.setitem(sys.modules,'lerobot.utils.visualization_utils',SimpleNamespace(init_visualization=lambda *a,**k:None,shutdown_visualization=lambda *a:None))
    cache=ModelCache();cache.loaded=Resettable()
    with pytest.raises(ValueError,match='finalize failed'):
        run_native_case(SimpleNamespace(strategy=None,display_data=False),cache,threading.Event())
    assert not engine._thread.is_alive()
    assert not device.is_connected
    assert cache.loaded.resets==0
