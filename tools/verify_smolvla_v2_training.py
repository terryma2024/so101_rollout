"""CPU final verification adds checkpoint-step, FP32 and every full validation count."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def verify_validation_counts(result, frames_by_color, steps):
    expected_steps=[str(s) for s in range(5000,steps+1,5000)]
    if set(result['evaluation'])!=set(expected_steps):
        raise RuntimeError('Missing full validation pass')
    for step in expected_steps:
        for color,count in frames_by_color.items():
            if result['evaluation'][step].get(color,{}).get('samples')!=count:
                raise RuntimeError(f'Partial validation: step{step}/{color}')
    for color,count in frames_by_color.items():
        if result['seen']['validation'].get(color)!=count*len(expected_steps):
            raise RuntimeError('Total validation coverage differs')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['checkpoint','train','audit','receipt','data-approval']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--steps',type=int,required=True);a=p.parse_args()
    temp=a.receipt.with_name(a.receipt.stem+'-base.json')
    subprocess.run([sys.executable,'-m','tools.verify_smolvla_training','--checkpoint',str(a.checkpoint),
                    '--train',str(a.train),'--audit',str(a.audit),'--receipt',str(temp),'--steps',str(a.steps)],check=True)
    result=json.loads((a.audit/'result.json').read_text());data=json.loads(a.data_approval.read_text())
    verify_validation_counts(result,{c:x['frames'] for c,x in data['datasets']['validation']['colors'].items()},a.steps)
    state=json.loads((a.checkpoint.parent/'training_state/training_step.json').read_text())
    if state['step']!=a.steps or state['batch_size']!=32:
        raise RuntimeError('Checkpoint training state does not match expected step/batch')
    from safetensors import safe_open
    with safe_open(a.checkpoint/'model.safetensors',framework='pt',device='cpu') as f:
        if {f.get_slice(k).get_dtype() for k in f.keys()}!={'F32'}:
            raise RuntimeError('Checkpoint contains non-FP32 parameters')
    entry=json.loads((a.audit/'entrypoint.json').read_text())
    if hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest()!=entry['sha256']:
        raise RuntimeError('V2 entrypoint changed after launch')
    receipt=json.loads(temp.read_text());receipt.update(all_saved_parameters_fp32=True,
        full_validation_steps=[5000,10000,15000,20000],checkpoint_training_state=state,
        v2_entrypoint_sha256=entry['sha256'],validation_samples_per_pass=data['datasets']['validation']['frames'])
    a.receipt.write_text(json.dumps(receipt,indent=2)+'\n');print('V2_FINAL_FULLY_VERIFIED')


if __name__=='__main__':main()
