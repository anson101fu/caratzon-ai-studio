import {authorize,json,body,validImage,sign} from './_shared.js';
const HOST='https://microsoft-trellis-2.hf.space';
const API=HOST+'/gradio_api';
const maxGlb=80*1024*1024;
function hfToken(env){return typeof env.HF_TOKEN==='string'&&/^hf_[A-Za-z0-9]+$/.test(env.HF_TOKEN.trim())?env.HF_TOKEN.trim():null;}
function fail(code,stage){return Object.assign(new Error(code),{code,stage});}
function classify(text,stage,status){if(/quota|zerogpu.*limit|gpu.*(?:seconds|exceeded)|rate.limit/i.test(text)||status===429)return fail('HF_QUOTA',stage);if(status===401||status===403||/unauthori[sz]ed|invalid token/i.test(text))return fail('HF_AUTH',stage);return fail('HF_FAILED',stage);}
async function hf(url,token,opts={},stage='connect'){
 const r=await fetch(url,{...opts,redirect:'error',headers:{Authorization:'Bearer '+token,...opts.headers}});
 if(!r.ok){let msg=(await r.text()).slice(0,1200);console.warn('TRELLIS upstream',stage,r.status);throw classify(msg,stage,r.status);}
 return r;
}
function fileData(v){if(!v||typeof v!=='object'||typeof v.path!=='string')throw fail('HF_SCHEMA','file');return {path:v.path,meta:{_type:'gradio.FileData'}};}
function safeFile(v){const u=new URL(v?.url||`${API}/file=${v?.path||''}`,HOST);if(u.origin!==HOST||!/^\/(?:gradio_api\/)?file=/.test(u.pathname)||!u.pathname.toLowerCase().endsWith('.glb')||u.search||u.hash)throw fail('HF_SCHEMA','extract');return u.pathname;}
// Same random session_hash is essential: Gradio stores the generated latent state in gr.State.
async function call(name,data,session,token,signal,stage,ignore=false){
 const q=await hf(`${API}/call/${name}`,token,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data,session_hash:session}),signal},stage);
 const {event_id:id}=await q.json();if(typeof id!=='string'||!(/^[\w-]{1,128}$/.test(id)))throw fail('HF_SCHEMA',stage);
 const r=await hf(`${API}/call/${name}/${id}`,token,{signal},stage);if(!r.body)throw fail('HF_SCHEMA',stage);
 // The preview HTML can be large; keep only bounded line buffers and discard the image_to_3d data.
 const reader=r.body.getReader(),decoder=new TextDecoder();let buf='',event='',payload='',discard=false;
 try{while(true){const {value,done}=await reader.read();if(done)break;buf+=decoder.decode(value,{stream:true});let idx;
 while((idx=buf.indexOf('\n'))>=0){let line=buf.slice(0,idx).replace(/\r$/,'');buf=buf.slice(idx+1);
 if(line.startsWith('event:')){event=line.slice(6).trim();payload='';discard=false;}
 else if(line.startsWith('data:')){if(!discard&&!(ignore&&event==='complete'))payload+=(payload?'\n':'')+line.slice(5).trimStart();}
 else if(!line){if(event==='error')throw classify(payload,stage);if(event==='complete'){if(ignore)return null;try{return JSON.parse(payload)}catch{throw fail('HF_SCHEMA',stage)}}event='';payload='';discard=false;}
 if(payload.length>2*1024*1024)throw fail('HF_SCHEMA',stage);
 }
 if(buf.length>512*1024){if(ignore&&event==='complete'&&(discard||buf.startsWith('data:'))){buf='';discard=true;}else throw fail('HF_SCHEMA',stage);}
 }}finally{try{await reader.cancel()}catch{}}
 throw fail('HF_FAILED',stage);
}
export async function runTrellis(d,token,signal,emit){
 const session=crypto.randomUUID().replace(/-/g,'');const res=d.resolution==='1024'?'1024':'512';
 const [,mime,b64]=d.image.match(/^data:(image\/(?:png|jpeg|webp));base64,(.+)$/);const bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));const f=new FormData();f.append('files',new Blob([bytes],{type:mime}),'reference.'+mime.split('/')[1]);
 emit('upload');const uploaded=await (await hf(`${API}/upload`,token,{method:'POST',body:f,signal},'upload')).json();if(!Array.isArray(uploaded)||typeof uploaded[0]!=='string')throw fail('HF_SCHEMA','upload');
 emit('preprocess');const pre=await call('preprocess_image',[fileData({path:uploaded[0]})],session,token,signal,'preprocess');const image=fileData(pre?.[0]);
 emit('generate');const seed=crypto.getRandomValues(new Uint32Array(1))[0]%2147483647;
 await call('image_to_3d',[image,seed,res,7.5,.7,12,5,7.5,.5,12,3,1,0,12,3],session,token,signal,'generate',true);
 emit('extract');const out=await call('extract_glb',[null,300000,2048],session,token,signal,'extract');const path=safeFile(out?.[0]||out?.[1]);return path;
}
export async function onRequestPost(ctx){const denied=await authorize(ctx);if(denied)return denied;const {env,request}=ctx;const token=hfToken(env);if(!token)return json({error:'HF_NOT_CONFIGURED'},503);let d;try{d=await body(request)}catch{return json({error:'HF_BAD_IMAGE'},400)}if(!validImage(d?.image)||d.consent!==true)return json({error:'HF_BAD_IMAGE'},400);
 const abort=new AbortController();const cancel=()=>abort.abort();request.signal?.addEventListener('abort',cancel,{once:true});const timer=setTimeout(cancel,540000);const encoder=new TextEncoder();let ended=false;
 const stream=new ReadableStream({start(controller){const send=(obj)=>{if(!ended)try{controller.enqueue(encoder.encode(JSON.stringify(obj)+'\n'))}catch{ended=true;cancel()}};const heartbeat=setInterval(()=>send({type:'heartbeat'}),10000);(async()=>{try{const path=await runTrellis(d,token,abort.signal,stage=>send({type:'progress',stage}));const exp=Date.now()+600000;const signature=await sign(`${path}|${exp}`,env.STUDIO_ACCESS_CODE);send({type:'done',path,exp,signature});}catch(e){console.warn('TRELLIS stage failed',e.stage||'network',e.code||e.name);send({type:'error',error:e.code||'HF_FAILED',stage:e.stage||'network'});}finally{clearTimeout(timer);clearInterval(heartbeat);request.signal?.removeEventListener('abort',cancel);if(!ended){ended=true;try{controller.close()}catch{}}}})();},cancel(){ended=true;cancel();}});
 return new Response(stream,{headers:{'Content-Type':'application/x-ndjson; charset=utf-8','Cache-Control':'no-store, no-transform','X-Content-Type-Options':'nosniff'}});
}
export async function onRequestGet(ctx){const denied=await authorize(ctx);if(denied)return denied;const {env,request}=ctx;const token=hfToken(env);if(!token)return json({error:'HF_NOT_CONFIGURED'},503);const u=new URL(request.url),path=u.searchParams.get('path')||'',exp=Number(u.searchParams.get('exp')),signature=u.searchParams.get('signature')||'';if(!Number.isFinite(exp)||exp<Date.now()||exp>Date.now()+600000||!/^\/(?:gradio_api\/)?file=/.test(path)||!path.toLowerCase().endsWith('.glb')||path.includes('?')||path.includes('#')||signature!==await sign(`${path}|${exp}`,env.STUDIO_ACCESS_CODE))return json({error:'HF_FILE_EXPIRED'},403);
 try{const r=await hf(HOST+path,token,{},'download');if(Number(r.headers.get('Content-Length'))>maxGlb)return json({error:'HF_FILE_LARGE'},413);if(!r.body)throw fail('HF_FAILED','download');let total=0;const transform=new TransformStream({transform(chunk,c){total+=chunk.byteLength;if(total>maxGlb)throw Error('GLB too large');c.enqueue(chunk)}});return new Response(r.body.pipeThrough(transform),{headers:{'Content-Type':'model/gltf-binary','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}})}catch{return json({error:'HF_FILE_EXPIRED'},502)}
}
