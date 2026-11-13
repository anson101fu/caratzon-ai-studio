import {authorize,json,body,validImage,sign} from './_shared.js';
const HOST='https://microsoft-trellis-2.hf.space';
const API=HOST+'/gradio_api';
const BUILD='3.6.5';
const maxGlb=80*1024*1024;
function hfToken(env){return typeof env.HF_TOKEN==='string'&&/^hf_[A-Za-z0-9]+$/.test(env.HF_TOKEN.trim())?env.HF_TOKEN.trim():null;}
function fail(code,stage,detail=''){return Object.assign(new Error(code),{code,stage,detail});}
// Only expose bounded, constructed diagnostics, never upstream payloads or credentials.
function classify(text,stage,status){const t=String(text||'');
 const nums=t.match(/(\d{1,6})\s*s(?:ec(?:onds?)?)?\s+requested\s+vs\.?\s+(\d{1,6})\s*s(?:ec(?:onds?)?)?\s+left/i);
 const http=Number.isInteger(status)?'HTTP '+status:'Space';
 if(/space app has reached its GPU limit|shared (?:anonymous )?(?:GPU )?(?:quota|limit)/i.test(t))return fail('HF_SHARED_QUOTA',stage,http+' · shared Space GPU limit');
 if(/pending credits|too many ZeroGPU credits allocated/i.test(t))return fail('HF_RATE_LIMIT',stage,http+' · pending GPU tasks');
 if(/illegal duration|larger than the maximum allowed/i.test(t))return fail('HF_FAILED',stage,http+' · GPU duration limit');
 if(/ZeroGPU.{0,80}(?:quota|seconds|limit)|(?:GPU|GPU time).{0,80}(?:quota|seconds left|exceeded)|(?:seconds|\bs\b) (?:requested|left).*?(?:quota|left)/i.test(t))return fail('HF_QUOTA',stage,http+' · '+(nums?'requested '+nums[1]+'s / left '+nums[2]+'s':'GPU quota rejection'));
 if(status===429||/rate.limit|too many requests|quota/i.test(t))return fail(stage==='preprocess'?'HF_BACKGROUND_LIMIT':'HF_RATE_LIMIT',stage,http+' · rate limit');
 if(status===401||status===403||/unauthori[sz]ed|invalid token/i.test(t))return fail('HF_AUTH',stage,http+' · authorization');return fail('HF_FAILED',stage,http+' · upstream failure');}

const HUB='https://huggingface.co/api';
async function readHub(path,token,signal){try{const r=await fetch(HUB+path,{redirect:'manual',headers:{Authorization:'Bearer '+token,Accept:'application/json'},signal});if(!r.ok)return {status:r.status};return {status:r.status,data:await r.json()};}catch{return {status:0};}}
export async function quotaInfo(token,signal){const r=await readHub('/spaces/zero-gpu/quota',token,signal);const d=r.data;if(!d||typeof d.current!=='number'||typeof d.base!=='number'||!Number.isFinite(d.current)||!Number.isFinite(d.base)||d.base<=0)return {status:r.status,available:false};return {status:r.status,available:true,base:d.base,remaining:Math.max(0,d.current),resetsAt:typeof d.resetsAt==='string'?d.resetsAt:null};}
async function checkQuota(token,signal,stage){const q=await quotaInfo(token,signal);if(q.available&&q.remaining<120)throw fail('HF_QUOTA',stage,'Hub quota: '+Math.floor(q.remaining)+'s left / 120s requested');if(!q.available)throw fail(q.status===401?'HF_AUTH':'HF_QUOTA_UNKNOWN',stage);}
async function statusInfo(token,signal){const [who,quota]=await Promise.all([readHub('/whoami-v2',token,signal),quotaInfo(token,signal)]);return {build:BUILD,account:typeof who.data?.name==='string'?who.data.name:null,authStatus:who.status,quota};}
async function hf(url,token,opts={},stage='connect'){
 // Workers supports manual/follow only. Never forward credentials to a redirect target.
 let r;
 try{r=await fetch(url,{...opts,redirect:'manual',headers:{...opts.headers,Authorization:'Bearer '+token,'X-HF-Authorization':'Bearer '+token}});}
 catch(e){console.warn('TRELLIS transport',stage,e?.name||'Error');throw fail('HF_FAILED',stage,'Network transport');}
 if(r.status>=300&&r.status<400){console.warn('TRELLIS unexpected redirect',stage,r.status);throw fail('HF_FAILED',stage,'Unexpected redirect HTTP '+r.status);}
 if(!r.ok){let msg=(await r.text()).slice(0,1200);const e=classify(msg,stage,r.status);console.warn('TRELLIS upstream',stage,r.status,e.detail);throw e;}
 return r;
}
function fileData(v){if(!v||typeof v!=='object'||typeof v.path!=='string')throw fail('HF_SCHEMA','file');return {path:v.path,meta:{_type:'gradio.FileData'}};}
function safeFile(v){const u=new URL(v?.url||`${API}/file=${v?.path||''}`,HOST);if(u.origin!==HOST||!/^\/(?:gradio_api\/)?file=/.test(u.pathname)||!u.pathname.toLowerCase().endsWith('.glb')||u.search||u.hash)throw fail('HF_SCHEMA','extract');return u.pathname;}
// Same random session_hash is essential: Gradio stores the generated latent state in gr.State.
// Gradio 6.1 queues messages by session_hash. /call/.../<event_id> reads by
// event_id instead, so it cannot be paired with a custom persistent session.
// Submit by name, then read the full queue stream by the SAME session hash.
async function readEndpoints(token,signal){
 const conf=await (await hf(HOST+'/config',token,{signal},'config')).json();
 if(!Array.isArray(conf.dependencies))throw fail('HF_SCHEMA','config','Space config missing dependencies');
 const map={};for(const name of ['preprocess_image','image_to_3d','extract_glb']){
  const found=conf.dependencies.find(d=>String(d.api_name||'').replace(/^\//,'')===name);
  if(!found||!Number.isInteger(found.id))throw fail('HF_SCHEMA','config','Missing endpoint: '+name);
  map[name]=found.id;
 }return map;
}
async function call(name,data,session,token,signal,stage,ignore=false,endpoints){
 const q=await hf(`${API}/queue/join`,token,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data,fn_index:endpoints[name],session_hash:session,event_data:null}),signal},stage);
 const {event_id:id}=await q.json();if(typeof id!=='string'||!(/^[\w-]{1,128}$/.test(id)))throw fail('HF_SCHEMA',stage);
 const r=await hf(`${API}/queue/data?session_hash=${encodeURIComponent(session)}`,token,{signal,headers:{Accept:'text/event-stream'}},stage);if(!r.body)throw fail('HF_SCHEMA',stage);
 const reader=r.body.getReader(),decoder=new TextDecoder();let line='',tail='',large=false,complete=false,result;
 function append(s){if(!large){line+=s;if(line.length>1024*1024){if(!ignore||!/^data:\s*\{\s*"msg"\s*:\s*"process_completed"/.test(line)||!line.slice(0,512).includes(id))throw fail('HF_SCHEMA',stage);large=true;tail=line.slice(-4096);line=line.slice(0,512);}}else tail=(tail+s).slice(-4096);}
 function finish(){if(large){if(!/}\s*,\s*"success"\s*:\s*true\s*,\s*"title"\s*:\s*(?:null|"[^"\\]*")\s*}\s*$/.test(tail))throw fail('HF_FAILED',stage);complete=true;result=null;}
 else if(line.startsWith('data:')){let msg;try{msg=JSON.parse(line.slice(5))}catch{throw fail('HF_SCHEMA',stage)}
  if(msg.msg==='unexpected_error'){console.warn('TRELLIS queue error',stage,msg.session_not_found?'session_not_found':'upstream_error');throw classify(String(msg.message||''),stage);}
  if(msg.msg==='process_completed'&&msg.event_id===id){if(msg.success!==true){const error=[msg.output?.error,msg.output?.message,msg.title].filter(x=>typeof x==='string').join(' ');console.warn('TRELLIS job failed',stage,error?'upstream_error':'no_detail');throw classify(error,stage);}if(!ignore&&!Array.isArray(msg.output?.data))throw fail('HF_SCHEMA',stage);complete=true;result=ignore?null:msg.output.data;}
  if(msg.msg==='close_stream'&&complete)return true;
 }line='';tail='';large=false;return false;}
 try{while(true){const {value,done}=await reader.read();const chunk=done?decoder.decode():decoder.decode(value,{stream:true});let start=0,idx;
 while((idx=chunk.indexOf('\n',start))!==-1){append(chunk.slice(start,idx));if(finish())return result;start=idx+1;}append(chunk.slice(start));if(done){if(line||large)finish();if(complete)return result;break;}
 }}finally{try{await reader.cancel()}catch{}}
 console.warn('TRELLIS queue ended without completion',stage);throw fail('HF_FAILED',stage);
}
export async function runTrellis(d,token,signal,emit){
 emit('quota');await checkQuota(token,signal,'quota');
 const endpoints=await readEndpoints(token,signal);
 const session=crypto.randomUUID().replace(/-/g,'');const res=d.resolution==='1024'?'1024':'512';
 const [,mime,b64]=d.image.match(/^data:(image\/(?:png|jpeg|webp));base64,(.+)$/);const bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));const f=new FormData();f.append('files',new Blob([bytes],{type:mime}),'reference.'+mime.split('/')[1]);
 emit('upload');const uploaded=await (await hf(`${API}/upload`,token,{method:'POST',body:f,signal},'upload')).json();if(!Array.isArray(uploaded)||typeof uploaded[0]!=='string')throw fail('HF_SCHEMA','upload');
 let image=fileData({path:uploaded[0]});
 // Browser prepared black-background square uses the same input convention as TRELLIS preprocess.
 // Do not invoke external RMBG when the local cutout was used.
 if(d.prepared!==true){emit('preprocess');const pre=await call('preprocess_image',[image],session,token,signal,'preprocess',false,endpoints);image=fileData(pre?.[0]);}
 await checkQuota(token,signal,'generate');emit('generate');const seed=crypto.getRandomValues(new Uint32Array(1))[0]%2147483647;
 await call('image_to_3d',[image,seed,res,7.5,.7,12,5,7.5,.5,12,3,1,0,12,3],session,token,signal,'generate',true,endpoints);
 await checkQuota(token,signal,'extract');emit('extract');const out=await call('extract_glb',[null,300000,2048],session,token,signal,'extract',false,endpoints);let path;for(const item of out||[]){try{path=safeFile(item);break}catch{}}if(!path)throw fail('HF_SCHEMA','extract');return path;
}
export async function onRequestPost(ctx){const denied=await authorize(ctx);if(denied)return denied;const {env,request}=ctx;const token=hfToken(env);if(!token)return json({error:'HF_NOT_CONFIGURED'},503);let d;try{d=await body(request)}catch{return json({error:'HF_BAD_IMAGE'},400)}if(!validImage(d?.image)||d.consent!==true||(d.prepared===true&&!d.image.startsWith('data:image/png;base64,')))return json({error:'HF_BAD_IMAGE'},400);
 const abort=new AbortController();const cancel=()=>abort.abort();request.signal?.addEventListener('abort',cancel,{once:true});const timer=setTimeout(cancel,540000);const encoder=new TextEncoder();let ended=false;
 const stream=new ReadableStream({start(controller){const send=(obj)=>{if(!ended)try{controller.enqueue(encoder.encode(JSON.stringify(obj)+'\n'))}catch{ended=true;cancel()}};const heartbeat=setInterval(()=>send({type:'heartbeat'}),10000);(async()=>{try{const path=await runTrellis(d,token,abort.signal,stage=>send({type:'progress',stage}));const exp=Date.now()+600000;const signature=await sign(`${path}|${exp}`,env.STUDIO_ACCESS_CODE);send({type:'done',path,exp,signature});}catch(e){console.warn('TRELLIS stage failed',e.stage||'network',e.code||e.name,e.detail||'');send({type:'error',error:e.code||'HF_FAILED',stage:e.stage||'network',detail:e.detail||''});}finally{clearTimeout(timer);clearInterval(heartbeat);request.signal?.removeEventListener('abort',cancel);if(!ended){ended=true;try{controller.close()}catch{}}}})();},cancel(){ended=true;cancel();}});
 return new Response(stream,{headers:{'Content-Type':'application/x-ndjson; charset=utf-8','Cache-Control':'no-store, no-transform','X-Content-Type-Options':'nosniff'}});
}
export async function onRequestGet(ctx){const denied=await authorize(ctx);if(denied)return denied;const {env,request}=ctx;const token=hfToken(env);if(!token)return json({error:'HF_NOT_CONFIGURED'},503);const u=new URL(request.url);if(u.searchParams.get('status')==='1')return json(await statusInfo(token,request.signal));const path=u.searchParams.get('path')||'',exp=Number(u.searchParams.get('exp')),signature=u.searchParams.get('signature')||'';if(!Number.isFinite(exp)||exp<Date.now()||exp>Date.now()+600000||!/^\/(?:gradio_api\/)?file=/.test(path)||!path.toLowerCase().endsWith('.glb')||path.includes('?')||path.includes('#')||signature!==await sign(`${path}|${exp}`,env.STUDIO_ACCESS_CODE))return json({error:'HF_FILE_EXPIRED'},403);
 try{const r=await hf(HOST+path,token,{},'download');if(Number(r.headers.get('Content-Length'))>maxGlb)return json({error:'HF_FILE_LARGE'},413);if(!r.body)throw fail('HF_FAILED','download');let total=0;const transform=new TransformStream({transform(chunk,c){total+=chunk.byteLength;if(total>maxGlb)throw Error('GLB too large');c.enqueue(chunk)}});return new Response(r.body.pipeThrough(transform),{headers:{'Content-Type':'model/gltf-binary','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}})}catch{return json({error:'HF_FILE_EXPIRED'},502)}
}
