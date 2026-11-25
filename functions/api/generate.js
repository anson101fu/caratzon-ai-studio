import {buildSmartPlan,inspectStoneFree} from './_prompt.js';
import {authorize,json,body,provider,validImage} from './_shared.js';
const instructions={design:'Create a jewellery concept visual from the supplied design brief.',sketch:'Transform the provided jewellery sketch into a photorealistic product rendering, preserving design details.',edit:'Edit the reference jewellery according to the brief; preserve unspecified details.',views:'Use the reference photo as the exact product, not design inspiration. Generate a single white-background contact sheet of three separate complete views of the same piece: front, side (90 degrees), rear (180 degrees). Keep silhouette, geometry, proportions, metal colour, finish, engravings, settings and gemstone count, size and placement consistent. If the reference has no stones, do not add stones or settings. Preserve existing stones. Do not invent features or measurements. Only change details explicitly requested by the customer.',wear:'Show this jewellery being worn by an adult model, tightly cropped without face, preserving the product design and plausible scale.',retouch:'Clean the background to pure white, centre the jewellery, preserve its exact visible design and proportions, improve product photography without adding details.',relief:'Create a detailed relief jewellery concept illustration with fine sculpted surface texture. This is a 2D design preview.'};
export async function onRequestPost(ctx){let denied=await authorize(ctx);if(denied)return denied;const {env,request}=ctx;try{const d=await body(request);if(!Object.hasOwn(instructions,d.tool))return json({error:'Unsupported tool.'},400);let prompt=typeof d.prompt==='string'?d.prompt.slice(0,2400):'';const needsImage=!['design','relief'].includes(d.tool);if(needsImage&&!validImage(d.image))return json({error:'A valid reference image is required.'},400);if(['design','relief','edit'].includes(d.tool)&&!prompt.trim())return json({error:'Design description is required.'},400);let settings=['category','metal','stone','style','zodiac'].map(k=>`${k}: ${String(d.settings?.[k]||'Any').slice(0,80)}`).join('; ');let text=d.tool==='views'?`${instructions.views} Customer request: ${prompt.trim()||'None; change camera angle only'}. Explicit selections (ignore Any): ${settings}. Accurate product photography, consistent views, no text, no brand logos, no watermark. Output one image containing three views.`:`${instructions[d.tool]} Design brief: ${prompt}. Preferences (ignore Any): ${settings}. Professional jewellery design, accurate visual detail, no brand logos, no watermark. Output one image.`;const engine=d.engine||'cloudflare';
if(engine==='cloudflare'){
 if(needsImage&&d.tool!=='sketch')return json({error:'Free FLUX supports text-to-image only. Use Free Tools V2 for local image processing.'},400);
 if(typeof env.AI?.run!=='function')return json({error:'Cloudflare AI binding missing. Add AI to Production and redeploy.'},503);
 try{
  // V4.1.3: FLUX.2 image-conditioned sketch rendering, separate from the text pipeline.
  if(d.tool==='sketch'){
   const m=d.image.match(/^data:image\/png;base64,([A-Za-z0-9+/=]+)$/);if(!m)return json({error:'SKETCH_REFERENCE_INVALID'},400);
   let bytes;try{bytes=Uint8Array.from(atob(m[1]),c=>c.charCodeAt(0));}catch{return json({error:'SKETCH_REFERENCE_INVALID'},400);}
   if(bytes.length<33||bytes.length>3*1024*1024||bytes[0]!==137||bytes[1]!==80||bytes[2]!==78||bytes[3]!==71||bytes[4]!==13||bytes[5]!==10||bytes[6]!==26||bytes[7]!==10||String.fromCharCode(...bytes.slice(12,16))!=='IHDR')return json({error:'SKETCH_REFERENCE_INVALID'},400);
   const view=new DataView(bytes.buffer);const w=view.getUint32(16),h=view.getUint32(20);if(w<1||h<1||w>=512||h>=512)return json({error:'SKETCH_REFERENCE_INVALID'},400);
   const sketchPrompt=('Use input image 0 as the actual jewellery design reference. Convert the hand-drawn sketch into one photorealistic luxury jewellery product render. Preserve the overall silhouette, proportions, openings, decorative motifs, band geometry, and gemstone count and placement wherever visible. Preserve stones shown in the sketch unless explicitly requested otherwise; do not add new stones by default. If preferences specify no stone, render without gemstones. Apply requested materials and colours without unrelated redesign. Remove paper, construction lines and handwriting. Show the single complete jewellery piece centred on a pure white studio background, realistic polished metal, fine details, soft controlled lighting, no text, no logo, no watermark. '+text).slice(0,4000);
   const form=new FormData();form.append('prompt',sketchPrompt);form.append('width','1024');form.append('height','1024');form.append('input_image_0',new Blob([bytes],{type:'image/png'}),'sketch.png');
   const serialized=new Response(form);
   const out=await env.AI.run('@cf/black-forest-labs/flux-2-klein-4b',{multipart:{body:serialized.body,contentType:serialized.headers.get('content-type')}});
   const img=out?.image;if(typeof img!=='string'||img.length<24||!(/^[A-Za-z0-9+/=]+$/.test(img)))throw Error('Invalid FLUX.2 image result');
   const mime=img.startsWith('iVBORw0KGgo')?'image/png':img.startsWith('/9j/')?'image/jpeg':img.startsWith('UklGR')?'image/webp':null;if(!mime)throw Error('Unknown FLUX.2 image format');
   return json({image:'data:'+mime+';base64,'+img,engine:'cloudflare',model:'flux-2-klein-4b',check:'not_required',attempts:1});
  }
  const lang=['zh','en','ru'].includes(d.lang)?d.lang:'zh';
  const plan=await buildSmartPlan(env.AI,prompt,d.settings||{},lang,d.tool);
  for(let attempt=1;attempt<=2;attempt++){
   const fluxPrompt=attempt===1?plan.prompt:('A solid all-metal sculpture, unbroken metal surfaces, no separate inset objects, no stone settings. '+plan.prompt).slice(0,2048);
   const out=await env.AI.run('@cf/black-forest-labs/flux-1-schnell',{prompt:fluxPrompt,steps:8});
   if(typeof out?.image!=='string'||!out.image||!(/^[A-Za-z0-9+/=]+$/.test(out.image)))throw Error('Cloudflare AI returned no valid image.');
   if(plan.noStone){
    let check;try{check=await inspectStoneFree(env.AI,out.image)}catch(e){console.error('Vision check failed',String(e?.message||e));check='UNSURE';}
    if(check==='UNSURE')return json({image:'data:image/jpeg;base64,'+out.image,engine:'cloudflare',plan,check:'manual_required',attempts:attempt});
    if(check==='FAIL'){if(attempt===1)continue;return json({error:'STONE_CHECK_REJECTED'},422);}
   }
   return json({image:'data:image/jpeg;base64,'+out.image,engine:'cloudflare',plan,check:plan.noStone?'passed':'not_required',attempts:attempt});
  }
 }catch(e){console.error('Cloudflare AI generation failed',String(e?.message||e));return json({error:'FREE_GENERATION_FAILED'},502);}
}
if(engine!=='openai')return json({error:'Unsupported AI engine.'},400);
if(env.ENABLE_PAID_AI!=='true'||!env.OPENAI_API_KEY)return json({error:'Paid OpenAI mode is disabled. Use Cloudflare free mode.'},403);
let model=env.OPENAI_IMAGE_MODEL||'gpt-image-2.5-flare';let data={model,prompt:text,n:1,size:'1024x1024',quality:'medium',output_format:'png'};let url='https://api.openai.com/v1/images/'+(needsImage?'edits':'generations');let result;if(needsImage){const f=new FormData();Object.entries(data).forEach(([k,v])=>f.append(k,String(v)));const [,mime,b64]=d.image.match(/^data:(image\/(?:png|jpeg|webp));base64,(.+)$/);const bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));f.append('image',new Blob([bytes],{type:mime}),'reference.'+mime.split('/')[1]);result=await provider(url,env.OPENAI_API_KEY,{method:'POST',body:f})}else result=await provider(url,env.OPENAI_API_KEY,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});let img=result.data?.[0]?.b64_json;if(!img)throw Error('No image received from provider.');return json({image:'data:image/png;base64,'+img,engine:'openai'});}catch(e){return json({error:e.message||'Image generation failed.'},502)}}
