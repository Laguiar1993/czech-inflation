"""Portable Windows commands; every new data/run directory is explicit."""
import argparse,functools,http.server,json,os,subprocess,sys,webbrowser
from datetime import datetime,timezone
from pathlib import Path
from .runtime import ROOT,configure

def emit(value):print(json.dumps(value,indent=2,default=str))
def stamp():return datetime.now(timezone.utc).isoformat()

def bloomberg_capture(lane,output,end_date,python=None):
    out=Path(output).resolve()
    if out.exists():raise FileExistsError('Choose a new Bloomberg capture directory')
    configs={'nowcast':'tools/forecast_updates_r33/bloomberg_current_config.json','path':'tools/current_path_r34/capture_config.json'}
    interpreter=Path(python).resolve() if python else Path(sys.executable)
    env=dict(os.environ);env.pop('PYTHONPATH',None)
    env['PATH']=os.pathsep.join(str(interpreter.parent/p) for p in ('','Library/bin','Scripts'))+os.pathsep+env.get('PATH','')
    cmd=[str(interpreter),'-B','-m','tools.market_data.probe_bloomberg_candidates','--config',configs[lane],'--output',str(out)]
    if end_date:cmd+=['--end-date',end_date]
    subprocess.run(cmd,cwd=ROOT,env=env,check=True)
    errors=json.loads((out/'errors.json').read_bytes())
    if errors:raise ValueError('Bloomberg capture contains errors; inspect '+str(out/'errors.json'))
    return {'status':'captured','lane':lane,'output':str(out)}

def nowcast(args):
    from tools.forecast_updates_r33 import workflow as w
    ann=Path(args.announcements).resolve() if args.announcements else None
    invoke=w.invoke_r32
    if ann:
        from .runtime import announcement_rows
        announcement_rows(ann)
        def invoke(request,directory):
            copied=directory/'prospective_announcements.csv';copied.write_bytes(ann.read_bytes())
            w.write_new(directory/'portable_input.json',{'announcements_sha256':w.sha(copied.read_bytes()),'source_path':str(ann),'runner_sha256':w.sha(Path(__file__).read_bytes())})
            cmd=[sys.executable,'-B','-m','portable','_r32',request['command'],'--bundle',request['bundle'],'--target',request['target'],'--as-of',request['as_of']]
            if request['live_calendar']:cmd+=['--live-calendar',str(directory/'live_calendar.csv')]
            env=dict(os.environ,CPI_PORTABLE_ANN_PATH=str(copied));scratch=directory/'scratch';scratch.mkdir()
            env.update(TMP=str(scratch),TEMP=str(scratch),TMPDIR=str(scratch))
            with (directory/'adapter.stdout').open('xb') as out,(directory/'adapter.stderr').open('xb') as err:
                result=w.bounded_run(cmd,timeout=request['timeout_seconds'],cwd=ROOT,env=env,stdout=out,stderr=err)
            if result.returncode not in (0,2):raise ValueError('Adapter failed; inspect adapter.stderr')
            return w.read_json(directory/'adapter.stdout')
    result=w.record(args.bundle,args.target,args.as_of or stamp(),args.mode,store=args.store,command='run' if args.command=='nowcast' else 'readiness',live_calendar=args.calendar,timeout=args.timeout,invoke=invoke)
    emit(result)
    return 0 if result['status'] in ('ready','successful') and result['publication']['status']!='failed' else 2

def verify(models=False):
    from .archive import restore,verify_tree
    from .relocation import relocations
    result={'restore':restore(ROOT),'tree':verify_tree(ROOT)}
    with relocations(ROOT):
        from output.inflation_dashboard_r35_delivery.verify import audit
        result['r35']=audit()
        from tools.current_path_r34.run import load_record
        meta,table,history=load_record(ROOT/'output/current_path_r34/final')
        result['path']={'origin':meta['origin'],'rows':len(table),'h0':meta['h0']}
    if models:
        from .parity import check
        result['offline_models']=check()
    return result

def main(argv=None):
    configure();os.chdir(ROOT);argv=list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0]=='_r32':
        from .runtime import announcements
        from tools.live_bundle_r32.cli import main as r32main
        with announcements(os.environ.get('CPI_PORTABLE_ANN_PATH')):return r32main(argv[1:])
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('restore')
    q=sub.add_parser('doctor');q.add_argument('--bloomberg',action='store_true')
    q=sub.add_parser('verify');q.add_argument('--models',action='store_true')
    q=sub.add_parser('serve');q.add_argument('--port',type=int,default=8766);q.add_argument('--directory',type=Path,default=ROOT/'output/inflation_dashboard_r35');q.add_argument('--open',action='store_true')
    q=sub.add_parser('capture-bloomberg');q.add_argument('--lane',choices=['nowcast','path'],required=True);q.add_argument('--output',required=True,type=Path);q.add_argument('--end-date');q.add_argument('--python')
    q=sub.add_parser('capture-public');q.add_argument('--kind',choices=['farm','categories'],required=True);q.add_argument('--output',required=True,type=Path)
    q=sub.add_parser('prepare-nowcast');q.add_argument('--base-bundle',type=Path,default=ROOT/'data/bloomberg_inputs_20260922_foodppi');q.add_argument('--snapshot',required=True,type=Path);q.add_argument('--farm-raw',required=True,type=Path);q.add_argument('--manual-inputs',type=Path);q.add_argument('--target',required=True);q.add_argument('--output',required=True,type=Path);q.add_argument('--as-of')
    for name in ['nowcast','readiness']:
        q=sub.add_parser(name);q.add_argument('--bundle',required=True,type=Path);q.add_argument('--target',required=True);q.add_argument('--calendar',required=True,type=Path);q.add_argument('--as-of');q.add_argument('--mode',choices=['prospective','replay'],default='prospective');q.add_argument('--store',type=Path,default=ROOT/'output/forecast_updates_r33/portable');q.add_argument('--timeout',type=float,default=180);q.add_argument('--announcements',type=Path)
    q=sub.add_parser('prepare-path');q.add_argument('--base-bundle',type=Path,default=ROOT/'data/bloomberg_inputs_20260922_foodppi');q.add_argument('--current-bundle',required=True,type=Path);q.add_argument('--capture',required=True,type=Path);q.add_argument('--farm-raw',required=True,type=Path);q.add_argument('--origin',required=True);q.add_argument('--output',required=True,type=Path);q.add_argument('--as-of')
    q=sub.add_parser('run-path');q.add_argument('--bundle',required=True,type=Path);q.add_argument('--inputs',required=True,type=Path);q.add_argument('--nowcast-run',required=True,type=Path);q.add_argument('--output',required=True,type=Path);q.add_argument('--announcements',type=Path)
    q=sub.add_parser('prepare-momentum');q.add_argument('--capture',required=True,type=Path);q.add_argument('--through',required=True);q.add_argument('--output',required=True,type=Path)
    q=sub.add_parser('momentum');q.add_argument('--prepared',required=True,type=Path);q.add_argument('--output',required=True,type=Path)
    args=p.parse_args(argv)
    try:
        if args.command=='restore':
            from .archive import restore
            emit(restore(ROOT))
        elif args.command=='doctor':
            from .runtime import doctor
            result=doctor(args.bloomberg);emit(result);return 0 if result['ready'] and (not args.bloomberg or result['bloomberg'].get('ready')) else 2
        elif args.command=='verify':emit(verify(args.models))
        elif args.command=='serve':
            directory=args.directory.resolve()
            if not (directory/'index.html').is_file():raise ValueError('Dashboard index.html not found')
            handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(directory))
            server=http.server.ThreadingHTTPServer(('127.0.0.1',args.port),handler);url=f'http://127.0.0.1:{args.port}/'
            print('Dashboard: '+url,flush=True)
            if args.open:webbrowser.open(url)
            server.serve_forever()
        elif args.command=='capture-bloomberg':emit(bloomberg_capture(args.lane,args.output,args.end_date,args.python))
        elif args.command=='capture-public':
            if args.kind=='farm':
                from .sources import capture_farm
                emit(capture_farm(args.output))
            else:
                from tools.momentum_r35.inputs import capture
                emit(capture(args.output))
        elif args.command=='prepare-nowcast':
            from .sources import prepare_nowcast
            emit(prepare_nowcast(args.base_bundle,args.snapshot,args.farm_raw,args.target,args.output,args.manual_inputs,args.as_of))
        elif args.command in ('nowcast','readiness'):return nowcast(args)
        elif args.command=='prepare-path':
            from tools.current_path_r34.inputs import prepare
            result=prepare(args.base_bundle,args.current_bundle,args.capture,args.output,origin=args.origin,as_of=args.as_of or stamp(),farm_raw=args.farm_raw)
            emit({'status':'prepared','output':str(result['output'])})
        elif args.command=='run-path':
            from .runtime import announcements
            from tools.current_path_r34.run import record
            if args.announcements:
                from tools.forecast_updates_r33.workflow import sha
                evidence=json.loads((args.nowcast_run/'portable_input.json').read_bytes())
                if evidence['announcements_sha256']!=sha(args.announcements.read_bytes()):raise ValueError('Path announcement input differs from h0')
            elif (args.nowcast_run/'portable_input.json').exists():raise ValueError('Supply the same --announcements used by h0')
            with announcements(args.announcements):emit(record(args.bundle,args.inputs,args.nowcast_run,args.output))
        elif args.command=='prepare-momentum':
            from tools.momentum_r35.inputs import prepare
            result=prepare(args.capture,args.output,through=args.through);emit({'status':'prepared','output':str(args.output),'month':result['provenance']['through']})
        elif args.command=='momentum':
            from tools.momentum_r35.build import build
            emit(build(args.prepared,args.output))
        return 0
    except (ValueError,FileNotFoundError,FileExistsError,KeyError,subprocess.CalledProcessError) as exc:
        emit({'status':'blocked','reason':str(exc)});return 2
if __name__=='__main__':raise SystemExit(main())
