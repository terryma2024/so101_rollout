"""V2 entry: explicitly promote the official mixed-dtype base to FP32 before optimizer creation."""
import argparse
import hashlib
import json
from pathlib import Path
from tools import train_smolvla as adapter


def fp32_policy_factory(factory):
    def make_policy(*args,**kwargs):
        import torch
        policy=factory(*args,**kwargs).float()
        if any(p.dtype != torch.float32 for p in policy.parameters()):
            raise RuntimeError('V2 requires every policy parameter in FP32')
        return policy
    return make_policy


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--validation-root',type=Path,required=True)
    p.add_argument('--audit',type=Path,required=True)
    a=p.parse_args()
    from lerobot.scripts import lerobot_train as trainer
    entry={'path':str(Path(__file__).resolve()),'sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'all_parameters_fp32':True}
    try:
        with adapter.scoped_overrides(trainer,make_policy=fp32_policy_factory(trainer.make_policy)):
            adapter.run(a.config,a.validation_root,a.audit)
    finally:
        if a.audit.exists():
            import torch
            (a.audit/'entrypoint.json').write_text(json.dumps(entry,indent=2)+'\n')
            if torch.cuda.is_initialized():
                memory={'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved(),'scope':'entire training and evaluation process'}
                (a.audit/'gpu-memory.json').write_text(json.dumps(memory,indent=2)+'\n')


if __name__=='__main__':main()
