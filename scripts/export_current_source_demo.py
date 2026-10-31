"""Package an actual successful local capture; never synthesize footage."""
from pathlib import Path
import argparse,json,hashlib,shutil,html

ROOT=Path(__file__).resolve().parents[1]
CAPTIONS={
'intro':['PortWatch: restored Company, Port, Vessel and Admin workspaces.','Traffic is simulated; activity-data age and weather freshness are separate.'],
'source':['Actual Paradip Port Authority report; product time is separate from receipt time.','The working section lists 19 rows, including completed/departed entries. It is not available berth capacity.','Qualified during the morning collection; LATEST_AVAILABLE at this later capture. Refreshing old bytes cannot restore freshness.','The anchorage section is date-only. Counts are not individual waiting hours.','An acknowledged operator review rule associates the fictional owned voyage by destination.'],
'triage':['The existing queue keeps one row per owned current call.','Source-review responsibility is separate from the workflow stage and next role. No silent plan adoption.'],
'S06':['ILLUSTRATIVE Suez assumption; unrelated to the routine Paradip report.','Existing strategic engine: computed primary and alternative geometry, distance and timing.','An inspectable detour is not certified navigation or an approved route. This preset is not in the port-approach advisory chain.','Stress-horizon uncertainty can favor keeping the current plan or waiting for more information.'],
'S07':['ILLUSTRATIVE counterexample: the hull is already inside the exposed water.','Rerouting is unavailable after the commitment point. No teleport or invented branch.'],
'S10':['ILLUSTRATIVE voyage and hourly source assumptions: declared 240 nm remaining passage.','12 kn and 10 kn reach the same conditional clear approach. Less assumed anchorage waiting does not mean earlier delivery.','Fuel is modeled from explicit consumption assumptions. Complete costs and measured savings remain unavailable.'],
'S12':['ILLUSTRATIVE undeparted hull: departure holding requires a declared permitted location.','At sea the original departure cannot be delayed. Every option uses its own supported hourly approach.'],
'S17':['ILLUSTRATIVE cargo schedule, capacity and schematic handling assumptions.','A slower option misses the required cutoff and is rejected, despite lower modeled fuel.','A rejected alternative does not make a valid current plan fail. No space is booked or reserved.'],
'S16':['ILLUSTRATIVE cargo fit: handling is counted once; the common approach gives equal cargo readiness.','Company explicitly reviews and approves the selected frozen passage option.','The dedicated backend is restarted. Frozen evidence, selected option and Company approval survive.','The scoped Port desk reviews the same proposal and issues through the advisory register.','Vessel acknowledgement and acceptance remain separate human actions. Acceptance is not navigation or cargo execution.','Only after acceptance can Port reproduce a SIMULATED_DEMO_OUTCOME. No independent actual outcome or saving is claimed.'],
'S03':['SOFTWARE LIFECYCLE FIXTURE, not an actual authority revision: ready rows change from 4 to 7.','Exact consumed metric/rule changes require explicit successor review. Earlier evidence and approvals remain inspectable.','The short scene shows the retained revision; API validation separately covers the consumed-binding lifecycle.'],
'S25':['ILLUSTRATIVE unsupported arrival horizon: genuine refusal; no invented clear route.','Missing quantities remain unknown. They are not replaced by zero, unlimited capacity or a best option.'],
'mobile':['Original mobile Layers and Timeline access; the same isolated visitor world.','No replacement interface or simplified scene.'],
'scope':['Original Admin workspace and research evidence remain available.','Weather learning is COLLECTING; both rejected models remain rejected.','No unauthorized CCTV, adopted correction, joint reservation, certified navigation or measured benefit is supplied by presets.']}


def clock(value):
    ms=round(value*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'


def export(capture):
    capture=capture.resolve();allowed=(ROOT/'work/current-source-demo/video').resolve()
    if not capture.is_relative_to(allowed):raise ValueError('Use only the dedicated local capture directory')
    data=json.loads((capture/'manifest.json').read_text())
    if data.get('result')!='PASS':raise ValueError('A failed capture is not a finished demonstration')
    final=allowed/'final';final.mkdir(parents=True,exist_ok=True)
    source=capture/'portwatch-demonstration.webm'
    if not source.is_file() or source.stat().st_size<10000:raise ValueError('Actual playable recording required')
    shutil.copyfile(source,final/source.name)
    shutil.copyfile(capture/'intro.png',final/'poster.png')
    scenes=data['scenes'];duration=data['durationSeconds'];vtt=['WEBVTT',''];chapters=[]
    for i,scene in enumerate(scenes):
        start=scene['startSeconds'];end=scenes[i+1]['startSeconds'] if i+1<len(scenes) else duration
        chapters.append(clock(start)+' '+scene['id']+' — '+scene['title'])
        words=CAPTIONS[scene['id']]
        for j,text in enumerate(words):
            a=start+(end-start)*j/len(words);b=start+(end-start)*(j+1)/len(words)-.05
            vtt += [f'{clock(a)} --> {clock(max(a+.1,b))}',text,'']
    (final/'captions.vtt').write_text('\n'.join(vtt),encoding='utf8')
    (final/'chapters.txt').write_text('\n'.join(chapters)+'\n',encoding='utf8')
    data['rawCaptureManifestSha256']=hashlib.sha256((capture/'manifest.json').read_bytes()).hexdigest()
    audit=capture/'official-context-audit.json'
    if audit.exists():
        original=json.loads(audit.read_text())
        if (data.get('officialContext') or {}).get('evidenceKind')=='SOFTWARE_LIFECYCLE_FIXTURE':
            data['lastIllustrativeContext']=data['officialContext']
            data['manifestProcessingNote']='Official context is taken from the frozen audit downloaded in the real-source scene; the last viewed software context is retained separately. Raw capture manifest is preserved.'
        data['officialContext']=original['context']
        data['officialContextAuditSha256']=hashlib.sha256(audit.read_bytes()).hexdigest()
    data['encoding']={'container':'WebM','videoCodec':'VP8','audio':None,'fallbackReason':'Bounded installed-encoder inspection found PNG and libvpx VP8; H.264/AAC unavailable. No software installed.'}
    data['deliverySha256']={name:hashlib.sha256((final/name).read_bytes()).hexdigest() for name in ['portwatch-demonstration.webm','poster.png','captions.vtt','chapters.txt']}
    (final/'manifest.json').write_text(json.dumps(data,indent=2),encoding='utf8')
    (final/'player.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>PortWatch local demonstration</title><style>body{margin:0;background:#0b141d;color:#d9e6ef;font:16px system-ui}main{max-width:1920px;margin:auto}video{width:100%;max-height:90vh}p{margin:12px}</style><main><video controls preload="metadata" poster="poster.png"><source src="portwatch-demonstration.webm" type="video/webm"><track kind="captions" src="captions.vtt" srclang="en" label="English" default></video><p>Actual local UI recording. Official source freshness shown at capture; voyage/source presets and outcomes are illustrative. Silent recording with captions.</p></main></html>''',encoding='utf8')
    print(final)
    print(f'Capture duration {duration:.1f} s; inspect playable metadata and sampled frames before delivery.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);export(p.parse_args().capture)
