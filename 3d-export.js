/* Caratzon.com global static GLB to OBJ + MTL exporter, v2.0.
 * Offline, no CDN and no server uploads. OBJ coordinates are millimetres.
 * Supports standard uncompressed static glTF 2.0 triangle meshes / node transforms.
 * Explicitly rejects unsupported Draco/Meshopt rather than silently corrupting output.
 */
(function (root) {
  'use strict';
  const encoder = new TextEncoder();
  const MAX_TRIANGLES = 1200000;
  const MAX_SOURCE = 80 * 1024 * 1024;
  const outName = s => (String(s || 'caratzon_model').replace(/[^\w.-]+/g, '_').slice(0, 80) || 'caratzon_model');
  function readGLB(buf) {
    if (!(buf instanceof ArrayBuffer)) throw Error('Expected GLB ArrayBuffer');
    if (buf.byteLength > MAX_SOURCE) throw Error('GLB too large for browser export (80 MB limit)');
    const v = new DataView(buf);
    if (v.byteLength < 20 || v.getUint32(0, true) !== 0x46546c67 || v.getUint32(4, true) !== 2 || v.getUint32(8, true) !== v.byteLength)
      throw Error('Invalid glTF 2.0 GLB');
    let pos = 12, json = null, bin = null;
    while (pos + 8 <= buf.byteLength) {
      const length = v.getUint32(pos, true), kind = v.getUint32(pos + 4, true); pos += 8;
      if (length > buf.byteLength - pos) throw Error('Malformed GLB chunk');
      if (kind === 0x4E4F534A) json = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, pos, length)));
      if (kind === 0x004E4942) bin = { start: pos, length };
      pos += length;
    }
    if (!json || !bin) throw Error('GLB needs JSON and BIN chunks');
    if ((json.extensionsRequired || []).some(e => /meshopt|draco/i.test(e))) throw Error('Compressed GLB (Draco/Meshopt) is not supported. Export an uncompressed GLB first.');
    return { json, bin, view: v };
  }
  const componentBytes = {5120:1,5121:1,5122:2,5123:2,5125:4,5126:4};
  function accessor(glb, id, expected) {
    const g = glb.json, a = g.accessors?.[id], bv = g.bufferViews?.[a?.bufferView];
    if (!a || !bv || a.sparse || a.bufferView === undefined || bv.buffer !== 0 || bv.extensions) throw Error('Unsupported sparse/external/compressed accessor');
    if (expected && a.type !== expected) throw Error('Unexpected accessor type');
    const fields = {SCALAR:1,VEC2:2,VEC3:3,VEC4:4}[a.type];
    const bytes = componentBytes[a.componentType];
    if (!fields || !bytes) throw Error('Unsupported vertex component type');
    const stride = bv.byteStride || (fields * bytes), offset = glb.bin.start + (bv.byteOffset || 0) + (a.byteOffset || 0);
    const end = glb.bin.start + Math.min(glb.bin.length, (bv.byteOffset || 0) + bv.byteLength);
    if (stride < fields * bytes || offset < glb.bin.start || (a.count && offset + (a.count - 1) * stride + fields * bytes > end)) throw Error('Accessor is outside GLB buffer');
    const dv = glb.view;
    function val(i, j) {
      const p = offset + i * stride + j * bytes;
      let x;
      switch (a.componentType) {
        case 5120: x = dv.getInt8(p); break;
        case 5121: x = dv.getUint8(p); break;
        case 5122: x = dv.getInt16(p, true); break;
        case 5123: x = dv.getUint16(p, true); break;
        case 5125: x = dv.getUint32(p, true); break;
        case 5126: x = dv.getFloat32(p, true); break;
      }
      return x;
    }
    return { count:a.count, read:val };
  }
  const ident = () => [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1];
  function mul(a,b) { const c = new Array(16).fill(0); for(let j=0;j<4;j++)for(let i=0;i<4;i++)for(let k=0;k<4;k++)c[j*4+i]+=a[k*4+i]*b[j*4+k];return c; }
  function localMatrix(n) {
    if (n.matrix) return n.matrix;
    const [x,y,z,w] = n.rotation || [0,0,0,1], [sx,sy,sz] = n.scale || [1,1,1], [tx,ty,tz] = n.translation || [0,0,0];
    return [(1-2*y*y-2*z*z)*sx,(2*x*y+2*z*w)*sx,(2*x*z-2*y*w)*sx,0,
      (2*x*y-2*z*w)*sy,(1-2*x*x-2*z*z)*sy,(2*y*z+2*x*w)*sy,0,
      (2*x*z+2*y*w)*sz,(2*y*z-2*x*w)*sz,(1-2*x*x-2*y*y)*sz,0,tx,ty,tz,1];
  }
  const fmt = n => {if (!Number.isFinite(n)) throw Error('Nonfinite mesh vertex');return Number(n.toFixed(5)).toString();};
  function materialName(i) { return `material_${i}`; }
  function convert(buffer, name='caratzon_model') {
    const b = readGLB(buffer), g = b.json, base = outName(name);
    const obj = [`# Caratzon.com OBJ export\n# Coordinates: millimetres (mm)\nmtllib ${base}.mtl\n`];
    const materials = new Map();
    let vertexOffset=1, totalFaces=0, parts=0;
    function walk(id, parent, depth) {
      if (depth>150) throw Error('Node hierarchy too deep');
      const n=g.nodes?.[id]; if(!n)throw Error('Invalid scene node');
      const mat=mul(parent,localMatrix(n));
      if(n.mesh!==undefined) {
        const m=g.meshes?.[n.mesh]; if(!m)throw Error('Invalid glTF mesh');
        for (const pr of m.primitives || []) {
          if(pr.extensions || (pr.mode!==undefined && pr.mode!==4)) throw Error('Compressed/nontriangle primitive not supported');
          const p=accessor(b,pr.attributes?.POSITION,'VEC3');
          const inds=pr.indices===undefined ? null : accessor(b,pr.indices,'SCALAR');
          const count=inds ? inds.count : p.count;
          if(count%3) throw Error('Triangle index count is invalid');
          totalFaces += count/3; if(totalFaces>MAX_TRIANGLES)throw Error('Too many triangles for browser OBJ export (1.2 million maximum)');
          const mi=pr.material ?? -1;
          if(!materials.has(mi)) {
            const mtl=g.materials?.[mi] || {}, rgb=mtl.pbrMetallicRoughness?.baseColorFactor || [0.8,0.8,0.8,1];
            materials.set(mi,{rgb,metallic:mtl.pbrMetallicRoughness?.metallicFactor||0});
          }
          obj.push(`\no ${base}_part_${++parts}\nusemtl ${materialName(mi)}\n`);
          for(let i=0;i<p.count;i++) {
            const x=p.read(i,0),y=p.read(i,1),z=p.read(i,2);
            // glTF geometry coordinates in metres -> OBJ convention in millimetres.
            obj.push(`v ${fmt(1000*(mat[0]*x+mat[4]*y+mat[8]*z+mat[12]))} ${fmt(1000*(mat[1]*x+mat[5]*y+mat[9]*z+mat[13]))} ${fmt(1000*(mat[2]*x+mat[6]*y+mat[10]*z+mat[14]))}\n`);
          }
          const flip=(mat[0]*(mat[5]*mat[10]-mat[9]*mat[6])-mat[4]*(mat[1]*mat[10]-mat[9]*mat[2])+mat[8]*(mat[1]*mat[6]-mat[5]*mat[2]))<0;
          for(let i=0;i<count;i+=3) {
            const a=inds?inds.read(i,0):i, c=inds?inds.read(i+1,0):i+1, d=inds?inds.read(i+2,0):i+2;
            if(Math.max(a,c,d)>=p.count)throw Error('Index outside mesh vertex range');
            obj.push(`f ${a+vertexOffset} ${flip?d+vertexOffset:c+vertexOffset} ${flip?c+vertexOffset:d+vertexOffset}\n`);
          }
          vertexOffset+=p.count;
        }
      }
      for(const child of n.children || []) walk(child,mat,depth+1);
    }
    const scene=g.scenes?.[g.scene??0];
    if(!scene)throw Error('GLB has no scene');
    for(const id of scene.nodes||[])walk(id,ident(),0);
    if(!parts)throw Error('GLB has no triangle meshes');
    const mtl=[`# Caratzon.com materials\n# Match with ${base}.obj\n`];
    for(const [id,m] of materials) {
      const [r,gg,bl,a=1]=m.rgb;mtl.push(`newmtl ${materialName(id)}\nKa 0.15 0.15 0.15\nKd ${fmt(r)} ${fmt(gg)} ${fmt(bl)}\nKs ${m.metallic>0.5?'0.7 0.7 0.7':'0.15 0.15 0.15'}\nNs 120\nd ${fmt(a)}\nillum 2\n\n`);
    }
    return {name:base,files:[{name:base+'.obj',bytes:encoder.encode(obj.join(''))},{name:base+'.mtl',bytes:encoder.encode(mtl.join(''))}],faces:totalFaces,parts};
  }
  // ZIP container with uncompressed entries (STORE); Blender-compatible OBJ and MTL.
  const crcTable=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=(c&1)?(0xEDB88320^(c>>>1)):(c>>>1);crcTable[n]=c>>>0;}
  function crc32(bytes){let c=0xFFFFFFFF;for(const x of bytes)c=crcTable[(c^x)&255]^(c>>>8);return (c^0xFFFFFFFF)>>>0;}
  function zip(files){const locals=[],central=[];let offset=0;for(const f of files){const fn=encoder.encode(f.name),data=f.bytes,crc=crc32(data);if(data.length>=0xFFFFFFFF)throw Error('File too large');const lh=new Uint8Array(30+fn.length);let v=new DataView(lh.buffer);v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint16(6,0x0800,true);v.setUint32(14,crc,true);v.setUint32(18,data.length,true);v.setUint32(22,data.length,true);v.setUint16(26,fn.length,true);lh.set(fn,30);locals.push(lh,data);const ch=new Uint8Array(46+fn.length);v=new DataView(ch.buffer);v.setUint32(0,0x02014b50,true);v.setUint16(4,20,true);v.setUint16(6,20,true);v.setUint16(8,0x0800,true);v.setUint32(16,crc,true);v.setUint32(20,data.length,true);v.setUint32(24,data.length,true);v.setUint16(28,fn.length,true);v.setUint32(42,offset,true);ch.set(fn,46);central.push(ch);offset+=lh.length+data.length;}const csize=central.reduce((n,c)=>n+c.length,0),end=new Uint8Array(22),dv=new DataView(end.buffer);dv.setUint32(0,0x06054b50,true);dv.setUint16(8,files.length,true);dv.setUint16(10,files.length,true);dv.setUint32(12,csize,true);dv.setUint32(16,offset,true);return new Blob([...locals,...central,end],{type:'application/zip'});}
  function download(blob,filename){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);}
  async function exportBlob(blob,name){if(!blob||blob.size>MAX_SOURCE)throw Error('GLB missing or larger than 80 MB');const data=convert(await blob.arrayBuffer(),name);download(zip(data.files),data.name+'_OBJ_MTL.zip');return data;}
  const labels={zh:['下载 GLB','下载 OBJ + MTL','正在转换 OBJ…','当前没有 GLB 模型','导出失败：'],en:['Download GLB','Download OBJ + MTL','Converting OBJ…','No GLB model available','Export failed: '],ru:['Скачать GLB','Скачать OBJ + MTL','Конвертация OBJ…','GLB отсутствует','Ошибка экспорта: ']};
  const L=()=>labels[document.querySelector('#lang,#freeLang')?.value]||labels.zh;
  function attachStudio(){
    const parent=document.querySelector('.resultactions'),model=document.querySelector('#modelResult'),viewer=document.querySelector('#viewer');
    if(!parent||!model||!viewer||document.querySelector('#czGlobalObj'))return;
    const glb=document.createElement('button'),obj=document.createElement('button');glb.type=obj.type='button';glb.className=obj.className='outline';glb.id='czGlobalGlb';obj.id='czGlobalObj';
    const status=document.createElement('span');status.id='czExportStatus';status.setAttribute('role','status');status.style.cssText='flex-basis:100%;font-size:12px;color:#e6ca90';
    const dl=document.querySelector('#download');if(dl)dl.after(glb,obj);else parent.append(glb,obj);parent.append(status);
    const src=()=>viewer.getAttribute('src');
    function refresh(){const show=!model.hidden&&!!src();glb.hidden=obj.hidden=!show;glb.textContent=L()[0];obj.textContent=L()[1];}
    async function getBlob(){const url=src();if(!url)throw Error(L()[3]);const response=await fetch(url);if(!response.ok)throw Error('GLB could not be loaded ('+response.status+')');const b=await response.blob();if(b.size>MAX_SOURCE)throw Error('GLB too large');return b;}
    glb.onclick=async()=>{glb.disabled=true;status.textContent='';try{download(await getBlob(),'caratzon_model.glb');}catch(e){status.textContent=L()[4]+e.message;}finally{glb.disabled=false;}};
    obj.onclick=async()=>{obj.disabled=true;status.textContent=L()[2];try{const r=await exportBlob(await getBlob(),'caratzon_model');status.textContent=`OBJ + MTL · ${r.parts} parts · ${r.faces.toLocaleString()} triangles`;}catch(e){status.textContent=L()[4]+e.message;}finally{obj.disabled=false;}};
    new MutationObserver(refresh).observe(model,{attributes:true,attributeFilter:['hidden','style','class']});new MutationObserver(refresh).observe(viewer,{attributes:true,attributeFilter:['src']});
    document.querySelector('#lang')?.addEventListener('change',refresh);refresh();
  }
  root.Caratzon3DExport={convert,zip,download,exportBlob,attachStudio};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',attachStudio,{once:true});else attachStudio();
})(window);
