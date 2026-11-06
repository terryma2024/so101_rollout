"""Offline serial-boundary doubles: these tests never open robot devices."""
import importlib
import json
from types import SimpleNamespace

import pytest


def mod():
    return importlib.import_module('tools.probe_leader_follower_handover')


def calibration(mid=2000):
    return {j: dict(id=i, drive_mode=0, homing_offset=0, range_min=mid-1000, range_max=mid+1000)
            for i, j in enumerate(('shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper'), 1)}


class Clock:
    now = 0.
    def __call__(self): return self.now
    def sleep(self, dt): self.now += dt


class Bus:
    def __init__(self, port, mid, events):
        self.port, self.mid, self.events = port, mid, events
        self.motors = {j: SimpleNamespace(id=i) for i,j in enumerate(calibration(),1)}
        self.is_connected = False
        self.values = {j: dict(Present_Position=mid, Torque_Enable=0, Goal_Position=mid, Operating_Mode=0, Present_Load=0, Present_Current=0)
                       for j in self.motors}
        self.stuck = False
        self.fail_cleanup = None
    def connect(self): self.is_connected = True
    def read_calibration(self): return {j: SimpleNamespace(**v) for j,v in calibration(self.mid).items()}
    def read(self, register, motor, *, normalize=False): return self.values[motor][register]
    def sync_read(self, register, *, normalize=False):
        assert normalize is False
        return {j:self.read(register,j) for j in self.motors}
    def write(self, register, motor, value, *, normalize=False):
        assert normalize is False
        self.events.append((self.port, register, motor, value))
        if register == 'Torque_Enable' and value == 0 and motor == self.fail_cleanup:
            raise OSError('disable failure')
        self.values[motor][register] = value
        if register == 'Goal_Position' and not self.stuck:
            self.values[motor]['Present_Position'] = value
    def disconnect(self, *, disable_torque):
        assert not disable_torque
        self.is_connected = False
        self.events.append((self.port,'closed'))


def rig():
    c=Clock(); events=[]
    return c, Bus('/fake/leader',2000,events), Bus('/fake/follower',2200,events), events


def settings(**kw):
    return mod().Settings(poll_hz=20, command_timeout=1, align_timeout=2,
                          ready_timeout=2, teaching_seconds=.3,
                          converge_seconds=.15, baseline_seconds=.15,
                          sustain_seconds=.15, **kw)


def run(tmp_path, c, l, f, *, config=None, trigger=True, commands=('ARM','GO')):
    queue=list(commands)
    def command(): return queue.pop(0) if queue else ''
    def sleep(dt):
        c.sleep(dt)
        # Move gripper only after the stable baseline window; arm remains put.
        if trigger and c.now > 2: l.values['gripper']['Present_Position']=2050
    return mod().run_probe(l,f,calibration(2000),calibration(2200),config or settings(),
                           tmp_path, clock=c,sleep=sleep,command=command)


def rows(path): return [json.loads(s) for s in (path/'events.jsonl').read_text().splitlines()]


def test_degrees_mapping_does_not_copy_counts_and_gripper_uses_percent():
    m=mod(); l=calibration(2000); f=calibration(2200)
    assert m.to_raw(f,'shoulder_pan',m.to_normal(l,'shoulder_pan',2100)) == 2300
    assert m.to_normal(l,'gripper',2000) == 50
    with pytest.raises(ValueError): m.to_raw(l,'shoulder_pan',1000)


def test_complete_handover_preserves_first_gripper_and_continuous_arms(tmp_path):
    c,l,f,events=rig()
    l.values['shoulder_pan']['Present_Position']=1900
    assert run(tmp_path,c,l,f) == 'finished'
    writes=[e for e in events if len(e)==4]
    assert [(e[0], e[1], e[3]) for e in writes[:6]] == [(f.port, 'Goal_Position', 2200)] * 6
    assert all(e[1]=='Torque_Enable' and e[3]==1 for e in writes[6:12])
    assert next(e[3] for e in writes if e[:3]==(l.port,'Goal_Position','shoulder_pan')) == 1900
    records=rows(tmp_path)
    trigger=next(r for r in records if r['event']=='takeover')
    commands=[r for r in records if r['event']=='follower_command']
    assert trigger['leader_reference']['gripper'] == pytest.approx(52.5)
    assert commands[0]['raw']['gripper'] == 2200
    assert commands[0]['raw']['shoulder_pan'] == 2200
    assert not [e for e in events if len(e)==4 and e[0]==l.port and e[1:]==('Torque_Enable','gripper',1)]
    assert any(r['event']=='ready' for r in records)
    assert all(v['Torque_Enable']==0 for b in (l,f) for v in b.values.values())
    assert not l.is_connected and not f.is_connected
    leader_goals=[e[3] for e in events if len(e)==4 and e[:3]==(l.port,'Goal_Position','shoulder_pan')]
    assert max(abs(b-a) for a,b in zip(leader_goals,leader_goals[1:])) <= 6


def test_initial_torque_on_refuses_all_writes(tmp_path):
    c,l,f,events=rig(); f.values['gripper']['Torque_Enable']=1
    with pytest.raises(RuntimeError,match='already enabled'): run(tmp_path,c,l,f)
    assert all(len(e)==2 for e in events)
    assert not l.is_connected and not f.is_connected


def test_live_calibration_mismatch_refuses_writes(tmp_path):
    c,l,f,events=rig()
    f.read_calibration=lambda: {j:SimpleNamespace(**v) for j,v in calibration(2300).items()}
    with pytest.raises(RuntimeError,match='calibration mismatch'): run(tmp_path,c,l,f)
    assert all(len(e)==2 for e in events)


def test_stuck_leader_never_becomes_ready_and_both_release(tmp_path):
    c,l,f,events=rig(); l.stuck=True; l.values['shoulder_pan']['Present_Position']=1950
    with pytest.raises(RuntimeError,match='alignment timeout'): run(tmp_path,c,l,f)
    assert not any(r['event']=='ready' for r in rows(tmp_path))
    assert all(v['Torque_Enable']==0 for b in (l,f) for v in b.values.values())


def test_no_go_timeout_releases_follower(tmp_path):
    c,l,f,events=rig()
    with pytest.raises(RuntimeError,match='command timeout'): run(tmp_path,c,l,f,commands=('ARM',))
    assert all(v['Torque_Enable']==0 for b in (l,f) for v in b.values.values())


def test_partial_cleanup_attempts_other_joints_buses_and_closes(tmp_path):
    c,l,f,events=rig(); l.fail_cleanup='shoulder_pan'
    with pytest.raises(RuntimeError,match='cleanup'): run(tmp_path,c,l,f)
    assert (l.port,'Torque_Enable','gripper',0) in events
    assert (f.port,'Torque_Enable','gripper',0) in events
    assert not l.is_connected and not f.is_connected
    assert any(r['event']=='cleanup_failed' for r in rows(tmp_path))


def test_nonfinite_or_out_of_range_telemetry_refuses_writes(tmp_path):
    c,l,f,events=rig(); f.values['gripper']['Present_Position']=float('nan')
    with pytest.raises(RuntimeError,match='telemetry'): run(tmp_path,c,l,f)
    assert all(len(e)==2 for e in events)


def test_ports_alias_and_bad_calibration_rejected_before_connect(tmp_path):
    c,l,f,events=rig(); f.port=l.port
    with pytest.raises(ValueError,match='ports'): run(tmp_path,c,l,f)
    assert not events
    bad=calibration(); bad['gripper']['id']=5
    with pytest.raises(ValueError,match='id'): mod().validate_calibration(bad)


def test_ready_without_gripper_trigger_times_out_and_releases(tmp_path):
    c,l,f,events=rig()
    with pytest.raises(RuntimeError,match='ready timeout'):
        run(tmp_path,c,l,f,trigger=False)
    assert any(r['event']=='ready' for r in rows(tmp_path))
    assert not any(r['event']=='takeover' for r in rows(tmp_path))
    assert all(v['Torque_Enable']==0 for b in (l,f) for v in b.values.values())


def test_waiting_for_arm_never_writes(tmp_path):
    c,l,f,events=rig()
    with pytest.raises(RuntimeError,match='command timeout'):
        run(tmp_path,c,l,f,commands=())
    assert all(len(e)==2 for e in events)


def test_follow_motion_has_bounded_updates_after_preserved_first_command(tmp_path):
    c,l,f,events=rig(); queue=['ARM','GO']; released_at=None
    def command(): return queue.pop(0) if queue else ''
    def sleep(dt):
        nonlocal released_at
        c.sleep(dt)
        if c.now > 2: l.values['gripper']['Present_Position']=2050
        if c.now > 2.2 and all(v['Torque_Enable']==0 for v in l.values.values()):
            if released_at is None: released_at=c.now
            # A deliberate large leader move is bounded into small follower commands.
            l.values['gripper']['Present_Position']=2250
            l.values['shoulder_pan']['Present_Position']=2100
    assert mod().run_probe(l,f,calibration(),calibration(2200),settings(),tmp_path,
                          clock=c,sleep=sleep,command=command)=='finished'
    commands=[r for r in rows(tmp_path) if r['event']=='follower_command']
    assert commands[0]['raw']['gripper']==2200
    assert commands[-1]['raw']['gripper']>2200
    assert commands[-1]['raw']['shoulder_pan']>2200
    for a,b in zip(commands,commands[1:]):
        for j in calibration():
            assert abs(a['normalized'][j]-b['normalized'][j])<=1.500001
    # All samples before takeover keep every follower joint energized.
    before=[r for r in rows(tmp_path) if r['event']=='sample' and r['state'] in ('align','ready')]
    assert before and all(r['follower'][j]['Torque_Enable']==1 for r in before for j in calibration())


def test_keyboard_interrupt_during_hold_releases_both_buses(tmp_path):
    c,l,f,events=rig(); calls=0
    def command():
        nonlocal calls
        calls+=1
        if calls==1: return 'ARM'
        raise KeyboardInterrupt('injected SIGINT')
    with pytest.raises(KeyboardInterrupt):
        mod().run_probe(l,f,calibration(),calibration(2200),settings(),tmp_path,
                        clock=c,sleep=c.sleep,command=command)
    assert all(v['Torque_Enable']==0 for b in (l,f) for v in b.values.values())
    assert not l.is_connected and not f.is_connected


def test_gripper_last_recorded_close_is_capped_without_negative_target():
    # Literal values from the failed 20261105-213637 handover, in percent.
    value, reasons = mod().gripper_command(7.851256, 21.671826625387,
        16.71826625386997, 11.564625850340136, step=1.5, closing_lead=3)
    assert value == pytest.approx(8.564625850340136)
    assert 'closing_lead' in reasons


def test_gripper_bounds_drop_excess_travel_and_reverse_immediately():
    m=mod()
    value, reasons=m.gripper_command(1, 50, 0, 1, step=1.5, closing_lead=3)
    assert value == 0 and 'range' in reasons
    value, _=m.gripper_command(value, 0, 1, 0, step=1.5, closing_lead=3)
    assert value == 1
    value, reasons=m.gripper_command(99, 0, 100, 99, step=1.5, closing_lead=3)
    assert value == 100 and 'range' in reasons
    value, _=m.gripper_command(value, 100, 99, 100, step=1.5, closing_lead=3)
    assert value == 99


def test_blocked_gripper_limits_closing_lead_drops_delta_and_opens_on_reversal():
    m=mod(); value=20
    for prev,current in [(50,40),(40,30),(30,20),(20,10)]:
        value,reasons=m.gripper_command(value,prev,current,20,step=1.5,closing_lead=3)
        assert value >= 17
    assert value == 17
    value,_=m.gripper_command(value,10,11,20,step=1.5,closing_lead=3)
    assert value == 18  # Opening raises the goal immediately, no discarded closure to repay.
    value,_=m.gripper_command(value,11,11,20,step=1.5,closing_lead=3)
    assert value == 18


def test_gripper_spike_step_bound_and_invalid_telemetry_remain_strict():
    m=mod()
    value,reasons=m.gripper_command(50, 0, 100, 50, step=.2, closing_lead=3)
    assert value == pytest.approx(50.2) and 'step' in reasons
    with pytest.raises(ValueError,match='gripper telemetry'):
        m.gripper_command(50,0,101,50,step=1.5,closing_lead=3)
    with pytest.raises(ValueError,match='gripper telemetry'):
        m.gripper_command(50,0,20,float('nan'),step=1.5,closing_lead=3)
    with pytest.raises(ValueError,match='target outside'):
        m.to_raw(calibration(),'shoulder_pan',1000)


def test_exact_failed_trial_gripper_trace_replays_offline_without_range_abort():
    from pathlib import Path
    trace=json.loads((Path(__file__).parent/'fixtures/handover_gripper_close_trace.json').read_text())
    goal=trace['initial_goal']; previous=trace['initial_leader']; cap_seen=False
    assert goal == pytest.approx(1.3605442176870748)
    for dt,leader,measured in trace['samples']:
        step=min(1.5,30*dt)
        new,reasons=mod().gripper_command(goal,previous,leader,measured,step=step,closing_lead=3)
        assert 0 <= new <= 100
        assert abs(new-goal)<=step+1e-10
        cap_seen |= 'closing_lead' in reasons
        previous,goal=leader,new
    assert cap_seen
    # Final requested opening stays within the configured lead of the measured opening.
    assert 8.564625850340136 <= goal <= 11.564625850340136


class LoadedElbowBus(Bus):
    """Position-servo plant with a persistent 42-tick load error while powered."""
    response = 'normal'
    def read(self, register, motor, *, normalize=False):
        value=super().read(register,motor,normalize=normalize)
        if register=='Present_Position' and motor=='elbow_flex' and self.values[motor]['Torque_Enable']:
            goal=self.values[motor]['Goal_Position']
            if self.response=='stuck': return 2042
            if self.response=='wrong': return 2042-(goal-2000)
            return goal+42
        return value
    def write(self, register, motor, value, *, normalize=False):
        measured=self.read('Present_Position',motor) if register=='Torque_Enable' and value==0 else None
        super().write(register,motor,value,normalize=normalize)
        if measured is not None: self.values[motor]['Present_Position']=measured


def compensated_run(tmp_path, *, enabled=True, response='normal'):
    c,l,f,events=rig(); l=LoadedElbowBus(l.port,2000,events); l.response=response
    queue=['ARM','GO']
    def command(): return queue.pop(0) if queue else ''
    def sleep(dt):
        c.sleep(dt)
        if c.now>10: l.values['gripper']['Present_Position']=2050
    config=mod().Settings(elbow_compensation=enabled,poll_hz=20,command_timeout=1,align_timeout=20,
        ready_timeout=15,teaching_seconds=.3,converge_seconds=.15,baseline_seconds=.15,
        sustain_seconds=.15,converge_tolerance=1.5)
    result=mod().run_probe(l,f,calibration(),calibration(2200),config,tmp_path,
                          clock=c,sleep=sleep,command=command)
    return result,events,rows(tmp_path)


def test_opt_in_elbow_compensation_handles_load_without_changing_other_goals(tmp_path):
    result,events,records=compensated_run(tmp_path)
    assert result=='finished'
    aligned=next(r for r in records if r['event']=='aligned')
    assert aligned['error_degrees']<=1.5
    elbow=[r for r in records if r['event']=='elbow_compensation']
    assert elbow and min(r['offset_degrees'] for r in elbow)<-2
    assert all(-3<=r['offset_degrees']<=0 for r in elbow)
    for a,b in zip(elbow,elbow[1:]):
        assert abs(b['offset_degrees']-a['offset_degrees']) <= .5*(b['monotonic']-a['monotonic'])+1e-9
    for e in events:
        if len(e)==4 and e[0]=='/fake/leader' and e[1]=='Goal_Position' and e[2]!='elbow_flex':
            assert e[3]==2000
    first=next(r for r in records if r['event']=='follower_command')
    assert set(first['raw'].values())=={2200}
    actual_elbow=[e[3] for e in events if len(e)==4 and e[:3]==('/fake/leader','Goal_Position','elbow_flex')]
    assert min(actual_elbow)<=1975


def test_disabled_elbow_compensation_keeps_nominal_goals(tmp_path):
    with pytest.raises(RuntimeError,match='alignment timeout'):
        compensated_run(tmp_path,enabled=False)
    records=rows(tmp_path)
    assert not any(r['event']=='elbow_compensation' for r in records)
    assert all(r['goal']['elbow_flex']==0 for r in records if r['event']=='alignment')


@pytest.mark.parametrize('response,reason',[('stuck','no measured improvement'),('wrong','worsened')])
def test_elbow_probe_aborts_before_winding_to_cap(tmp_path,response,reason):
    with pytest.raises(RuntimeError,match=reason):
        compensated_run(tmp_path,response=response)
    records=rows(tmp_path)
    offsets=[r['offset_degrees'] for r in records if r['event']=='elbow_compensation']
    assert offsets and min(offsets)>-1.1
    assert any(r['event']=='cleanup_verified' for r in records)
    assert not any(r['event']=='ready' for r in records)


def test_elbow_compensation_limit_overshoot_and_raw_goal_range():
    m=mod(); cfg=m.Settings(elbow_compensation=True,converge_tolerance=1.5)
    trial=m.ElbowCompensation(cfg)
    # A stable nominal residual is required before the first offset.
    for i in range(20): assert trial.observe(i*.05,4,True,.4)==0
    offset=trial.observe(1,4,True,.4)
    assert -.025001 <= offset <= 0
    with pytest.raises(RuntimeError,match='overshoot'):
        trial.observe(1.05,-2,True,.4)
    # An otherwise valid measured elbow at a nominal lower endpoint must not
    # produce a raw goal below its own calibrated range.
    cal=calibration(); nominal=m.to_normal(cal,'elbow_flex',1000)
    with pytest.raises(ValueError,match='target outside'):
        m.to_raw(cal,'elbow_flex',nominal-.025)


def test_elbow_compensation_reaches_hard_cap_and_aborts_with_residual_error():
    m=mod(); trial=m.ElbowCompensation(m.Settings(elbow_compensation=True,converge_tolerance=1.5))
    offsets=[]
    with pytest.raises(RuntimeError,match='limit exhausted'):
        for i in range(400):
            # Partial physical response improves each trial, but cannot converge within3°.
            error=4 + .5*trial.offset
            previous=trial.offset
            offsets.append(trial.observe(i*.05,error,True,.4))
            assert abs(trial.offset-previous)<=.025001
    assert min(offsets)==pytest.approx(-3)
    assert all(-3<=v<=0 for v in offsets)


def test_compensated_elbow_raw_boundary_aborts_before_outside_goal_write(tmp_path):
    c,l,f,events=rig(); l=LoadedElbowBus(l.port,2000,events)
    l.values['elbow_flex']['Present_Position']=1000
    f.values['elbow_flex']['Present_Position']=1200
    with pytest.raises(ValueError,match='target outside calibrated range'):
        run(tmp_path,c,l,f,config=settings(elbow_compensation=True,converge_tolerance=1.5),trigger=False)
    goals=[e[3] for e in events if len(e)==4 and e[:3]==('/fake/leader','Goal_Position','elbow_flex')]
    assert goals and min(goals)>=1000
    assert any(r['event']=='cleanup_verified' for r in rows(tmp_path))


def test_teaching_deadline_holds_until_enter_without_following_or_leader_reenable(tmp_path):
    c,l,f,events=rig(); queue=['ARM','GO']; waiting_at=None; held_events=None
    def command():
        nonlocal waiting_at,held_events
        if queue: return queue.pop(0)
        if any(r['event']=='teaching_stopped' for r in rows(tmp_path)):
            if waiting_at is None:
                waiting_at=c.now
                held_events=list(events)
            assert all(v['Torque_Enable']==1 for v in f.values.values())
            assert all(v['Torque_Enable']==0 for v in l.values.values())
            # New free-leader motion must not update the held follower goals.
            l.values['shoulder_pan']['Present_Position']=2100
            if c.now-waiting_at>=2:
                assert events==held_events
                return ''
        return None
    def sleep(dt):
        c.sleep(dt)
        if c.now>2: l.values['gripper']['Present_Position']=2050
    assert mod().run_probe(l,f,calibration(),calibration(2200),settings(),tmp_path,
        clock=c,sleep=sleep,command=command)=='finished'
    assert waiting_at is not None and c.now-waiting_at>=2
    assert any(r['event']=='release_confirmed' for r in rows(tmp_path))
    enables=[e for e in events if len(e)==4 and e[0]==l.port and e[1]=='Torque_Enable' and e[3]==1]
    assert len(enables)==5
    assert all(v['Torque_Enable']==0 for b in (l,f) for v in b.values.values())


def test_fault_in_wait_for_release_still_cleans_up_immediately(tmp_path):
    c,l,f,events=rig(); queue=['ARM','GO']; injected=False
    def command():
        nonlocal injected
        if queue: return queue.pop(0)
        if any(r['event']=='teaching_stopped' for r in rows(tmp_path)):
            f.values['shoulder_pan']['Torque_Enable']=0
            injected=True
        return None
    def sleep(dt):
        c.sleep(dt)
        if c.now>2: l.values['gripper']['Present_Position']=2050
    with pytest.raises(RuntimeError,match='unexpected torque state'):
        mod().run_probe(l,f,calibration(),calibration(2200),settings(),tmp_path,
            clock=c,sleep=sleep,command=command)
    assert injected
    assert any(r['event']=='cleanup_verified' for r in rows(tmp_path))
    assert not any(r['event']=='release_confirmed' for r in rows(tmp_path))


class ApproximateBus(LoadedElbowBus):
    """Read-only position response; release retains the last measured position."""
    def __init__(self,port,mid,events,clock,offsets):
        super().__init__(port,mid,events)
        self.clock,self.offsets=clock,offsets
    def read(self,register,motor,*,normalize=False):
        value=Bus.read(self,register,motor,normalize=normalize)
        if register=='Present_Position' and self.values[motor]['Torque_Enable']:
            return self.values[motor]['Goal_Position']+self.offsets(motor,self.clock.now)
        return value


def approximate_run(tmp_path,offsets,*,enabled=True,on_sleep=None,tolerance=.75):
    c,l,f,events=rig(); l=ApproximateBus(l.port,2000,events,c,offsets); queue=['ARM','GO']
    def command(): return queue.pop(0) if queue else ''
    def sleep(dt):
        c.sleep(dt)
        if on_sleep: on_sleep(c,l)
        if c.now>2: l.values['gripper']['Present_Position']=2050
    config=mod().Settings(approximate_alignment=enabled,poll_hz=20,command_timeout=1,align_timeout=2,
        ready_timeout=3,teaching_seconds=.3,baseline_seconds=.15,sustain_seconds=.15,
        converge_tolerance=tolerance)
    result=mod().run_probe(l,f,calibration(),calibration(2200),config,tmp_path,
                          clock=c,sleep=sleep,command=command)
    return result,events,rows(tmp_path)


def test_approximate_stable_37_degree_elbow_reaches_ready_with_continuous_first_goal(tmp_path):
    result,events,records=approximate_run(tmp_path,lambda j,t:42 if j=='elbow_flex' else 0)
    assert result=='finished'
    aligned=next(r for r in records if r['event']=='aligned')
    assert aligned['alignment_mode']=='approximate'
    assert aligned['alignment_gate']['elapsed_seconds']>=1
    assert aligned['alignment_gate']['joints']['elbow_flex']['residual_degrees']==pytest.approx(42*360/4095)
    assert next(r for r in records if r['event']=='follower_command')['raw']=={j:2200 for j in calibration()}
    assert next(r for r in records if r['event']=='takeover')['leader_reference']['elbow_flex']==pytest.approx(42*360/4095)
    assert not any(r['event']=='elbow_compensation' for r in records)
    assert all(e[3]==2000 for e in events if len(e)==4 and e[0]=='/fake/leader' and e[1]=='Goal_Position')


@pytest.mark.parametrize('offsets',[
    lambda j,t:47 if j=='elbow_flex' else 0,  # >4° elbow
    lambda j,t:18 if j=='wrist_flex' else 0,  # >1.5° another axis
    lambda j,t:(40+(3 if int(t*20)%2 else -3)) if j=='elbow_flex' else 0,
    lambda j,t:round(t*6) if j=='wrist_roll' else 0,  # >0.35°/second drift
])
def test_approximate_rejects_bound_violations_jitter_and_drift(tmp_path,offsets):
    with pytest.raises(RuntimeError,match='alignment timeout'):
        approximate_run(tmp_path,offsets,tolerance=20)  # Cannot widen fixed approximate bounds.
    records=rows(tmp_path)
    assert not any(r['event']=='ready' for r in records)
    assert any(r['event']=='cleanup_verified' for r in records)


@pytest.mark.parametrize('new_ticks',[47,37])
def test_approximate_ready_motion_aborts_before_trigger_even_if_within_elbow_bound(tmp_path,new_ticks):
    def after_ready(c,l):
        if any(r['event']=='ready' for r in rows(tmp_path)):
            l.offsets=lambda j,t:new_ticks if j=='elbow_flex' else 0
    with pytest.raises(RuntimeError,match='approximate alignment lost'):
        approximate_run(tmp_path,lambda j,t:42 if j=='elbow_flex' else 0,on_sleep=after_ready)
    records=rows(tmp_path)
    assert any(r['event']=='ready' for r in records)
    assert not any(r['event']=='takeover' for r in records)
    assert any(r['event']=='cleanup_verified' for r in records)


def test_approximate_is_explicit_mutually_exclusive_and_strict_stays_strict(tmp_path):
    with pytest.raises(ValueError,match='mutually exclusive'):
        mod().Settings(approximate_alignment=True,elbow_compensation=True).validate()
    with pytest.raises(RuntimeError,match='alignment timeout'):
        approximate_run(tmp_path,lambda j,t:42 if j=='elbow_flex' else 0,enabled=False,tolerance=1.5)
    assert not any(r['event']=='ready' for r in rows(tmp_path))


def test_approximate_window_starts_after_nominal_ramp_and_rechecks_all_old_samples():
    m=mod(); gate=m.ApproximateAlignment()
    target={j:0 for j in m.ARM_JOINTS}; pos=dict(target,elbow_flex=3.7)
    for t in (0,.5,1,1.5): assert not gate.observe(t,pos,target,False)['ready']
    assert not gate.observe(2,pos,target,True)['ready']
    assert not gate.observe(2.5,pos,target,True)['ready']
    assert gate.observe(3,pos,target,True)['ready']
    # All positions are stable within0.11°, and the latest sample is within4°,
    # but an old out-of-bound sample prevents accepting the full window.
    gate=m.ApproximateAlignment(); pos['elbow_flex']=4.1
    gate.observe(0,pos,target,True)
    pos['elbow_flex']=3.99
    for i in range(1,11): report=gate.observe(i/10,pos,target,True)
    assert report['stable'] and not report['within_limits'] and not report['ready']
    assert gate.observe(1.1,pos,target,True)['ready']


def test_approximate_and_compensation_cli_conflict_exits_before_bus_creation(capsys):
    with pytest.raises(SystemExit) as exc:
        mod().main(['--approximate-alignment','--elbow-compensation'])
    assert exc.value.code==2
    assert 'mutually exclusive' in capsys.readouterr().err
