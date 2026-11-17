import {authorize,json,body,validImage} from './_shared.js';
const headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'};
export async function onRequest(ctx){
 const denied=await authorize(ctx);if(denied)return denied;
 const {env,request}=ctx;const base=String(env.LOCAL_3D_URL||'').trim().replace(/\/$/,'');const token=String(env.LOCAL_3D_TOKEN||'').trim();
 if(!/^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(base)||!(/^[a-f0-9]{64}$/.test(token)))return json({error:'LOCAL_NOT_CONFIGURED'},503);
 let path,opts={method:request.method,headers:{Authorization:'Bearer '+token,'User-Agent':'Caratzon-AI-Studio/4.2','Accept':'application/json, model/gltf-binary'},redirect:'manual',signal:AbortSignal.timeout(40000)};
 const u=new URL(request.url);
 if(request.method==='POST'){
  let d;try{d=await body(request)}catch{return json({error:'BAD_IMAGE'},400)}
  if(!validImage(d?.image)||!['pixal','trellis'].includes(d.engine)||d.consent!==true||!['fast','hd','ultra'].includes(d.quality||'ultra'))return json({error:'BAD_IMAGE'},400);
  path='/submit';opts.headers['Content-Type']='application/json';opts.body=JSON.stringify({image:d.image,engine:d.engine,quality:d.quality||'ultra'});
 }else if(request.method==='GET'){
  const action=u.searchParams.get('action'),job=u.searchParams.get('job');
  if(action==='health')path='/health';else if(['job','file'].includes(action)&&/^[a-f0-9]{32}$/.test(job||''))path='/'+action+'/'+job;else return json({error:'BAD_REQUEST'},400);
 }else return json({error:'METHOD'},405);
 if(path.startsWith('/file/'))opts.signal=AbortSignal.timeout(300000);
 try{const r=await fetch(base+path,opts);if(r.status>=300&&r.status<400)return json({error:'LOCAL_REDIRECT'},502);if(path.startsWith('/file/')&&r.ok){const n=Number(r.headers.get('Content-Length'));if(!n||n>80*1024*1024||!r.body)return json({error:'FILE_SIZE'},413);return new Response(r.body,{headers:{...headers,'Content-Type':'model/gltf-binary','Content-Length':String(n),'X-GLB-Bytes':String(n)}});}
  const d=await r.json().catch(()=>null);if(!d||typeof d!=='object'||Array.isArray(d)){const type=r.headers.get('cf-error-type');return json({error:'LOCAL_UPSTREAM_'+r.status+(/^[0-9]{4,5}$/.test(type||'')?'_CF'+type:'')},502);}return json(d,r.ok?r.status:Math.min(599,Math.max(400,r.status)));
 }catch(e){const kind=e?.name;return json({error:kind==='TimeoutError'||kind==='AbortError'?'LOCAL_TIMEOUT':kind==='TypeError'?'LOCAL_FETCH_TYPEERROR':'LOCAL_OFFLINE'},503)}
}
