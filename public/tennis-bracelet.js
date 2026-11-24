'use strict';
const $ = id => document.getElementById(id);
let modelUrl = null, currentJob = null;
function updateEstimate(){
 const length=Number($('length').value),stone=Number($('stone').value),spacing=stone*($('shape').value==='round'?1.30:1.40);
 const count=Math.max(18,Math.min(150,Math.round(length/spacing)))-1;
 $('estimate').textContent=`约 ${count} 粒宝石 · 长度 ${(length/10).toFixed(0)} cm · 每粒 ${stone.toFixed(1)} mm · 示意结构（不含加工公差）`;
}
['length','stone','shape','metal','clasp'].forEach(id=>$(id).addEventListener('change',updateEstimate));updateEstimate();
function status(s){$('status').textContent=s}
async function api(action,method='GET',data=null,job=null){
 const code=sessionStorage.getItem('cz-test')||'';
 const url='api/local3d?action='+encodeURIComponent(action)+(job?'&job='+encodeURIComponent(job):'');
 const r=await fetch(url,{method,headers:{'X-Studio-Code':code,...(data?{'Content-Type':'application/json'}:{})},body:data?JSON.stringify(data):undefined,cache:'no-store'});
 if(action==='file'&&r.ok)return r.blob();
 const j=await r.json().catch(()=>({error:'NETWORK_ERROR'}));
 if(!r.ok)throw Error(j.error||'HTTP_'+r.status);
 return j;
}
function wait(ms){return new Promise(resolve=>setTimeout(resolve,ms))}
$('generate').addEventListener('click',async()=>{
 if(currentJob)return;
 $('generate').disabled=true;$('download').disabled=true;
 if(modelUrl){URL.revokeObjectURL(modelUrl);modelUrl=null}
 $('viewer').removeAttribute('src');$('details').textContent='';
 try{
  status('正在检查本地 Bridge…');
  const h=await api('health');
  if(!h.online)throw Error('GPU_OFFLINE');
  if(h.remaining<=0)throw Error('SESSION_LIMIT');
  if(h.busy)throw Error('GPU_BUSY');
  status('正在建立钻石、镶座及扣位结构…');
  const request={length_mm:Number($('length').value),stone_mm:Number($('stone').value),shape:$('shape').value,metal:$('metal').value,clasp:$('clasp').value,consent:true};
  const sub=await api('tennis-submit','POST',request);currentJob=sub.job;
  let done=false;
  for(let i=0;i<120;i++){
   await wait(1000);const x=await api('job','GET',null,currentJob);
   if(x.state==='error')throw Error(x.error||'MODEL_FAILED');
   if(x.state==='done'){done=true;break}
   status('正在建立结构化模型… 已等待 '+(i+1)+' 秒');
  }
  if(!done)throw Error('MODEL_TIMEOUT');
  const b=await api('file','GET',null,currentJob);
  modelUrl=URL.createObjectURL(b);$('viewer').src=modelUrl;$('download').disabled=false;
  $('details').textContent=`模型文件 ${(b.size/1024/1024).toFixed(2)} MB；可旋转、缩放与下载。`;
  status('✅ 模型生成成功！可旋转预览或下载 GLB。');
 }catch(e){status('❌ '+e.message+(e.message==='UNAUTHORIZED'?'；请返回主站重新测试登录。':''))}
 finally{currentJob=null;$('generate').disabled=false}
});
$('download').addEventListener('click',()=>{
 if(!modelUrl)return;
 const a=document.createElement('a');a.href=modelUrl;a.download='caratzon_tennis_bracelet_v1.glb';document.body.append(a);a.click();a.remove();
});
