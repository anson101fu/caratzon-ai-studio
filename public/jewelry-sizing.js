/* Caratzon jewelry size picker v1.0 - design specification, not CAD calibration. */
(function(){
'use strict';
const $=id=>document.getElementById(id);
const HK={5:13.8,6:14.2,7:14.5,8:14.8,9:15.2,10:15.5,11:15.9,12:16.2,13:16.5,14:16.9,15:17.2,16:17.5,17:17.8,18:18.2,19:18.5,20:18.9,21:19.2,22:19.5,23:19.8,24:20.2,25:20.5};
const T={
 zh:{title:'尺寸規格 · 按類別選擇',note:'尺寸為設計目標；AI 效果圖及自動重建 GLB 並非精確 CAD，生產前請實測核對。',ring:'戒指圈號系統',hk:'香港圈號（參考）',diam:'內圈直徑 (mm)',ringWidth:'戒圈寬度 (mm)',earH:'耳環高度 (mm)',earW:'耳環寬度 (mm)',earPost:'耳針直徑 (mm)',pendH:'吊墜高度 (mm)',pendW:'吊墜寬度 (mm)',neckL:'頸鏈長度 (cm)',chainW:'鏈條闊度 (mm)',wrist:'手圍 (cm)',braceletL:'手鏈總長度 (cm)',braceletW:'手鏈闊度 (mm)',broochH:'胸針高度 (mm)',broochW:'胸針寬度 (mm)',custom:'自訂內徑',hint:'香港圈號對照為近似值；以內徑 mm 為準。',model:'目前所選尺寸：',modelCaution:'注意：尺寸只用於設計要求，現有 3D 網格沒有自動校準到此尺寸。'},
 en:{title:'Dimensions · by jewellery type',note:'Design targets only. Generated images and reconstructed GLB models are not precision CAD; verify measurements before production.',ring:'Ring sizing standard',hk:'Hong Kong size (reference)',diam:'Inner diameter (mm)',ringWidth:'Band width (mm)',earH:'Earring height (mm)',earW:'Earring width (mm)',earPost:'Post diameter (mm)',pendH:'Pendant height (mm)',pendW:'Pendant width (mm)',neckL:'Necklace length (cm)',chainW:'Chain width (mm)',wrist:'Wrist circumference (cm)',braceletL:'Bracelet length (cm)',braceletW:'Bracelet width (mm)',broochH:'Brooch height (mm)',broochW:'Brooch width (mm)',custom:'Custom inner diameter',hint:'HK conversions are approximate; verify inner diameter in mm.',model:'Selected design dimensions: ',modelCaution:'Dimensions are a design brief; the existing 3D mesh is not automatically calibrated.'},
 ru:{title:'Размеры · по типу изделия',note:'Заданные размеры ориентировочные. Изображения и GLB не являются точными CAD-моделями.',ring:'Система размеров кольца',hk:'Гонконгский размер',diam:'Внутренний диаметр (мм)',ringWidth:'Ширина кольца (мм)',earH:'Высота серьги (мм)',earW:'Ширина серьги (мм)',earPost:'Диаметр штифта (мм)',pendH:'Высота подвески (мм)',pendW:'Ширина подвески (мм)',neckL:'Длина колье (см)',chainW:'Ширина цепочки (мм)',wrist:'Обхват запястья (см)',braceletL:'Длина браслета (см)',braceletW:'Ширина браслета (мм)',broochH:'Высота броши (мм)',broochW:'Ширина броши (мм)',custom:'Свой диаметр',hint:'Размер HK приблизительный; проверяйте диаметр в мм.',model:'Заданные размеры: ',modelCaution:'Размеры не калибруют GLB автоматически.'}
};
const definitions={
 ring:[['ringSize','hk',null],['innerDiameter','diam',[12,25,.1,16.5]],['bandWidth','ringWidth',[1,15,.1,2.5]]],
 earrings:[['height','earH',[2,120,.5,20]],['width','earW',[2,80,.5,12]],['post','earPost',[.6,1.5,.05,.8]]],
 pendant:[['height','pendH',[5,120,.5,22]],['width','pendW',[3,100,.5,16]]],
 necklace:[['length','neckL',[30,100,1,45]],['width','chainW',[.5,20,.1,1.5]]],
 bracelet:[['wrist','wrist',[12,24,.5,16]],['length','braceletL',[14,28,.5,18]],['width','braceletW',[1,25,.5,4]]],
 brooch:[['height','broochH',[5,120,.5,30]],['width','broochW',[5,120,.5,25]]]
};
let values={};let category='auto';
const lang=()=>T[$('lang')?.value]||T.zh;
const getCategory=()=> $('category')?.value||'auto';
function label(id,title){const e=document.createElement('label');e.htmlFor=id;e.textContent=title;e.style.cssText='display:block;margin-bottom:6px;font-size:13px';return e;}
function field(id,title,range){const d=document.createElement('div');d.style.minWidth='125px';d.append(label(id,title));let input;if(id==='ringSize'){
 input=document.createElement('select');input.id=id;input.style.width='100%';for(let n=5;n<=25;n++){const opt=new Option(`HK ${n} · Ø ${HK[n].toFixed(1)} mm`,String(n));input.add(opt);}input.value=String(values.ring?.ringSize||13);
 input.onchange=()=>{(values.ring??={}).ringSize=Number(input.value);const diameter=$('innerDiameter');if(diameter){diameter.value=HK[Number(input.value)];values.ring.innerDiameter=Number(diameter.value);}updateDisplay();};
 }else{
 input=document.createElement('input');input.type='number';input.id=id;input.min=range[0];input.max=range[1];input.step=range[2];input.value=values[category]?.[id]??range[3];input.style.width='100%';input.onchange=()=>{let n=Number(input.value);if(!Number.isFinite(n)||n<range[0]||n>range[1]){input.value=values[category]?.[id]??range[3];return;} (values[category]??={})[id]=n;updateDisplay();};
 }d.append(input);return d;}
let panel=null,tip=null;
function render(){if(!panel)return;const tx=lang();category=getCategory();panel.hidden=!definitions[category];panel.replaceChildren();if(!definitions[category]){updateDisplay();return;}
const heading=document.createElement('strong');heading.textContent=tx.title;heading.style.display='block';heading.style.marginBottom='10px';panel.append(heading);
const grid=document.createElement('div');grid.style.cssText='display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:12px';for(const [id,key,range] of definitions[category])grid.append(field(id,tx[key],range));panel.append(grid);
const note=document.createElement('p');note.style.cssText='font-size:12px;line-height:1.5;opacity:.8;margin:10px 0 0';note.textContent=(category==='ring'?tx.hint+' ':'')+tx.note;panel.append(note);updateDisplay();}
function brief(){const cat=getCategory();if(!definitions[cat])return '';
let v={};for(const [id,key,range] of definitions[cat]){const e=$(id);if(!e)continue;let n=Number(e.value);if(Number.isFinite(n)){v[id]=n;}}
if(!Object.keys(v).length)return '';
values[cat]=v;
switch(cat){case 'ring':return `Ring HK size ${v.ringSize} (reference), actual INNER diameter ${v.innerDiameter} mm, band width ${v.bandWidth} mm. Inside diameter is a target to be verified with CAD measurement.`;
case 'earrings':return `Earring overall height ${v.height} mm, width ${v.width} mm; post diameter ${v.post} mm.`;
case 'pendant':return `Pendant body overall height ${v.height} mm, width ${v.width} mm (excluding chain).`;
case 'necklace':return `Necklace chain length ${v.length} cm, chain width ${v.width} mm.`;
case 'bracelet':return `Wrist circumference ${v.wrist} cm, bracelet finished total length ${v.length} cm, width ${v.width} mm.`;
case 'brooch':return `Brooch overall height ${v.height} mm, width ${v.width} mm.`;
}return '';}
function updateDisplay(){const text=brief();if(tip){tip.hidden=!text;tip.textContent=lang().model+text+' '+lang().modelCaution;}}
function init(){const p=$('parameters'),sel=$('category');if(!p||!sel)return;
panel=document.createElement('section');panel.id='czJewelrySizes';panel.className='field';panel.style.cssText='margin-top:16px;padding:14px;border:1px solid #665639;border-radius:10px';p.append(panel);
const model=$('modelOptions');if(model){tip=document.createElement('p');tip.id='czModelSizeNotice';tip.className='note';tip.style.marginTop='12px';model.append(tip);}
sel.addEventListener('change',render);$('lang')?.addEventListener('change',()=>setTimeout(render,0));
new MutationObserver(()=>{if(category!==getCategory())render();else updateDisplay();}).observe(sel,{attributes:true,attributeFilter:['value']});
render();
}
window.CaratzonJewelrySizing={getBrief:brief,getCategory,refresh:render,getValues:()=>JSON.parse(JSON.stringify(values))};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
