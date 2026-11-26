/* V4.4.2: conservative GLB primitive separation; no geometric guessing. */
(function(root){
'use strict';
const stone=/^(?:gemstone|gem|diamond|ruby|sapphire|emerald|pearl|宝石|钻石|珍珠)(?:[ _.-]*\d+)?$/i;
const metal=/^(?:metal|gold|silver|platinum|mounting|setting|prong|basket|gallery|shank|金属|黄金|白银|镶爪)(?:[ _.-]*\d+)?$/i;
function fail(msg){throw Error(msg);}
function split(bytes){
 const v=new DataView(bytes);if(v.byteLength<20||v.getUint32(0,true)!==0x46546c67||v.getUint32(4,true)!==2||v.getUint32(8,true)!==v.byteLength)fail('Invalid GLB');
 const n=v.getUint32(12,true);if(n%4||20+n>v.byteLength||v.getUint32(16,true)!==0x4e4f534a)fail('Invalid JSON chunk');
 const g=JSON.parse(new TextDecoder().decode(new Uint8Array(bytes,20,n)));
 if(g.skins?.length||g.animations?.length||g.extensionsRequired?.length||g.extensionsUsed?.length||g.buffers?.length!==1||g.buffers[0].uri)fail('Unsupported GLB structure');
 const meshes=g.meshes||[], materials=g.materials||[], nodes=g.nodes||[];
 let removed=0,kept=0;const cut=new Set(),stay=new Set();
 for(let i=0;i<meshes.length;i++){
  const m=meshes[i], ps=[]; if(!Array.isArray(m.primitives)||!m.primitives.length)fail('Invalid mesh');
  const names=nodes.filter(x=>x.mesh===i).map(x=>x.name||'').filter(Boolean);
  for(const p of m.primitives){
   if(p.extensions||p.targets||(p.mode!==undefined&&p.mode!==4)||!Number.isInteger(p.attributes?.POSITION))fail('Unsupported primitive');
   const labels=[m.name,...names,materials[p.material]?.name].filter(Boolean).map(s=>String(s).trim());
   const isStone=labels.some(s=>stone.test(s)),isMetal=labels.some(s=>metal.test(s));
   if(isStone&&isMetal)fail('Conflicting gemstone/metal labels');
   if(!isStone&&!isMetal)fail('融合或未标记网格，无法安全自动分石 / Fused or unlabelled mesh; CAD separation required');
   if(isStone){removed++;cut.add(p.attributes.POSITION);}else{kept++;stay.add(p.attributes.POSITION);ps.push(p);}
  }
  m.primitives=ps;
 }
 if(!removed||!kept)fail('No independently labelled gemstone and metal geometry');
 for(const a of cut)if(stay.has(a))fail('Shared position buffer; separation blocked');
 // Keep all original metal accessors, vertices, materials, textures and transforms unchanged.
 const map=new Map(), out=[];meshes.forEach((m,i)=>{if(m.primitives.length){map.set(i,out.length);out.push(m);}});
 for(const node of nodes)if(node.mesh!==undefined){if(map.has(node.mesh))node.mesh=map.get(node.mesh);else delete node.mesh;}
 g.meshes=out;
 const json=new TextEncoder().encode(JSON.stringify(g)), pad=(4-json.length%4)%4, tail=new Uint8Array(bytes,20+n), result=new Uint8Array(20+json.length+pad+tail.length), w=new DataView(result.buffer);
 w.setUint32(0,0x46546c67,true);w.setUint32(4,2,true);w.setUint32(8,result.length,true);w.setUint32(12,json.length+pad,true);w.setUint32(16,0x4e4f534a,true);result.set(json,20);result.fill(32,20+json.length,20+json.length+pad);result.set(tail,20+json.length+pad);
 return {bytes:result.buffer,removed,kept};
}
root.CZMeshLock={split};
})(typeof window==='undefined'?globalThis:window);
