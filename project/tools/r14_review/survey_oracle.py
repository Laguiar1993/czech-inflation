"""One custom-clock bridge integrity oracle; no benchmark outcomes or scoring."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

def main():
    from forecast_independent import fixture_frames,runtime_identity
    from independent_bridge_experiment import forecast_bridge
    from path_integration_r14 import survey_h12
    from survey_benchmark_r14 import dependencies
    called=set();read_files=set();prefix=str(ROOT).casefold()+'\\'
    def profile(frame,event,arg):
        if event=='call':
            name=frame.f_code.co_filename
            if name.casefold().startswith(prefix):called.add(name[len(prefix):].replace('\\','/'))
    def audit(event,args):
        if event=='open' and isinstance(args[0],str):
            name=args[0]
            if name.casefold().startswith(prefix):read_files.add(name[len(prefix):].replace('\\','/'))
    sys.addaudithook(audit);sys.setprofile(profile)
    frames=fixture_frames();origin=pd.Period('2023-08','M');clock=pd.Timestamp('2023-08-25',tz='Europe/Prague')
    results=[forecast_bridge(frames,origin,clock,v) for v in (0.,-50.,100.)]
    baseline=results[0]
    for result in results[1:]:
        assert result['contributions']==baseline['contributions']
        assert result['weights']==baseline['weights']
        assert all(result['path'][h]==baseline['path'][h] for h in range(1,13))
    expected=100*(np.prod([1+baseline['path'][h]/100 for h in range(1,13)])-1)
    assert abs(expected-survey_h12(baseline['path']))<1e-12
    poisoned={k:v.copy() for k,v in frames.items()}
    for key in ('headline','core','regulated','alcohol','components'):
        poisoned[key].loc[poisoned[key].index>=origin]=999.
    for key in ('features','food_features'):
        poisoned[key].loc[poisoned[key].index>origin]=999.
    for col in ('exp12','exp36','household_exp','esi','exp12_x_state'):
        if col in poisoned['features']:poisoned['features'][col]=1e12
    again=forecast_bridge(poisoned,origin,clock,0.)
    assert again['contributions']==baseline['contributions']
    assert all(again['path'][h]==baseline['path'][h] for h in range(1,13))
    sys.setprofile(None)
    runtime=runtime_identity();hashed=dependencies(True)
    report=dict(status='passed',origin=str(origin),clock=clock.isoformat(),h0_probes=[0.,-50.,100.],
        exact_h0_invariance=True,future_and_expectations_poisoning_invariant=True,
        independent_annual_product_difference=abs(expected-survey_h12(baseline['path'])),
        executed_repo_files=sorted(called),executed_files_missing_from_dependencies=sorted(called-set(hashed)),
        read_repo_files=sorted(read_files),read_files_missing_from_dependencies=sorted(read_files-set(hashed)),
        runtime=runtime,scoring='none; no survey values or realised future errors consumed; released historical observations remain model inputs')
    out=ROOT/'output/research_r14/review';out.mkdir(parents=True,exist_ok=True)
    (out/'survey_pre_score_oracle.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
