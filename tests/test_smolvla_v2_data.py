import copy
import pytest


def old_records():
    return [dict(split=s, color=c, group=s+c, origin=s+c+':0', source_dataset=s+c,
                 source_episode_index=0, original_episode_index=0,
                 numeric_sha256=s+c, frames=2, task='task')
            for s in ('train','validation') for c in ('green','red')]


def selection():
    return {'status':'selection_only_approved','visual_status':'pass','merged':False,
            'excluded':{'dataset_name':'b02-green','episode_index':6,'plan_id':'G19','split':'train'},
            'replacement':{'dataset_name':'replacement-green','episode_index':0,'plan_id':'G19','split':'train'},
            'sources':[{'dataset_name':'b02-green','split':'train','selected_episode_indices':[0,1,2,3,4,5,7,8,9,10,11], 'selected_plan_ids':['G13','G14','G15','G16','G17','G18','G20','G21','G22','G23','G24']},
                       {'dataset_name':'replacement-green','split':'train','selected_episode_indices':[0],'selected_plan_ids':['G19'],'role':'replacement'}]}


def test_selection_removes_rejected_g19_and_keeps_original_source_episode_ids():
    from tools.prepare_smolvla_v2_data import selected_sources
    rows=selected_sources(selection())
    assert rows[0]['episodes']==[0,1,2,3,4,5,7,8,9,10,11]
    assert rows[1]['episodes']==[0]
    assert rows[0]['split']==rows[1]['split']=='train'


@pytest.mark.parametrize('mutation', ['rejected_present','replacement_missing','duplicate_episode','visual_pending'])
def test_unsafe_selection_is_rejected(mutation):
    from tools.prepare_smolvla_v2_data import selected_sources
    s=selection()
    if mutation=='rejected_present':s['sources'][0]['selected_episode_indices'].append(6)
    if mutation=='replacement_missing':s['sources'].pop()
    if mutation=='duplicate_episode':s['sources'][0]['selected_episode_indices'].append(0)
    if mutation=='visual_pending':s['visual_status']='pending_visual'
    with pytest.raises(ValueError):selected_sources(s)


def test_same_wide_capture_batch_groups_both_colors_together():
    from tools.prepare_smolvla_v2_data import capture_group
    assert capture_group('real-cube-bowl-smolvla-v2-wide-b03-green-20261102') == capture_group('real-cube-bowl-smolvla-v2-wide-b03-red-20261102')
    assert capture_group('real-cube-bowl-smolvla-v2-wide-b02-green-20261102') != capture_group('real-cube-bowl-smolvla-v2-wide-b03-green-20261102')


def test_g19_replacement_belongs_to_b02_group_without_changing_its_origin():
    from tools.prepare_smolvla_v2_data import capture_group
    assert capture_group('real-cube-bowl-smolvla-v2-wide-g19-replacement-green-20261103') == 'real-cube-bowl-smolvla-v2-wide-b02-20261102'
