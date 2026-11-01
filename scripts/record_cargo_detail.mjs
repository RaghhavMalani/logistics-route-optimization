/** Supplemental real UI take: an explicitly selected, separate fictional S16 call. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {chromium}=await import(pathToFileURL(path.join(root,'india-portwatch-terminal/node_modules/playwright/index.mjs')).href);
const base=process.env.DEMO_APP_URL||'http://127.0.0.1:4218';
if(!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base))throw Error('Local recording only');
const out=path.join(root,'work/current-source-demo/video',new Date().toISOString().replaceAll(':','-')+'-cargo-detail');await fs.mkdir(out,{recursive:true});
const manifest={contractVersion:'portwatch-screen-recording-v1',captureKind:'SUPPLEMENTAL_CARGO_DETAIL',baseCommit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),captureAt:new Date().toISOString(),viewport:{width:1920,height:1080},basis:'Separate explicitly selected fictional S16 call; explanatory cargo arithmetic, not the main approved advisory identity.',references:[],frames:[]};
manifest.sourceFiles=Object.fromEntries(await Promise.all(['scripts/record_cargo_detail.mjs','india-portwatch-terminal/src/components/intelligence/CargoCommitmentEvidence.tsx'].map(async f=>[f,createHash('sha256').update((await fs.readFile(path.join(root,f),'utf8')).replaceAll('\r\n','\n')).digest('hex')])));
const browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:manifest.viewport,deviceScaleFactor:1,recordVideo:{dir:out,size:manifest.viewport}});
await context.addInitScript(()=>window.addEventListener('DOMContentLoaded',()=>{const dot=document.createElement('div');dot.style.cssText='position:fixed;width:12px;height:12px;border:2px solid white;border-radius:50%;background:#d99d2488;pointer-events:none;z-index:2147483647;display:none';dot.setAttribute('aria-hidden','true');document.body.appendChild(dot);window.addEventListener('mousemove',e=>{dot.style.display='block';dot.style.left=(e.clientX-6)+'px';dot.style.top=(e.clientY-6)+'px';});}));
const page=await context.newPage();page.setDefaultTimeout(45000);const started=Date.now();const seconds=()=>Math.round((Date.now()-started)/100)/10;
page.on('pageerror',e=>(manifest.runtimeErrors??=[]).push(e.message));
async function click(locator){await locator.scrollIntoViewIfNeeded();const box=await locator.boundingBox();if(box)await page.mouse.move(box.x+box.width/2,box.y+box.height/2,{steps:12});await locator.click();}
async function shot(id){await page.screenshot({path:path.join(out,id+'.png')});manifest.frames.push({id,seconds:seconds()});}
try{
 await page.goto(base+'/login',{waitUntil:'domcontentloaded'});await click(page.getByRole('button',{name:'Company demo',exact:true}));await page.waitForURL('**/company/overview',{waitUntil:'domcontentloaded'});
 await page.goto(base+'/company/global-eye#intelligence-review',{waitUntil:'domcontentloaded'});const scenarios=page.getByTestId('demonstration-scenarios');await click(scenarios.locator('summary'));await scenarios.getByLabel('Shipping demonstration scenario').selectOption('S16');await scenarios.getByRole('checkbox').check();const ready=page.waitForResponse(r=>r.url().endsWith('/demonstrations/select')&&r.request().method()==='POST');await click(scenarios.getByRole('button',{name:'Calculate selected demonstration',exact:true}));const result=await(await ready).json();const problem=result.problem;if(!problem)throw Error('S16 calculation unavailable');
 const evidence=problem.evidence.currentEnvironment;manifest.references.push({scenarioId:'S16-cargo-detail',decisionId:problem.decisionId,evidenceId:evidence.evidenceId,cargoInputVersion:evidence.cargoComparison.inputVersion,assessments:evidence.cargoComparison.options.map(o=>({optionId:o.optionId,handlingHours:o.handlingHours,slackHours:o.slackHours,cutoffAt:o.cutoffAt,readinessAt:o.readinessAt,stages:o.stages}))});
 await click(scenarios.getByRole('button',{name:'Inspect calculated comparison',exact:true}));const decision=page.getByTestId('decision-panel');await click(decision.getByRole('button',{name:'Continue to Decide',exact:true}));await click(decision.getByTestId('decision-review'));await click(decision.getByTestId('decision-approve'));await decision.getByText('Approved:',{exact:false}).first().waitFor();
 await page.goto(base+'/company/overview',{waitUntil:'domcontentloaded'});await click(page.getByRole('button',{name:/Demo role/i}));await click(page.getByRole('menuitem',{name:/Port Authority/}));await page.waitForURL('**/port/overview',{waitUntil:'domcontentloaded'});await page.goto(base+'/port/advisories',{waitUntil:'domcontentloaded'});
 const cargo=page.getByTestId('current-proposal-review').getByTestId('frozen-cargo-comparison');await click(cargo.locator('summary').first());await cargo.locator('summary').first().evaluate(e=>e.scrollIntoView({block:'start'}));manifest.detailStartSeconds=seconds();await shot('cargo-detail-overview');await page.waitForTimeout(12000);
 await cargo.locator('[data-cargo-option]').first().evaluate(e=>e.scrollIntoView({block:'start'}));await shot('cargo-detail-math');await page.waitForTimeout(16000);
 manifest.detailEndSeconds=seconds();manifest.durationSeconds=seconds();manifest.result='PASS';manifest.finishedAt=new Date().toISOString();
}catch(e){manifest.result='FAIL';manifest.error=e.message;await shot('failure');throw e;}
finally{await fs.writeFile(path.join(out,'manifest.json'),JSON.stringify(manifest,null,2));await context.close();await page.video().saveAs(path.join(out,'portwatch-demonstration.webm'));await browser.close();console.log('Output:',out);}
