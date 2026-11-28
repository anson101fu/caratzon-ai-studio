import {authorize,json} from './_shared.js';
export async function onRequest(ctx){
 const denied=await authorize(ctx);if(denied)return denied;
 const {env,request}=ctx,u=new URL(request.url),a=u.searchParams.get('action'),j=u.searchParams.get('job')||'';
 const base=String(env.LOCAL_3D_URL||'').trim().replace(/\/$/,''),token=String(env.LOCAL_3D_TOKEN||'').trim();
 if(!/^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(base)||!/^[a-f0-9]{64}$/.test(token))return json({error:'LOCAL_NOT_CONFIGURED'},503);
 let path,opts={method:request.method,headers:{Authorization:'Bearer '+token},redirect:'manual',signal:AbortSignal.timeout(55000)};
 if(request.method==='POST'&&a==='submit'){
  const n=Number(request.headers.get('Content-Length'));if(n>50*1024*1024)return json({error:'STL_TOO_LARGE'},413);
  const b=await request.arrayBuffer();if(b.byteLength<134||b.byteLength>50*1024*1024)return json({error:'BAD_STL'},400);
  path='/ctb-submit';opts.body=b;opts.headers['Content-Type']='application/octet-stream';
 }else if(request.method==='GET'&&a==='health')path='/ctb-health';
 else if(request.method==='GET'&&['job','file'].includes(a)&&/^[a-f0-9]{32}$/.test(j))path='/ctb-'+a+'/'+j;
 else return json({error:'BAD_REQUEST'},400);
 try{const r=await fetch(base+path,opts);
  if(a==='file'&&r.ok){const n=Number(r.headers.get('Content-Length'));if(!n||n>100*1024*1024||!r.body)return json({error:'CTB_BAD_OUTPUT'},502);
  return new Response(r.body,{headers:{'Content-Type':'application/octet-stream','Content-Length':String(n),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});}
  const d=await r.json().catch(()=>null);return d?json(d,r.status):json({error:'CTB_UPSTREAM'},502);
 }catch{return json({error:'CTB_OFFLINE'},503);}
}
