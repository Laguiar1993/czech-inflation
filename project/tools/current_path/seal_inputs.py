"""Package explicitly prepared path CSVs; does not fetch or certify freshness."""
from pathlib import Path
import argparse,json,sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.current_path.run import PATH_FILES,PATH_UNITS,sha,load_path_inputs


def seal(source,output,notes):
    if not isinstance(notes,str) or not notes.strip():raise ValueError('Source notes required')
    source=Path(source).resolve();output=Path(output).resolve()
    payloads={name:(source/name).read_bytes() for name in PATH_FILES}
    output.mkdir(parents=True,exist_ok=False)
    for name,payload in payloads.items():
        with (output/name).open('xb') as stream:stream.write(payload)
    manifest=dict(schema=1,units=PATH_UNITS,source_notes=notes,
        captured_at_utc=datetime.now(timezone.utc).isoformat(),source_directory=str(source),
        files={name:sha(output/name) for name in PATH_FILES},
        caveat='Only packages supplied CSVs; release dates are caller declarations, freshness is checked by the forecast runner.')
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    load_path_inputs(output)
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--source-notes',required=True)
    a=p.parse_args();print(seal(a.source,a.output,a.source_notes))
