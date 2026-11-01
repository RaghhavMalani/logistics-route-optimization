/** Actual local UI capture. No mocks, auth injection or fabricated DOM values. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath,pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {chromium}=await import(pathToFileURL(path.join(root,'india-portwatch-terminal/node_modules/playwright/index.mjs')).href);
const quick=process.argv.includes('--quick'),record=!quick;
const workflowOnly=process.argv.includes('--workflow-only');if(workflowOnly&&!quick)throw Error('Workflow-only is validation, not a complete recording');
const base=process.env.DEMO_APP_URL||'http://127.0.0.1:4218';
if(!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base))throw Error('Local capture only; hosting remains deferred');
const out=path.join(root,'work/current-source-demo/video',quick?'validation':new Date().toISOString().replaceAll(':','-'));
await fs.mkdir(out,{recursive:true});
const manifest={contractVersion:'portwatch-screen-recording-v1',baseCommit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),captureAt:new Date().toISOString(),viewport:{width:1920,height:1080},localAppVersion:'current-source-demo-v1',scenes:[],references:[],limitations:['Official report freshness is shown at actual capture time; eligibility is not extended.','Illustrative presets do not enter real archives or learning.','Rerouting is a strategic comparison, not a connected port-approach advisory or safe navigation.','Fuel is modeled; complete costs, reservations, actual execution and measured savings remain unavailable.','Weather learning collecting; both model candidates remain rejected.'],audio:'NONE; captions and narration script supplied separately'};
const files=['backend/app/routes/demonstrations.py','src/portwatch_os/decision/demonstrations.py','src/portwatch_os/intelligence/public_port_context.py','src/portwatch_os/intelligence/port_context_review.py','src/portwatch_os/decision/current_arrival.py','india-portwatch-terminal/src/components/intelligence/DemonstrationScenarios.tsx','india-portwatch-terminal/src/components/intelligence/PortOperationalContext.tsx','india-portwatch-terminal/src/components/intelligence/FrozenWeatherBasis.tsx','india-portwatch-terminal/src/services/current-inputs.ts','india-portwatch-terminal/src/services/port-context.ts','scripts/local_demo_backend.py','scripts/restart_local_demo_backend.ps1','scripts/record_current_source_demo.mjs'];
const changed=execFileSync('git',['diff','--name-only','HEAD','--','backend','src','scripts','india-portwatch-terminal'],{cwd:root,encoding:'utf8'}).trim().split('\n');
const added=execFileSync('git',['ls-files','--others','--exclude-standard','--','backend','src','scripts','india-portwatch-terminal'],{cwd:root,encoding:'utf8'}).trim().split('\n');
files.push(...[...changed,...added].filter(f=>/\.(py|tsx?|mjs|ps1)$/.test(f)&&!files.includes(f)));
manifest.sourceHashNormalization='LF line endings';
manifest.sourceState='Base commit plus scoped source files identified by SHA-256; final handoff commit also includes validation documentation.';
manifest.sourceFiles=Object.fromEntries(await Promise.all(files.map(async f=>[f,createHash('sha256').update((await fs.readFile(path.join(root,f),'utf8')).replaceAll('\r\n','\n')).digest('hex')])));
let ready=false;
for(let attempt=0;attempt<180;attempt++){try{const response=await fetch('http://127.0.0.1:8817/api/demo/session',{signal:AbortSignal.timeout(2000)});if(response.status<500){ready=true;break;}}catch{}await new Promise(resolve=>setTimeout(resolve,1000));}
if(!ready)throw Error('Dedicated local backend must be reachable before capture; no sign-in bypass or invented fallback');
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:manifest.viewport,deviceScaleFactor:1,...(record?{recordVideo:{dir:out,size:manifest.viewport}}:{})});
if(record)await context.addInitScript(()=>window.addEventListener('DOMContentLoaded',()=>{const pointer=document.createElement('div');pointer.setAttribute('aria-hidden','true');pointer.style.cssText='position:fixed;display:none;width:12px;height:12px;border:2px solid white;border-radius:50%;background:#d99d2488;box-shadow:0 0 3px #000;pointer-events:none;z-index:2147483647';document.body.appendChild(pointer);window.addEventListener('mousemove',event=>{pointer.style.display='block';pointer.style.left=(event.clientX-6)+'px';pointer.style.top=(event.clientY-6)+'px';});}));
manifest.recordingOverlay=record?'Visible cursor indicator only; no application values or labels changed':'NONE';
const page=await context.newPage();page.setDefaultTimeout(45000);
const started=Date.now();page.on('pageerror',error=>(manifest.runtimeErrors??=[]).push(error.message));
const seconds=()=>Math.round((Date.now()-started)/100)/10;
page.on('response',async response=>{
  try{
    const url=new URL(response.url());
    if(url.pathname.endsWith('/intelligence/port-context')&&response.ok()){
      const body=await response.json();if(body.context?.evidenceKind!=='SOFTWARE_LIFECYCLE_FIXTURE')manifest.officialContext=body.context;else manifest.lastIllustrativeContext=body.context;
    }
  }catch{}
});
async function navigate(url){return page.goto(url,{waitUntil:'domcontentloaded'});}
async function until(t){if(!quick){while(seconds()<t)await page.waitForTimeout(Math.min(1000,(t-seconds())*1000));}}
async function shot(id){await page.screenshot({path:path.join(out,`${id}.png`)});(manifest.frames??=[]).push({id,seconds:seconds()});}
function scene(id,title,basis){manifest.scenes.push({id,title,basis,startSeconds:seconds()});console.log(`${id}: ${title}`);}
async function click(locator){await locator.scrollIntoViewIfNeeded();const box=await locator.boundingBox();if(box)await page.mouse.move(box.x+box.width/2,box.y+box.height/2,{steps:12});await locator.click();}
async function intelligence(){
  const dialog=page.getByRole('dialog',{name:'Connected global intelligence',exact:true});
  if(new URL(page.url()).pathname!='/company/global-eye'){
    await navigate(base+'/company/global-eye#intelligence-review');await dialog.waitFor({state:'visible'});
  }else if(!await dialog.isVisible()){
    const close=page.getByTestId('decision-float').getByRole('button',{name:'Close panel',exact:true});if(await close.isVisible())await click(close);
    await click(page.getByRole('button',{name:'Global intelligence',exact:true}));await dialog.waitFor({state:'visible'});
  }
  await page.getByTestId('demonstration-scenarios').waitFor({state:'visible'});
}
async function choose(id){
  await intelligence();const panel=page.getByTestId('demonstration-scenarios');if(await panel.getAttribute('open')===null)await click(panel.locator('summary'));
  await panel.getByLabel('Shipping demonstration scenario').selectOption(id);await panel.getByRole('checkbox').check();
  const ready=page.waitForResponse(r=>r.url().endsWith('/demonstrations/select')&&r.request().method()==='POST');
  await click(panel.getByRole('button',{name:'Calculate selected demonstration',exact:true}));const response=await ready;
  if(!response.ok())throw Error(`Scenario ${id} refused: ${response.status()}`);
  const result=await response.json();await fs.writeFile(path.join(out,`${id}-result.json`),JSON.stringify(result,null,2));
  if(result.problem){const p=result.problem;manifest.references.push({scenarioId:id,decisionId:p.decisionId,optionIds:p.options.map(o=>o.optionId),evidenceId:p.evidence.currentEnvironment?.evidenceId||null,sourceSha256:p.evidence.currentEnvironment?.responseSha256||null,status:result.status});}
  else manifest.references.push({scenarioId:id,status:result.status,missingInputs:result.missingInputs});
  return {panel,result};
}
async function declareCurrentRule(){
 const source=page.getByTestId('port-operational-context');const summary=source.getByText('Declare an operator review criterion for this owned call',{exact:true});
 const details=summary.locator('..');if(await details.getAttribute('open')===null)await click(summary);
 await source.getByLabel('Port context voyage').selectOption('PWD-001');await source.getByLabel('Port context metric').selectOption('WORKING_LISTED_ROWS');await source.getByLabel('Operator review row threshold').fill('20');await source.getByRole('checkbox',{name:/I explicitly declare INPRT/}).check();await click(source.getByRole('button',{name:'Declare INPRT context review',exact:true}));await source.getByText(/Saved rule WORKING_LISTED_ROWS/).waitFor();
}
async function inspectBoundJourney(){
 const selected=await choose('S16');await declareCurrentRule();await click(selected.panel.getByRole('button',{name:'Inspect calculated comparison',exact:true}));
 await click(page.getByRole('button',{name:'Edit inputs / saved comparisons',exact:true}));const editor=page.getByTestId('port-context-choices');await editor.getByRole('checkbox').check();
 const ready=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/decisions/problems')&&r.request().method()==='POST');await click(page.getByRole('button',{name:'Compare in the original decision panel',exact:true}));const response=await ready;if(!response.ok())throw Error('Explicit source-bound successor refused');const problem=await response.json();const env=problem.evidence.currentEnvironment;const binding=env.portContextBindings?.[0];if(!binding||binding.evidenceKind!=='OFFICIAL_PUBLIC_REPORT_CONTEXT')throw Error('Real official context was not frozen');
 manifest.references.push({scenarioId:'S16-source-reviewed-successor',decisionId:problem.decisionId,optionIds:problem.options.map(o=>o.optionId),evidenceId:env.evidenceId,officialOriginalSha256:binding.originalSha256,metricId:binding.metric.id,metricValue:binding.metric.value,operatorThreshold:binding.rule.threshold,predecessorDecisionId:selected.result.problem.decisionId});
 await fs.writeFile(path.join(out,'S16-source-reviewed-successor.json'),JSON.stringify(problem,null,2));return {...selected.result,problem};
}
async function inspect(id){const selected=await choose(id);await click(selected.panel.getByRole('button',{name:'Inspect calculated comparison',exact:true}));await page.getByTestId('decision-panel').waitFor();return selected.result;}
async function closeDialogs(){for(const name of ['Close fleet review','Close intelligence']){const button=page.getByRole('button',{name,exact:true});if(await button.isVisible())await click(button);}}
async function role(label){await closeDialogs();await click(page.getByRole('button',{name:/Demo role/i}));await click(page.getByRole('menuitem',{name:new RegExp(label)}));await page.waitForURL(base+({'Port Authority':'/port/overview','Vessel Bridge':'/vessel/overview','Fleet Command':'/company/overview','National Command':'/admin/radar'}[label]),{waitUntil:'domcontentloaded'});}
async function reviewAndApprove(scope){
  const decide=scope.getByRole('button',{name:'Continue to Decide',exact:true});await decide.waitFor({state:'visible'});await click(decide);
  await click(scope.getByTestId('decision-review'));await scope.getByTestId('decision-approve').waitFor();
  await click(scope.getByTestId('decision-approve'));await scope.getByText('Approved:',{exact:false}).first().waitFor();
}
async function advisoryAction(card,target){
  const done=page.waitForResponse(r=>/\/advisories\/[^/]+\/transition$/.test(new URL(r.url()).pathname)&&r.request().method()==='POST'&&r.request().postDataJSON()?.target===target);
  await click(card.getByTestId('advisory-action-'+target));const response=await done;if(!response.ok())throw Error('Advisory '+target+' refused: '+response.status());const value=await response.json();(manifest.workflowEvents??=[]).push({atSeconds:seconds(),advisoryId:value.advisoryId,state:value.state});await page.waitForTimeout(400);
}
try{
  if(workflowOnly){await navigate(base+'/login');await click(page.getByRole('button',{name:'Company demo',exact:true}));await page.waitForURL('**/company/overview',{waitUntil:'domcontentloaded'});}
  else {
  scene('intro','Restored Company map and four workspaces','Original interface, simulated traffic');
  await navigate(base+'/login');await click(page.getByRole('button',{name:'Company demo',exact:true}));await page.waitForURL('**/company/overview',{waitUntil:'domcontentloaded'});await shot('intro');await until(25);
  scene('source','Official Paradip receipt and capture-time freshness','Actual retained authority metadata; fictional destination declaration');
  await intelligence();const source=page.getByTestId('port-operational-context');await source.waitFor();await source.scrollIntoViewIfNeeded();await page.waitForTimeout(1500);await shot('source');
  await click(source.getByText('Original, interpretation and display scope',{exact:true}));
  const audit=page.waitForEvent('download');await click(source.getByRole('button',{name:'Download port context audit',exact:true}));await(await audit).saveAs(path.join(out,'official-context-audit.json'));
  await click(source.getByText('Declare an operator review criterion for this owned call',{exact:true}));await source.getByLabel('Port context voyage').selectOption('PWD-001');await source.getByLabel('Port context metric').selectOption('WORKING_LISTED_ROWS');await source.getByLabel('Operator review row threshold').fill('15');await source.getByRole('checkbox',{name:/I explicitly declare INPRT/}).check();await click(source.getByRole('button',{name:'Declare INPRT context review',exact:true}));await source.getByText(/Saved rule WORKING_LISTED_ROWS/).waitFor();await shot('source-rule');await until(75);
  scene('triage','Owned-call destination context and source responsibility','Actual retained context, no count-to-hours inference');
  await click(page.getByRole('button',{name:'Close intelligence',exact:true}));await navigate(base+'/company/overview');await click(page.getByRole('button',{name:/Fleet review queue/}));await page.waitForTimeout(1200);await shot('triage');await until(115);await closeDialogs();
  scene('S06','Computed strategic reroute','Fictional 720-hour Suez assumption; unrelated to the Paradip report');
  const route=await inspect('S06');const alternative=route.problem.options.find(o=>o.action==='REROUTE');if(!alternative?.geometry)throw Error('S06 has no computed reroute geometry');await click(page.getByTestId('decision-panel').getByText(alternative.label,{exact:true}).first());await shot('reroute');await until(155);
  scene('S07','Commitment-point refusal','Fictional hull already inside the exposed water');const refusal=await inspect('S07');if(refusal.problem.options.some(o=>o.action==='REROUTE'))throw Error('Committed S07 unexpectedly offers rerouting');await shot('route-refusal');await until(180);
  scene('S10','Slower speed, same clear approach','Software hourly forecast and declared 240 nm passage');await inspect('S10');await shot('same-approach');await until(215);
  scene('S12','Permitted departure holding','Fictional undeparted call and named permitted holding assumption');await inspect('S12');await shot('departure');await until(240);
  scene('S17','Required cargo cutoff defeats lower fuel','Software schedule/capacity/handling assumptions, no reservation');await inspect('S17');await shot('cargo-refusal');await until(270);
  }
  scene('S16','Cargo fit and connected human workflow','Explicit software hourly fixture, cargo and voyage declarations');const journey=await inspectBoundJourney();await shot('cargo-fit');await reviewAndApprove(page.getByTestId('decision-panel'));await shot('company-approved');
  const before=manifest.references.find(r=>r.scenarioId==='S16-source-reviewed-successor');
  if(process.argv.includes('--restart-backend')){
    execFileSync(process.env.PWSH||'pwsh',['-NoProfile','-File',path.join(root,'scripts/restart_local_demo_backend.ps1')],{cwd:root,stdio:'ignore',timeout:30000});
    let alive=false;manifest.restartWaitStarted=seconds();for(let n=0;n<180;n++){await page.waitForTimeout(1000);try{const r=await fetch('http://127.0.0.1:8817/api/demo/session',{signal:AbortSignal.timeout(2000),headers:{Connection:'close'}});if(r.status<500){alive=true;break;}}catch{}}manifest.restartReadyAt=seconds();
    if(!alive)throw Error('Dedicated backend did not recover');manifest.actualBackendRestart=true;
  }
  console.log('workflow: restart returned');await navigate(base+'/company/overview');await role('Port Authority');console.log('workflow: Port role');await navigate(base+'/port/advisories');const port=page.getByTestId('current-proposal-review');const reviewed=port.getByTestId('frozen-port-context');await reviewed.waitFor();await click(reviewed.locator('summary'));await shot('port-source-binding');await click(port.getByRole('button',{name:'Review Company weather proposal',exact:true}));await reviewAndApprove(port);console.log('workflow: Port approved');await click(port.getByTestId('decision-handoff'));
  let card=page.getByTestId('advisory-card').filter({hasText:'PW Meridian'}).first();await card.waitFor();await click(card.locator('button').first());await advisoryAction(card,'under_review');await advisoryAction(card,'issued');console.log('workflow: issued');await shot('port-issued');await until(310);
  await role('Vessel Bridge');await navigate(base+'/vessel/advisories');card=page.getByTestId('advisory-card').filter({hasText:'PW Meridian'}).first();await click(card.locator('button').first());await advisoryAction(card,'acknowledged');await advisoryAction(card,'accepted');console.log('workflow: accepted');await click(page.getByRole('button',{name:/^Answered/}));await shot('vessel-accepted');await until(335);
  await role('Port Authority');await navigate(base+'/port/advisories');await click(page.getByRole('button',{name:'Run frozen demo outcome',exact:true}));await page.getByTestId('current-demo-outcome').waitFor();await shot('simulated-outcome');manifest.connectedJourney=before;await until(355);
  await role('Fleet Command');scene('S03','Explicit source revision; originals retained','Software lifecycle fixture, not an actual authority revision');await choose('S03');const daily=page.getByTestId('port-operational-context');await daily.scrollIntoViewIfNeeded();await shot('fixture-before');const scenarios=page.getByTestId('demonstration-scenarios');await click(scenarios.getByRole('button',{name:'Explicit fixture update: ready rows 4 → 7',exact:true}));await daily.getByText(/ANCHORAGE READY ROWS: 7/).first().waitFor();await shot('fixture-after');await until(382);
  scene('S25','Unknown horizon is a refusal','Insufficient software hourly coverage, no fabricated clear route');await choose('S25');await shot('unknown');await until(398);
  scene('mobile','Original mobile Layers and Timeline','Same visitor world; no replacement scene');await navigate(base+'/company/overview');await closeDialogs();await page.setViewportSize({width:390,height:844});await page.getByTestId('fleet-command-panel').getByRole('button',{name:'Layers and filters',exact:true}).click();await page.getByTestId('mobile-map-layers').waitFor();await shot('mobile-layers');await page.getByRole('button',{name:'Return to inspector',exact:true}).click();await page.getByTestId('fleet-command-panel').getByRole('button',{name:'Timeline controls',exact:true}).click();await page.getByTestId('mobile-map-timeline').waitFor();await shot('mobile-timeline');await page.getByRole('button',{name:'Return to inspector',exact:true}).click();await page.setViewportSize(manifest.viewport);await until(410);
  scene('scope','Restored workspaces and explicit limits','No operational safety, booking or measured benefit claimed');await role('National Command');await page.waitForTimeout(1000);await shot('admin');await until(420);
  manifest.finishedAt=new Date().toISOString();manifest.durationSeconds=seconds();manifest.result='PASS';
}catch(error){manifest.result='FAIL';manifest.error=String(error.message);await shot('failure');throw error;}
finally{
  await fs.writeFile(path.join(out,'manifest.json'),JSON.stringify(manifest,null,2));
  await context.close();if(record){const video=page.video();await video.saveAs(path.join(out,'portwatch-demonstration.webm'));}await browser.close();console.log('Output:',out);
}
