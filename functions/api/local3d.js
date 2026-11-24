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
  if(u.searchParams.get('action')==='tennis-submit'){
   if(d?.consent!==true||typeof d?.length_mm!=='number'||d.length_mm<130||d.length_mm>230||typeof d?.stone_mm!=='number'||d.stone_mm<1.5||d.stone_mm>5||!['round','square'].includes(d.shape)||!['silver','gold','rose'].includes(d.metal)||!['box','lobster'].includes(d.clasp))return json({error:'BAD_BRACELET_PARAMS'},400);
   path='/tennis-submit';opts.headers['Content-Type']='application/json';opts.body=JSON.stringify({length_mm:d.length_mm,stone_mm:d.stone_mm,shape:d.shape,metal:d.metal,clasp:d.clasp});
  }else if(u.searchParams.get('action')==='image-submit'){
   if(!['text','edit'].includes(d?.mode)||typeof d.prompt!=='string'||d.prompt.length<3||d.prompt.length>3000||d.consent!==true||(d.mode==='edit'&&!validImage(d.image)))return json({error:'BAD_IMAGE_REQUEST'},400);
   path='/image-submit';opts.headers['Content-Type']='application/json';opts.body=JSON.stringify({mode:d.mode,prompt:d.prompt,...(d.mode==='edit'?{image:d.image}:{})});
  }else{
  if(!validImage(d?.image)||!['pixal','trellis'].includes(d.engine)||d.consent!==true||!['fast','hd','ultra'].includes(d.quality||'ultra'))return json({error:'BAD_IMAGE'},400);
  path='/submit';opts.headers['Content-Type']='application/json';opts.body=JSON.stringify({image:d.image,engine:d.engine,quality:d.quality||'ultra'});
  }
 }else if(request.method==='GET'){
  const action=u.searchParams.get('action'),job=u.searchParams.get('job');
  if(action==='health')path='/health';else if(['job','file','image-job','image-file'].includes(action)&&/^[a-f0-9]{32}$/.test(job||''))path='/'+action+'/'+job;else return json({error:'BAD_REQUEST'},400);
 }else return json({error:'METHOD'},405);
 if(path.startsWith('/file/')||path.startsWith('/image-file/'))opts.signal=AbortSignal.timeout(300000);
 try{const r=await fetch(base+path,opts);if(r.status>=300&&r.status<400)return json({error:'LOCAL_REDIRECT'},502);if((path.startsWith('/file/')||path.startsWith('/image-file/'))&&r.ok){const n=Number(r.headers.get('Content-Length'));if(!n||n>(path.startsWith('/image-file/')?10:80)*1024*1024||!r.body)return json({error:'FILE_SIZE'},413);return new Response(r.body,{headers:{...headers,'Content-Type':path.startsWith('/image-file/')?'image/png':'model/gltf-binary','Content-Length':String(n),...(path.startsWith('/file/')?{'X-GLB-Bytes':String(n)}:{})}});}
  const d=await r.json().catch(()=>null);if(!d||typeof d!=='object'||Array.isArray(d)){const type=r.headers.get('cf-error-type');return json({error:'LOCAL_UPSTREAM_'+r.status+(/^[0-9]{4,5}$/.test(type||'')?'_CF'+type:'')},502);}return json(d,r.ok?r.status:Math.min(599,Math.max(400,r.status)));
 }catch(e){const kind=e?.name;return json({error:kind==='TimeoutError'||kind==='AbortError'?'LOCAL_TIMEOUT':kind==='TypeError'?'LOCAL_FETCH_TYPEERROR':'LOCAL_OFFLINE'},503)}
}
