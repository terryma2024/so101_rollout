"""Recording shell integration runs only copied launchers and fake commands."""
import json
import subprocess

import pytest
from test_launchers import checkout


@pytest.mark.parametrize('status,answer,record', [(0,'',True),(1,'\n',False),(1,'N\n',False),(1,'n\n',False),(1,'',False),(1,'y\n',True),(1,'Y\n',True),(1,'yes\n',False),(124,'\n',False),(2,'\n',False)])
def test_confirmation_and_order(checkout, status, answer, record):
    root, fake, capture, env = checkout
    log = root/'order'
    (root/'camera_settings.sh').write_text(f'#!/bin/bash\necho lock >> "{log}"\nexit 0\n')
    timeout = fake/'timeout'
    timeout.write_text(f'''#!/bin/bash
if [[ "$*" == *so101_rollout.camera.preflight* ]]; then
  echo check >> "{log}"
  exit {status}
fi
exit 0
''')
    result = subprocess.run([str(root/'record.sh'),'unit-test-unused','1'], input=answer, text=True, capture_output=True, env=env)
    calls = [json.loads(line) for line in capture.read_text().splitlines()] if capture.exists() else []
    recorded = any('so101_rollout.operations.record_viz' in c['args'] for c in calls)
    assert recorded == record
    assert log.read_text().splitlines() == ['lock','check']
    assert ('y/N' in result.stdout) == (status != 0)
    if status and record: assert '未通过仍继续' in result.stdout
    decisions = list((root/'evidence').glob('*/decision.json'))
    assert len(decisions) == 1
    assert json.loads(decisions[0].read_text())['proceed'] == record


def test_lock_failure_requires_same_confirmation(checkout):
    root, fake, capture, env = checkout
    (root/'camera_settings.sh').write_text('#!/bin/bash\nexit 19\n')
    result = subprocess.run([str(root/'record.sh'),'unit-test-unused'], input='\n', text=True, capture_output=True, env=env)
    assert 'y/N' in result.stdout
    assert '锁定' in result.stdout
    calls = [json.loads(line) for line in capture.read_text().splitlines()] if capture.exists() else []
    assert not any('so101_rollout.operations.record_viz' in c['args'] for c in calls)
