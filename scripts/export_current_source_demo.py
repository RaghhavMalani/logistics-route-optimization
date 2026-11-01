"""Package an actual successful local capture; never synthesize footage."""
from pathlib import Path
import argparse,json,hashlib,shutil,subprocess

ROOT=Path(__file__).resolve().parents[1]
CAPTIONS={
'intro':['PortWatch: restored Company, Port, Vessel and Admin workspaces.','Traffic is simulated; activity-data age and weather freshness are separate.'],
'source':[],  # Filled from the actual source-scene audit, never an assumed report date/count.
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


def edit_video(capture, final, data, plan_path, ffmpeg):
    """Remove recorded idle/loading intervals; retain original speed and UI pixels."""
    if not ffmpeg or not Path(ffmpeg).is_file():
        raise ValueError('An explicit local ffmpeg executable is required for an edit')
    plan=json.loads(plan_path.read_text(encoding='utf8'))
    clips=plan['clips'];previous={};elapsed=0;scenes=[];cuts=[];supplements={}
    required={'intro','source','triage','S06','S07','S10','S12','S17','S16','S03','S25','mobile','scope'}
    if not required.issubset({clip['sceneId'] for clip in clips}):
        raise ValueError('The edit cannot omit a required result/refusal/workflow scene')
    directory=capture/'edited-clips';directory.mkdir(exist_ok=True)
    original_scenes={scene['id']:scene for scene in data['scenes']}
    with (directory/'encoding.log').open('w',encoding='utf8') as log:
        for i,clip in enumerate(clips):
            start=float(clip['sourceStart']);end=float(clip['sourceEnd'])
            take=clip.get('sourceTake',capture.name)
            take_dir=(capture.parent/take).resolve()
            if take_dir.parent!=capture.parent or not take_dir.is_dir():
                raise ValueError('Supplemental footage must be another dedicated local take')
            origin=data if take==capture.name else json.loads((take_dir/'manifest.json').read_text(encoding='utf8'))
            if origin.get('result')!='PASS':raise ValueError('Failed supplementary footage is not deliverable')
            if not 0<=previous.get(take,0)<=start<end<=origin['durationSeconds']+1:
                raise ValueError('Cuts must retain chronological order and actual source coverage')
            previous[take]=end
            if take!=capture.name:
                supplements[take]={'baseCommit':origin['baseCommit'],'captureAt':origin['captureAt'],'basis':origin['basis'],'references':origin['references'],'sourceFiles':origin['sourceFiles'],'manifestSha256':hashlib.sha256((take_dir/'manifest.json').read_bytes()).hexdigest()}
            output=directory/f'clip-{i:02}.mp4'
            subprocess.run([str(ffmpeg),'-hide_banner','-y','-ss',str(start),'-i',str(take_dir/'portwatch-demonstration.webm'),'-t',str(end-start),'-an','-vf','fps=25,format=yuv420p','-c:v','libx264','-preset','veryfast','-crf','20','-threads','2','-movflags','+faststart',str(output)],check=True,stdout=log,stderr=log)
            scene=dict(original_scenes[clip['sceneId']]);scene['startSeconds']=round(elapsed,3)
            scene['title']=clip.get('title',scene['title']);scene['basis']=clip.get('basis',scene['basis']);scene['captionOverride']=clip.get('captions')
            scenes.append(scene)
            cuts.append({**clip,'outputStart':round(elapsed,3),'outputEnd':round(elapsed+end-start,3)})
            elapsed+=end-start
            print(f'Encoded {i+1}/{len(clips)}: {scene["title"]}',flush=True)
        if not 360<=elapsed<=480:
            raise ValueError('Final edit must be between six and eight minutes')
        (directory/'concat.txt').write_text(''.join(f"file 'clip-{i:02}.mp4'\n" for i in range(len(clips))),encoding='utf8')
        subprocess.run([str(ffmpeg),'-hide_banner','-y','-f','concat','-safe','1','-i','concat.txt','-c','copy','-movflags','+faststart',str(final/'portwatch-demonstration.mp4')],cwd=directory,check=True,stdout=log,stderr=log)
    data['rawCaptureDurationSeconds']=data['durationSeconds'];data['rawCaptureScenes']=data['scenes']
    data['rawCaptureFrames']=data.pop('frames',[])
    data['scenes']=scenes;data['durationSeconds']=round(elapsed,3)
    data['supplementalTakes']=supplements
    data['recordingEdit']={'operation':'Chronological trims of idle/loading time only; original playback speed; no invented UI pixels/results.','planSha256':hashlib.sha256(plan_path.read_bytes()).hexdigest(),'clips':cuts}
    data['encoding']={'container':'MP4','videoCodec':'H.264 / libx264','pixelFormat':'yuv420p','frameRate':25,'audio':None,'tool':'Portable FFmpeg n8.1 in ignored work storage; no global installation or PATH change.','toolArchiveSha256':'29f1f119545c5998b52a1e1a23c08fbf1bd4f851e380a718c5b71386125f259a'}
    shutil.copyfile(plan_path,final/'edit-plan.json')
    return 'portwatch-demonstration.mp4','video/mp4'


def export(capture,edit_plan=None,ffmpeg=None):
    capture=capture.resolve();allowed=(ROOT/'work/current-source-demo/video').resolve()
    if not capture.is_relative_to(allowed):raise ValueError('Use only the dedicated local capture directory')
    data=json.loads((capture/'manifest.json').read_text(encoding='utf8'))
    if data.get('result')!='PASS':raise ValueError('A failed capture is not a finished demonstration')
    final=allowed/'final';final.mkdir(parents=True,exist_ok=True)
    source=capture/'portwatch-demonstration.webm'
    if not source.is_file() or source.stat().st_size<10000:raise ValueError('Actual playable recording required')
    if edit_plan:
        video_name,video_type=edit_video(capture,final,data,edit_plan,ffmpeg)
    else:
        shutil.copyfile(source,final/source.name);video_name=source.name;video_type='video/webm'
        data['encoding']={'container':'WebM','videoCodec':'VP8','audio':None,'fallbackReason':'Bounded installed-encoder inspection found PNG and libvpx VP8; H.264/AAC unavailable.'}
    # A retained source-scene frame is readable even if the first capture frame was loading.
    shutil.copyfile(capture/'source.png',final/'poster.png')
    audit=capture/'official-context-audit.json'
    official=json.loads(audit.read_text(encoding='utf8'))['context'] if audit.exists() else data.get('officialContext',{})
    working=next((m for m in official.get('metrics',[]) if m['id']=='WORKING_LISTED_ROWS'),{})
    CAPTIONS['source']=['Actual Paradip Port Authority report; product time is separate from receipt time.',f"Report {official.get('reportDate','unavailable')}: {working.get('value','unavailable')} named working-section rows. Rows can repeat across berths; not unique vessels or available capacity.",f"Capture-time status: {official.get('status','unavailable')}; working section: {working.get('eligibility','unavailable')}. Fixed age/check rules govern consumption.",'Anchorage has its own date-only scope. Counts are not individual waiting hours.','An acknowledged operator criterion associates the fictional owned call by declared destination.']
    CAPTIONS['S16'][0]='Official report context is explicitly reviewed and frozen with this ILLUSTRATIVE weather, passage and cargo comparison.'
    scenes=data['scenes'];duration=data['durationSeconds'];vtt=['WEBVTT',''];chapters=[]
    for i,scene in enumerate(scenes):
        start=scene['startSeconds'];end=scenes[i+1]['startSeconds'] if i+1<len(scenes) else duration
        chapters.append(clock(start)+' '+scene['id']+' — '+scene['title'])
        words=scene.pop('captionOverride',None) or CAPTIONS[scene['id']]
        for j,text in enumerate(words):
            a=start+(end-start)*j/len(words);b=start+(end-start)*(j+1)/len(words)-.05
            vtt += [f'{clock(a)} --> {clock(max(a+.1,b))}',text,'']
    (final/'captions.vtt').write_text('\n'.join(vtt),encoding='utf8')
    (final/'chapters.txt').write_text('\n'.join(chapters)+'\n',encoding='utf8')
    data['rawCaptureManifestSha256']=hashlib.sha256((capture/'manifest.json').read_bytes()).hexdigest()
    audit=capture/'official-context-audit.json'
    if audit.exists():
        original=json.loads(audit.read_text(encoding='utf8'))
        if (data.get('officialContext') or {}).get('evidenceKind')=='SOFTWARE_LIFECYCLE_FIXTURE':
            data['lastIllustrativeContext']=data['officialContext']
            data['manifestProcessingNote']='Official context is taken from the frozen audit downloaded in the real-source scene; the last viewed software context is retained separately. Raw capture manifest is preserved.'
        data['officialContext']=original['context']
        data['officialContextAuditSha256']=hashlib.sha256(audit.read_bytes()).hexdigest()
    data['deliverySha256']={name:hashlib.sha256((final/name).read_bytes()).hexdigest() for name in [video_name,'poster.png','captions.vtt','chapters.txt']}
    (final/'manifest.json').write_text(json.dumps(data,indent=2),encoding='utf8')
    player='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>PortWatch local demonstration</title><style>body{margin:0;background:#0b141d;color:#d9e6ef;font:16px system-ui}main{max-width:1920px;margin:auto}video{width:100%;max-height:90vh}p{margin:12px}</style><main><video controls preload="metadata" poster="poster.png"><source src="VIDEO_NAME" type="VIDEO_TYPE"><track kind="captions" src="captions.vtt" srclang="en" label="English" default></video><p>Actual local UI recording. Official source freshness shown at capture; voyage/source presets and outcomes are illustrative. Silent recording with captions.</p></main></html>'''
    (final/'player.html').write_text(player.replace('VIDEO_NAME',video_name).replace('VIDEO_TYPE',video_type),encoding='utf8')
    print(final)
    print(f'Capture duration {duration:.1f} s; inspect playable metadata and sampled frames before delivery.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--edit-plan',type=Path);p.add_argument('--ffmpeg',type=Path)
    args=p.parse_args();export(args.capture,args.edit_plan,args.ffmpeg)
