#!/usr/bin/env python3
"""Summarize a completed read-only coverage audit; no dataset changes."""
import argparse,json,csv,collections,hashlib,math
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--evidence',type=Path,required=True)
args=parser.parse_args()
O=args.evidence.resolve()
if (O/'review-scope.json').exists():parser.error('Already finalized evidence; use a fresh audit output')
r=json.load(open(O/'episodes.json'))
def save(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def dist(a,b):return 999 if 'unknown' in (a,b) else abs(ord(a[0])-ord(b[0]))+abs(int(a[1])-int(b[1]))
near=[]
for green,red in [('C2','C3'),('C3','C2')]:
 for color in ['green','red']:
  for split in ['train','validation']:
   hits=[x for x in r if x['split']==split and x['color']==color and dist(x['green_position'],green)<=1 and dist(x['red_position'],red)<=1]
   near.append(dict(green=green,red=red,color=color,split=split,episodes=len(hits),definition='each color within <=1 orthogonal nominal cell (4cm); includes exact',origins=[x['origin'] for x in hits]))
save('near-neighbor-coverage.json',near)
print('NEAR',[(x['green'],x['red'],x['color'],x['split'],x['episodes']) for x in near])
for key in ['origin','numeric_sha256']:
 c=collections.Counter(x[key] for x in r);print(key,'duplicates',sum(v-1 for v in c.values()))
# Coarse position labels preserve unknown and must not claim millimeter precision.
for x in r:
 x['position_precision']='nominal 4cm cell; no mm accuracy guarantee'
 x['action_review_current']='initial frame only; no new full-process review'
 x['action_review_prior']='process-frame human review accepted' if 'p2-' in x['source_dataset'] else 'legacy acceptance; current audit does not independently certify full motion'
 x['first_grasp_success']='unknown'
save('episodes.json',r)
fields=[k for k in r[0] if k not in ['current_cell_candidates','planned_match']]
with (O/'episodes.csv').open('w') as f:
 w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(r)
review={'current_initial_frame_visual':266,'current_full_process_visual':0,'prior_process_sample_review_reused':81,'prior_process_scope':'green P2 accepted40 + red P2 accepted41; sampled contact sheets, not frame-by-frame','position_unknown':[x['origin'] for x in r if 'unknown' in [x['green_position'],x['red_position']]],'viewed_sheets':[str(p) for p in sorted((O/'sheets').glob('*.jpg'))],'current_full_video_decode':False,'frozen_derived_file_sha256_all_match':True,'trajectory_hash_recomputed':266,'within_or_cross_split_duplicate_trajectories':0,'caveat':'Image labels are nominal nearest cells; projected-cell/contour heuristics are not a calibrated uncertainty estimate. No claims of continuous manual viewing.'}
save('review-scope.json',review)
rows=[]
for batch,split in [('v2-hard-a','train'),('v2-hard-b','train'),('v2-hard-c','validation')]:
 for green,red in [('C2','C3'),('C3','C2')]:
  for color in ['green','red']:
   for variant,dx,dy in [('column-minus',-3,0),('nominal',0,0),('column-plus',3,0)]:rows.append(dict(batch=batch,split=split,green_cell=green,red_cell=red,task_color=color,target_dx_mm=dx,target_dy_mm=dy,distractor_dx_mm=dx,distractor_dy_mm=dy,offset_axis='paper column-number direction; dx is along that axis, not robot x',variant=variant,status='planned_not_collected'))
save('collection-plan.json',{'status':'proposal_not_training_manifest','episodes':rows,'total':36,'new_train':24,'new_validation':12,'rules':['Each batch is independently reset and placed; interleave both colors and layouts; randomize reproducibly within batch.','Freeze whole batch split before recording; retries remain in original batch.','Keep both cameras and task text; record actual initial placement; no hardware or camera changes.','Reject wrong color, operator assistance or failed/repeated grasp under existing acceptance rules; never backfill discarded examples silently.','Only export after episode mapping, action audit and train-only normalization.'],'proposed_totals_if_all_accepted':{'train':{'episodes':238,'green':113,'red':125},'validation':{'episodes':64,'green':38,'red':26}}})
# Frozen original maps retained for exact provenance, not claimed new export.
save('frozen-split-reference.json',{'status':'existing_split_reference_only','records':r})
# Independent exact initial JPEG duplicate check (does not exclude near visual duplicates).
images=collections.defaultdict(list)
for x in r:
 p=O/f"first/{x['split']}-{x['derived_episode_index']:03d}.jpg";images[hashlib.sha256(p.read_bytes()).hexdigest()].append(x['origin'])
save('initial-image-duplicates.json',{'exact_jpeg_duplicate_groups':[v for v in images.values() if len(v)>1],'near_visual_duplicates_checked':False})
summary=[]
for group in dict.fromkeys(x['source_dataset'] for x in r):
 a=[x for x in r if x['source_dataset']==group];summary.append(dict(group=group,split=a[0]['split'],color=a[0]['color'],episodes=len(a),frames=sum(x['frames'] for x in a),unknown=sum('unknown' in [x['green_position'],x['red_position']] for x in a),nominal_layouts=len(set((x['green_position'],x['red_position']) for x in a)),planned_nominal_disagreements=sum(not all(x['planned_match'].values()) for x in a)))
save('source-summary.json',summary);print(summary)
