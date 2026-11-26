import {authorize,json} from './_shared.js';
export async function onRequest(ctx){
 const denied=await authorize(ctx);if(denied)return denied;
 const {env,request}=ctx;const base=String(env.LOCAL_3D_URL||'').trim().replace(/\/$/,'');const token=String(env.LOCAL_3D_TOKEN||'').trim();
 if(!/^https:\/\/[a-z0-9.-]+$/.test(base)||! /^[a-f0-9]{64}$/.test(token))return json({error:'LOCAL_NOT_CONFIGURED'},503);
 const q=new URL(request.url).searchParams,a=q.get('action'),j=q.get('job'),i=q.get('index');
 if(!/^[a-f0-9]{32}$/.test(j||'')||!['status','chunk','upload','commit'].includes(a)||((a==='chunk'||a==='upload')&&!/^\d{1,4}$/.test(i||'')))return json({error:'BAD_REQUEST'},400);
 const post=a==='upload'||a==='commit';if(request.method!==(post?'POST':'GET'))return json({error:'BAD_METHOD'},405);
 try{let body;if(post){body=await request.arrayBuffer();if(body.byteLength>400000)return json({error:'TOO_LARGE'},413);}
 const r=await fetch(base+'/transfer/'+a+'/'+j+((a==='chunk'||a==='upload')?'/'+i:''),{method:request.method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body,redirect:'manual',signal:AbortSignal.timeout(40000)});
 const d=await r.json();return json(d,r.status);
 }catch{return json({error:'TRANSFER_NETWORK'},503);}
}
