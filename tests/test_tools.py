"""Offline experiment contracts: single frames, human labels, colour binding and images."""
import copy
import importlib
import importlib.util
import json
from pathlib import Path

import pytest


def tool(name):
    spec = importlib.util.find_spec('tools')
    assert spec is not None, 'tools package has not been migrated'
    spec = importlib.util.find_spec('tools.' + name)
    assert spec is not None, f'offline tool {name} has not been migrated'
    return importlib.import_module('tools.' + name)


def test_preview_preserves_source_and_bounds_long_edge(tmp_path):
    from PIL import Image
    assets = tool('assets')
    src = tmp_path / 'original.png'
    Image.new('RGB', (2200, 3300), 'red').save(src)
    before = src.read_bytes()
    result = assets.preview(src, tmp_path / 'preview.png')
    assert result['original_size'] == [2200, 3300]
    with Image.open(tmp_path / 'preview.png') as im:
        assert max(im.size) == 1600
    assert src.read_bytes() == before
    with pytest.raises(ValueError):
        assets.preview(src, src)


def test_video_review_keeps_single_frame_and_metadata_order(tmp_path):
    import av
    import numpy as np
    import pandas as pd
    review = tool('review_dataset')
    ds = tmp_path / 'dataset'
    (ds / 'meta/episodes/chunk-000').mkdir(parents=True)
    (ds / 'data/chunk-000').mkdir(parents=True)
    (ds / 'meta/info.json').write_text(json.dumps({'fps': 20}))
    episodes = []
    for ei, t0, t1, length in [(1, .05, .3, 5), (0, 0, .05, 1)]:
        e = {'episode_index': ei, 'length': length}
        for cam in ['side', 'wrist']:
            key = f'videos/observation.images.{cam}'
            e.update({key + '/from_timestamp': t0, key + '/to_timestamp': t1,
                      key + '/file_index': 0, key + '/chunk_index': 1})
        episodes.append(e)
    pd.DataFrame(episodes).to_parquet(ds / 'meta/episodes/chunk-000/file-000.parquet')
    pd.DataFrame([{'episode_index': ei, 'frame_index': i, 'timestamp': i / 20}
                  for ei, length in [(0, 1), (1, 5)] for i in range(length)]).to_parquet(ds / 'data/chunk-000/file-000.parquet')
    for cam in ['side', 'wrist']:
        p = ds / f'videos/observation.images.{cam}/chunk-001/file-000.mp4'
        p.parent.mkdir(parents=True)
        with av.open(str(p), 'w') as container:
            stream = container.add_stream('libx264', rate=20)
            stream.width, stream.height, stream.pix_fmt = 64, 48, 'yuv420p'
            for i in range(6):
                frame = av.VideoFrame.from_ndarray(np.full((48, 64, 3), i * 30, dtype=np.uint8), format='rgb24')
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
    result = review.review(ds, tmp_path / 'review')
    assert result['integrity_ok']
    assert [r['recorded_episode'] for r in result['rows']] == [1, 2]
    assert [r['frames'] for r in result['rows']] == [1, 5]
    assert result['rows'][0]['short_record'] is True
    assert all(r['final_in_bowl'] is None for r in result['rows'])


def test_summary_requires_human_labels_and_does_not_infer_from_duration():
    summary = tool('summarize_results')
    rows = [dict(color='green', round=1, recorded_episode=1, final_in_bowl=True,
                 first_grasp_success=False, layout_row=6, recorded_duration_s=30),
            dict(color='red', round=1, recorded_episode=1, final_in_bowl=False,
                 first_grasp_success=None, layout_row=4, recorded_duration_s=22.1)]
    result = summary.summarize(rows)
    assert result['total'] == {'success': 1, 'trials': 2, 'unknown': 0}
    assert result['green']['first_grasp'] == {'success': 0, 'labelled': 1}
    assert result['red']['first_grasp']['labelled'] == 0
    with pytest.raises(ValueError, match='duplicate'):
        summary.summarize(rows + [rows[0]])
    with pytest.raises(ValueError, match='boolean'):
        summary.summarize([dict(rows[0], final_in_bowl='false')])


def test_collection_validation_rejects_mixed_colour_task_and_output_collision():
    cards = tool('render_collection')
    repo = Path(__file__).resolve().parents[1]
    plan = json.loads((repo / 'tools/plans/p2-20261030.json').read_text())
    cards.validate(plan)
    assert sum(len(b['episodes']) for b in plan['batches']) == 80
    assert sorted(len(b['episodes']) for b in plan['batches']) == [10, 20, 20, 30]
    bad = copy.deepcopy(plan)
    bad['batches'][0]['episodes'][0]['color'] = 'red'
    with pytest.raises(ValueError, match='color'):
        cards.validate(bad)
    bad = copy.deepcopy(plan)
    bad['batches'][0]['task'] = 'Put the red cube into the paper bowl'
    with pytest.raises(ValueError, match='task'):
        cards.validate(bad)
    bad = copy.deepcopy(plan)
    bad['batches'][1]['dataset_name'] = bad['batches'][0]['dataset_name']
    with pytest.raises(ValueError, match='dataset'):
        cards.validate(bad)


def test_language_pairing_compares_physical_colours_not_target_roles():
    audit = tool('language_coverage')
    def entry(c, target, distractor):
        return dict(color=c, target=target, distractor=distractor,
                    target_dx_mm=0, target_dy_mm=0, target_yaw_deg=0,
                    distractor_dx_mm=0, distractor_dy_mm=0, distractor_yaw_deg=0)
    # Identical physical scene: green at A1, red at C3, opposite task roles.
    green = entry('green', 'A1', 'C3')
    red = entry('red', 'C3', 'A1')
    result = audit.coverage([green, red])
    assert result['paired_conditions'] == 1
    assert result['paired_demonstrations'] == 2
    red['target_dx_mm'] = 3
    assert audit.coverage([green, red])['paired_conditions'] == 0
    assert audit.coverage([green, red], cells_only=True)['paired_conditions'] == 1


def test_manifest_refuses_to_replace_source(tmp_path):
    assets = tool('assets')
    src = tmp_path / 'source.bin'
    src.write_bytes(b'irreplaceable raw evidence')
    with pytest.raises(FileExistsError):
        assets.manifest(tmp_path, src)
    assert src.read_bytes() == b'irreplaceable raw evidence'


@pytest.mark.parametrize('mutation,match',[
    ('batch_path','batch'),('batch_duplicate','batch'),('wrong_prefix','id'),('wrong_order','order')])
def test_cards_reject_output_escape_and_misleading_ids(mutation, match):
    cards = tool('render_collection')
    p = Path(__file__).resolve().parents[1] / 'tools/plans/p2-20261030.json'
    plan = json.loads(p.read_text())
    if mutation == 'batch_path': plan['batches'][0]['batch'] = '../escaped'
    if mutation == 'batch_duplicate': plan['batches'][1]['batch'] = plan['batches'][0]['batch']
    if mutation == 'wrong_prefix': plan['batches'][0]['episodes'][0]['id'] = 'R999'
    if mutation == 'wrong_order': plan['batches'][0]['episodes'][0]['episode_order'] = 999
    with pytest.raises(ValueError, match=match):
        cards.validate(plan)


def test_cards_refuse_to_claim_unsupported_recording_root(tmp_path):
    cards = tool('render_collection')
    p = Path(__file__).resolve().parents[1] / 'tools/plans/p2-20261030.json'
    with pytest.raises(ValueError, match='record.sh'):
        cards.render(json.loads(p.read_text()), tmp_path / 'cards', '/tmp/unsupported-root')
    assert not (tmp_path / 'cards').exists()


def test_summary_requires_boolean_exclusion():
    summary = tool('summarize_results')
    with pytest.raises(ValueError, match='excluded'):
        summary.summarize([dict(color='green',round=1,recorded_episode=1,excluded='false',final_in_bowl=True)])


def test_review_rejects_empty_tables(tmp_path):
    import pandas as pd
    review = tool('review_dataset')
    ds=tmp_path/'empty';(ds/'data').mkdir(parents=True);(ds/'meta/episodes').mkdir(parents=True)
    (ds/'meta/info.json').write_text('{"fps":20}')
    pd.DataFrame(columns=['episode_index','frame_index','timestamp']).to_parquet(ds/'data/a.parquet')
    pd.DataFrame(columns=['episode_index','length']).to_parquet(ds/'meta/episodes/a.parquet')
    with pytest.raises(ValueError, match='empty'):
        review.review(ds,tmp_path/'out')


@pytest.mark.parametrize('timestamp,length',[(float('nan'),1),(0.0,1.9)])
def test_review_rejects_invalid_single_frame_metadata(tmp_path,timestamp,length):
    import pandas as pd
    review = tool('review_dataset')
    ds=tmp_path/'invalid';(ds/'data').mkdir(parents=True);(ds/'meta/episodes').mkdir(parents=True)
    (ds/'meta/info.json').write_text('{"fps":20}')
    pd.DataFrame([dict(episode_index=0,frame_index=0,timestamp=timestamp)]).to_parquet(ds/'data/a.parquet')
    pd.DataFrame([dict(episode_index=0,length=length)]).to_parquet(ds/'meta/episodes/a.parquet')
    with pytest.raises(ValueError, match='timestamp|length'):
        review.review(ds,tmp_path/'out')
