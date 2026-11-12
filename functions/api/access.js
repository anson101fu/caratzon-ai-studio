import {authorize,json} from './_shared.js';
export async function onRequestPost(ctx){
 const denied=await authorize(ctx); if(denied)return denied;
 const free=typeof ctx.env.AI?.run==='function';
 const paid=ctx.env.ENABLE_PAID_AI==='true'&&!!ctx.env.OPENAI_API_KEY;
 return json({image:free||paid,free,paid,model:!!ctx.env.MESHY_API_KEY});
}
