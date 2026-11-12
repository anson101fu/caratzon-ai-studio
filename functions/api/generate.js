import {buildSmartPlan,inspectStoneFree} from './_prompt.js';
import {authorize,json,body,provider,validImage} from './_shared.js';
const instructions={design:'Create a jewellery concept visual from the supplied design brief.',sketch:'Transform the provided jewellery sketch into a photorealistic product rendering, preserving design details.',edit:'Edit the reference jewellery according to the brief; preserve unspecified details.',views:'Create a presentation sheet showing plausible front, side, rear and top concept views of this jewellery. No invented measurements. Not an engineering drawing.',wear:'Show this jewellery being worn by an adult model, tightly cropped without face, preserving the product design and plausible scale.',retouch:'Clean the background to pure white, centre the jewellery, preserve its exact visible design and proportions, improve product photography without adding details.',relief:'Create a detailed relief jewellery concept illustration with fine sculpted surface texture. This is a 2D design preview.'};
export async function onRequestPost(ctx){let denied=await authorize(ctx);if(denied)return denied;const {env,request}=ctx;try{const d=await body(request);if(!Object.hasOwn(instructions,d.tool))return json({error:'Unsupported tool.'},400);let prompt=typeof d.prompt==='string'?d.prompt.slice(0,2400):'';const needsImage=!['design','relief'].includes(d.tool);if(needsImage&&!validImage(d.image))return json({error:'A valid reference image is required.'},400);if(['design','relief','edit'].includes(d.tool)&&!prompt.trim())return json({error:'Design description is required.'},400);let settings=['category','metal','stone','style','zodiac'].map(k=>`${k}: ${String(d.settings?.[k]||'Any').slice(0,80)}`).join('; ');let text=`${instructions[d.tool]} Design brief: ${prompt}. Preferences (ignore Any): ${settings}. Professional jewellery design, accurate visual detail, no brand logos, no watermark. Output one image.`;const engine=d.engine||'cloudflare';
if(engine==='cloudflare'){
 if(needsImage)return json({error:'Free FLUX supports text-to-image only. Use Free Tools V2 for local image processing.'},400);
 if(typeof env.AI?.run!=='function')return json({error:'Cloudflare AI binding missing. Add AI to Production and redeploy.'},503);
 try{
  const lang=['zh','en','ru'].includes(d.lang)?d.lang:'zh';
  let plan;try{plan=await buildSmartPlan(env.AI,prompt,d.settings||{},lang,d.tool)}catch(e){console.error('Smart plan failed',String(e?.message||e));return json({error:'SMART_PLAN_FAILED'},502);}
  for(let attempt=1;attempt<=2;attempt++){
   const fluxPrompt=attempt===1?plan.prompt:('A solid all-metal sculpture, unbroken metal surfaces, no separate inset objects, no stone settings. '+plan.prompt).slice(0,2048);
   const out=await env.AI.run('@cf/black-forest-labs/flux-1-schnell',{prompt:fluxPrompt,steps:8});
   if(typeof out?.image!=='string'||!out.image||!(/^[A-Za-z0-9+/=]+$/.test(out.image)))throw Error('Cloudflare AI returned no valid image.');
   if(plan.noStone){
    let check;try{check=await inspectStoneFree(env.AI,out.image)}catch(e){console.error('Vision check failed',String(e?.message||e));return json({error:'STONE_CHECK_UNAVAILABLE'},502);}
    if(check==='UNSURE')return json({error:'STONE_CHECK_UNAVAILABLE'},422);
    if(check==='FAIL'){if(attempt===1)continue;return json({error:'STONE_CHECK_REJECTED'},422);}
   }
   return json({image:'data:image/jpeg;base64,'+out.image,engine:'cloudflare',plan,check:plan.noStone?'passed':'not_required',attempts:attempt});
  }
 }catch(e){console.error('Cloudflare AI generation failed',String(e?.message||e));return json({error:'FREE_GENERATION_FAILED'},502);}
}
if(engine!=='openai')return json({error:'Unsupported AI engine.'},400);
if(env.ENABLE_PAID_AI!=='true'||!env.OPENAI_API_KEY)return json({error:'Paid OpenAI mode is disabled. Use Cloudflare free mode.'},403);
let model=env.OPENAI_IMAGE_MODEL||'gpt-image-2.5-flare';let data={model,prompt:text,n:1,size:'1024x1024',quality:'medium',output_format:'png'};let url='https://api.openai.com/v1/images/'+(needsImage?'edits':'generations');let result;if(needsImage){const f=new FormData();Object.entries(data).forEach(([k,v])=>f.append(k,String(v)));const [,mime,b64]=d.image.match(/^data:(image\/(?:png|jpeg|webp));base64,(.+)$/);const bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));f.append('image',new Blob([bytes],{type:mime}),'reference.'+mime.split('/')[1]);result=await provider(url,env.OPENAI_API_KEY,{method:'POST',body:f})}else result=await provider(url,env.OPENAI_API_KEY,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});let img=result.data?.[0]?.b64_json;if(!img)throw Error('No image received from provider.');return json({image:'data:image/png;base64,'+img,engine:'openai'});}catch(e){return json({error:e.message||'Image generation failed.'},502)}}
