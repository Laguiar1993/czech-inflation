"""Additional anchor descriptions; first-batch evaluator remains frozen."""
import argparse
import json
from pathlib import Path
from tools.research_r21 import evaluate
import r17_common as c


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);args=ap.parse_args()
    evaluate.path(args.root)
    out=args.root/'evaluation';payload=json.loads((out/'replay_data.json').read_text())
    payload['method'].insert(4,'Two anchor candidates let persistent core converge gradually toward the public2% policy target adjusted by a prior-only core/headline spread. Half-lives12/24 months; this is an explicit assumption, not a borrowed CNB forecast. Declared after initial R21 results.')
    for s in payload['series']:
        if s['kind']=='model':
            s['default']=s['id'] in ['STATE_FAST_R15','CORE_FEEDBACK_R21','ANCHOR_HL12_R21']
            if s['id'].startswith('ANCHOR_HL'):s['label']=s['short']='Long-run anchor - '+s['id'].split('_')[1][2:]+'m half-life'
    c.dump(out/'replay_data.json',payload)
    html=out/'cnb_rounds_replayed_r21.html';evaluate.previous.write_replay(html,payload)
    text=html.read_text(encoding='utf-8').replace('Czech CPI · R17 ·','Czech CPI · R21 ·').replace('CNB Rounds Replayed · R17 · historical','CNB Rounds Replayed · R21 · historical').replace('cnb-rounds-r17-visible-v1','cnb-rounds-r21-visible-v1')
    html.write_text(text,encoding='utf-8')
    definitions=json.loads((out/'definitions.json').read_text());definitions['limitations']=payload['method'];c.dump(out/'definitions.json',definitions)
    manifest=json.loads((out/'input_manifest.json').read_text());manifest['inputs'][str(Path(__file__).resolve())]=c.sha(Path(__file__))
    manifest['outputs']={p.name:c.sha(p) for p in out.iterdir() if p.is_file() and p.name!='input_manifest.json'};c.dump(out/'input_manifest.json',manifest)


if __name__=='__main__':main()
