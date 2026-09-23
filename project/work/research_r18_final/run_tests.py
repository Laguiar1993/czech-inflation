from pathlib import Path
import json,subprocess,sys
out=Path('work/research_r18_final')
log=out/'tests_final.log'
if log.exists():
 (out/'collection_missing_duckdb.log').write_bytes(log.read_bytes())
cmd=json.loads((out/'test_command.json').read_text(encoding='utf-8'))
cmd[-1]='work/pytest_r18_final_suite_runtime'
r=subprocess.run(cmd,text=True,capture_output=True,encoding='utf-8',errors='replace')
log.write_text(r.stdout+'\n'+r.stderr,encoding='utf-8')
(out/'test_command_final.json').write_text(json.dumps(cmd,indent=2),encoding='utf-8')
print(r.stdout[-5500:]);print(r.stderr[-500:]);print('EXIT',r.returncode)
sys.exit(r.returncode)
