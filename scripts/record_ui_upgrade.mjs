/** Loopback-only, normal-login UI acceptance and actual screen recording.
 * No route mocks, clock fixes, identity injection or edited application values.
 * All generated/private material stays in ignored work/. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {chromium}=await import(pathToFileURL(path.join(root,'india-portwatch-terminal/node_modules/playwright/index.mjs')).href);
const base=process.env.DEMO_APP_URL||'http://127.0.0.1:4220';
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(base))throw Error('Loopback only; hosting is deferred');
const out=path.join(root,'work/ui-visual-upgrade-20261101/video');await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1920,height:1080},reducedMotion:'reduce',recordVideo:{dir:out,size:{width:1920,height:1080}}});
const page=await context.newPage();page.setDefaultTimeout(60000);
const manifest={startedAt:new Date().toISOString(),base,scenes:[],errors:[],checks:[],basis:'Normal demo login. Explicit S16 software forecasts and fictional voyage/cargo; current public sources inspected separately. No operational outcome claim.'};
page.on('pageerror',e=>manifest.errors.push(e.message));const start=Date.now();
const elapsed=()=>Math.round((Date.now()-start)/100)/10;
const click=async l=>{await l.scrollIntoViewIfNeeded();await l.click();};
async function scene(id,caption){manifest.scenes.push({id,caption,start:elapsed()});console.log(id);await fs.writeFile(path.join(out,'progress.json'),JSON.stringify(manifest,null,2));}
async function shot(id){await page.waitForTimeout(1500);await page.screenshot({path:path.join(out,id+'.png')});}
async function navigate(p){await page.goto(base+p,{waitUntil:'domcontentloaded'});}
async function role(name){for(const n of ['Close fleet review','Close intelligence']){const b=page.getByRole('button',{name:n,exact:true});if(await b.isVisible())await click(b);}await click(page.getByRole('button',{name:/Demo role/i}));await click(page.getByRole('menuitem',{name:new RegExp(name)}));}
async function approve(scope){await click(scope.getByRole('button',{name:'Continue to Decide',exact:true}));await click(scope.getByTestId('decision-review'));await click(scope.getByTestId('decision-approve'));await scope.getByText('Approved:',{exact:false}).first().waitFor();}
async function action(card,target){const done=page.waitForResponse(r=>r.url().match(/\/advisories\/[^/]+\/transition$/)&&r.request().postDataJSON()?.target===target);await click(card.getByTestId('advisory-action-'+target));const r=await done;if(!r.ok())throw Error(target+' refused '+r.status());const body=await r.json();manifest.checks.push({state:target,advisoryId:body.advisoryId});return body;}
let problem,study,successor;
try{
 await scene('entry','Restored Company workspace. Traffic is explicitly simulated; the world clock and source age are separate.');
 await navigate('/login');await click(page.getByRole('button',{name:'Company demo',exact:true}));await page.getByTestId('fleet-command-panel').waitFor();await shot('company');
 await scene('sources','Retained public products: original dates, first receipt, last successful check and explicit unavailable states.');
 await navigate('/company/global-eye#intelligence-review');await page.getByTestId('port-operational-context').waitFor();await shot('sources');
 const disclosure=page.getByText('Public research products',{exact:true});if(await disclosure.isVisible())await click(disclosure);
 await scene('globe','The original God’s Eye globe is retained. Layers establish context; they do not imply a closure or measured delay.');
 await click(page.getByRole('tab',{name:'Globe',exact:true}));await click(page.getByRole('button',{name:'Open God’s Eye globe',exact:true}));await page.locator('.cesium-widget canvas').waitFor();await shot('globe');
 await scene('comparison','Explicit software case S16. This connected approach example is separate from strategic rerouting.');
 await click(page.getByRole('tab',{name:'Scenarios',exact:true}));const scenarios=page.getByTestId('demonstration-scenarios');await scenarios.waitFor();if(await scenarios.getAttribute('open')===null)await click(scenarios.locator('summary'));
 await scenarios.getByLabel('Shipping demonstration scenario').selectOption('S16');await scenarios.getByRole('checkbox').check();
 let done=page.waitForResponse(r=>r.url().endsWith('/demonstrations/select')&&r.request().method()==='POST');await click(scenarios.getByRole('button',{name:'Calculate selected demonstration',exact:true}));let r=await done;if(!r.ok())throw Error('S16 refused');problem=(await r.json()).problem;
 await click(scenarios.getByRole('button',{name:'Inspect calculated comparison',exact:true}));await page.getByTestId('decision-panel').waitFor();await shot('comparison');
 await scene('cargo','Company-private commercial declaration: multiple consignments share ship-level fuel once. Example terms are fictional.');
 await click(page.getByRole('tab',{name:'Business',exact:true}));const business=page.getByRole('region',{name:'Company commercial review',exact:true});await business.getByLabel('Explicit commercial example').selectOption('MULTI');await click(business.getByRole('button',{name:'Prepare editable fictional declaration',exact:true}));await click(business.getByRole('button',{name:'Evaluate declared components',exact:true}));await click(business.getByRole('tab',{name:'Impact',exact:true}));await shot('impact');
 await scene('insurance','Insurance review checks supplied evidence and expiry. Listed areas alone do not establish cover, premium or payable recovery.');
 await click(business.getByRole('tab',{name:'Insurance',exact:true}));await shot('insurance');
 await scene('uncertainty','Reproducible shadow sensitivity: one declared shared downstream delay distribution. Draws are not operational targets.');
 await click(business.getByRole('tab',{name:'Uncertainty',exact:true}));await business.getByRole('checkbox').check();done=page.waitForResponse(r=>r.url().endsWith('/commercial/evaluate')&&r.request().method()==='POST');await click(business.getByRole('button',{name:'Run and retain shadow study',exact:true}));r=await done;if(!r.ok())throw Error('Shadow study refused '+r.status());study=await r.json();await page.getByRole('region',{name:'Shadow uncertainty results'}).waitFor();await shot('uncertainty');
 done=page.waitForResponse(r=>r.url().endsWith('/successor')&&r.request().method()==='POST');await click(business.getByRole('button',{name:'Create commercial successor for fresh review',exact:true}));r=await done;if(!r.ok())throw Error('Successor refused');successor=await r.json();
 await scene('company-approval','A new comparison freezes the private study version. A human reviews and approves a feasible alternative; earlier evidence remains inspectable.');
 const alternative=successor.options.find(o=>o.status==='FEASIBLE'&&!o.isBaseline);if(!alternative)throw Error('No feasible alternative for this software journey');
 const decision=page.getByTestId('decision-panel');await click(decision.getByRole('tab',{name:/^Options/}));await click(decision.getByRole('button',{name:new RegExp(alternative.label.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'))}).first());await approve(decision);await shot('company-approved');
 manifest.comparison={decisionId:successor.decisionId,optionId:alternative.optionId,contextHash:study.contextHash,worldSampleHash:study.uncertainty.worldSampleHash};
 if(process.argv.includes('--restart-backend')){
  await scene('restart','The owned loopback backend is restarted. Durable comparison, selected option and private study survive.');
  execFileSync(process.env.PORTWATCH_PYTHON||'python',[path.join(root,'scripts/restart_local_provider_backend.py')],{cwd:root,timeout:30000,stdio:'ignore'});
  let ready=false;for(let n=0;n<120;n++){try{const h=await fetch('http://127.0.0.1:8820/api/demo/session',{signal:AbortSignal.timeout(1500)});if(h.status<500){ready=true;break;}}catch{}await new Promise(resolve=>setTimeout(resolve,1000));}if(!ready)throw Error('Backend recovery timed out');manifest.actualBackendRestart=true;
 }
 await navigate('/company/overview');await page.getByTestId('fleet-command-panel').waitFor();
 await scene('worklist','Fleet review uses a searchable worklist, exact saved comparison links and selected detail.');
 await click(page.getByRole('button',{name:/Fleet review queue/}));await page.getByTestId('company-fleet-triage').waitFor();await shot('worklist');await click(page.getByRole('button',{name:'Close fleet review',exact:true}));
 await scene('port','Port reviews the frozen Company proposal and issues an advisory. Private Company terms are not shared.');
 await role('Port Authority');await navigate('/port/advisories');const port=page.getByTestId('current-proposal-review');await click(port.getByRole('button',{name:'Review Company weather proposal',exact:true}));await approve(port);await click(port.getByTestId('decision-handoff'));let card=page.getByTestId('advisory-card').filter({hasText:'PW Meridian'}).first();await card.waitFor();await click(card.locator('button').first());await action(card,'under_review');await action(card,'issued');await shot('port-issued');
 await scene('vessel','Vessel acknowledgement and acceptance are retained responses, not proof of an executed voyage.');
 await role('Vessel Bridge');await navigate('/vessel/advisories');card=page.getByTestId('advisory-card').filter({hasText:'PW Meridian'}).first();await click(card.locator('button').first());await action(card,'acknowledged');await action(card,'accepted');await click(page.getByRole('button',{name:/^Answered/}));await shot('vessel-accepted');
 await scene('outcome','The outcome is explicitly SIMULATED_DEMO_OUTCOME. It is software/workflow evidence, not measured savings or model accuracy.');
 await role('Port Authority');await navigate('/port/advisories');await click(page.getByRole('button',{name:'Run frozen demo outcome',exact:true}));await page.getByTestId('current-demo-outcome').waitFor();await shot('simulated-outcome');
 await scene('admin','Admin retains source-quality and research access. Weather learning remains collecting; rejected models remain rejected.');await role('National Command');await navigate('/admin/data');await click(page.getByRole('button',{name:/Inspect evidence for/}).first());await page.getByTestId('source-quality-inspector').waitFor();await shot('admin');
 await role('Fleet Command');await scene('mobile','Narrow-screen Layers and Timeline stay accessible in the original workspace.');await navigate('/company/overview');await page.setViewportSize({width:390,height:844});const fleet=page.getByTestId('fleet-command-panel');await click(fleet.getByRole('button',{name:'Layers and filters',exact:true}));await page.getByTestId('mobile-map-layers').waitFor();await shot('mobile-layers');await click(page.getByRole('button',{name:'Return to inspector',exact:true}));await click(fleet.getByRole('button',{name:'Timeline controls',exact:true}));await page.getByTestId('mobile-map-timeline').waitFor();await shot('mobile-timeline');await click(page.getByRole('button',{name:'Return to inspector',exact:true}));
 manifest.result='PASS';manifest.duration=elapsed();
}catch(error){manifest.result='FAIL';manifest.error=error.message;await page.screenshot({path:path.join(out,'failure.png')});console.error(error.message);process.exitCode=1;}
finally{
 manifest.finishedAt=new Date().toISOString();await fs.writeFile(path.join(out,'manifest.json'),JSON.stringify(manifest,null,2));
 const stamp=s=>{const ms=Math.round(s*1000);return `${String(Math.floor(ms/3600000)).padStart(2,'0')}:${String(Math.floor(ms/60000)%60).padStart(2,'0')}:${String(Math.floor(ms/1000)%60).padStart(2,'0')}.${String(ms%1000).padStart(3,'0')}`;};
 await fs.writeFile(path.join(out,'captions.vtt'),'WEBVTT\n\n'+manifest.scenes.map((s,i)=>`${i+1}\n${stamp(s.start)} --> ${stamp(manifest.scenes[i+1]?.start??elapsed())}\n${s.caption}\n`).join('\n'));
 const video=page.video();await context.close();await video.saveAs(path.join(out,'ui-upgrade.webm'));await browser.close();console.log(manifest.result,out);
}
