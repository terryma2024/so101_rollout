"""Regression checks for parameterized historical offline helpers."""
import importlib
import json
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def calibration(tmp_path):
    directory = tmp_path / 'calibration'
    directory.mkdir()
    (directory / 'intrinsics-side.json').write_text(json.dumps({
        'K': [[100, 0, 320], [0, 100, 240], [0, 0, 1]], 'D': [0, 0, 0, 0, 0]}))
    (directory / 'extrinsics-side.json').write_text(json.dumps({
        'position_cm': [0, 20, 10], 'forward': [0, 0, -1],
        'frames': [{'image_up': [0, 1, 0]}]}))
    return directory


def test_supplied_calibration_projection_and_cube_estimates(tmp_path):
    cubes = importlib.import_module('tools.cube_positions')
    cal = calibration(tmp_path)
    projection = cubes.Calibration(cal)
    np.testing.assert_allclose(projection.to_table([320, 240]), [0, 20])
    np.testing.assert_allclose(projection.to_table([330, 240]), [-.9, 20])
    review = tmp_path / 'review'
    review.mkdir()
    image = Image.new('RGB', (640, 480), 'white')
    from PIL import ImageDraw
    ImageDraw.Draw(image).rectangle((315, 235, 325, 245), fill=(0, 150, 0))
    for when in ['first', 'last']:
        image.save(review / f'ep1-side-{when}.jpg', quality=100, subsampling=0)
    layout = tmp_path / 'layout.json'
    layout.write_text(json.dumps({'cells': {'A1': [0, 20], 'B1': [10, 20]}, 'bowl': [0, 25]}))
    result = cubes.estimate(review, cal, layout, tmp_path / 'estimates')
    assert 'estimate' in result['notice'].lower()
    assert result['rows'][0]['green_first'] == {'cm': [0., 20.], 'cell': 'A1', 'bowl_dist': 5.}
    assert result['rows'][0]['red_last'] is None
    assert 'final_in_bowl' not in result['rows'][0]
    assert json.loads((tmp_path / 'estimates/cubes.json').read_text()) == result
    with Image.open(tmp_path / 'estimates/ep1-first-last-preview.jpg') as preview:
        assert max(preview.size) <= 1600
    with pytest.raises(FileExistsError):
        cubes.estimate(review, cal, layout, tmp_path / 'estimates')
    file_output = tmp_path / 'estimates.json'
    cubes.estimate(review, cal, layout, file_output)
    with pytest.raises(FileExistsError):
        cubes.estimate(review, cal, layout, file_output)


def test_missing_calibration_and_unpaired_frames_fail_before_output(tmp_path):
    cubes = importlib.import_module('tools.cube_positions')
    with pytest.raises(FileNotFoundError):
        cubes.Calibration(tmp_path)
    cal = calibration(tmp_path)
    review = tmp_path / 'review'
    review.mkdir()
    Image.new('RGB', (640, 480)).save(review / 'ep1-side-first.jpg')
    layout = tmp_path / 'layout.json'
    layout.write_text(json.dumps({'cells': {'A1': [0, 20]}, 'bowl': [0, 25]}))
    with pytest.raises(ValueError, match='pair'):
        cubes.estimate(review, cal, layout, tmp_path / 'bad-output')
    assert not (tmp_path / 'bad-output').exists()


def test_p0_layout_pdf_has_seven_a4_pages_and_bounded_previews(tmp_path):
    renderer = importlib.import_module('tools.render_evaluation')
    layouts = Path(__file__).resolve().parents[1] / 'tools/plans/control-layouts.json'
    assert json.loads(layouts.read_text())['episodes'][5] == {'green': 'D1', 'red': 'C1'}
    result = renderer.render(layouts, 'fixture-run', tmp_path / 'print-artifacts')
    assert result['pages'] == 7
    assert [x['color'] for x in result['groups']] == ['green', 'red', 'red', 'green', 'green', 'red']
    assert result['groups'][2]['dataset'] == 'eval-p0-fixture-run-red-r2'
    data = Path(result['pdf']).read_bytes()
    assert data.startswith(b'%PDF')
    assert len(re.findall(rb'/Type\s*/Page\b', data)) == 7
    dimensions = re.findall(rb'/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]', data)
    assert len(dimensions) == 7
    assert all(abs(float(w) - 595.2) < 1 and abs(float(h) - 841.92) < 1 for w, h in dimensions)
    previews = list((tmp_path / 'print-artifacts').glob('*-preview.png'))
    assert len(previews) == 7
    for path in previews:
        with Image.open(path) as image:
            assert max(image.size) <= 1600
    with pytest.raises(FileExistsError):
        renderer.render(layouts, 'fixture-run', tmp_path / 'print-artifacts')
