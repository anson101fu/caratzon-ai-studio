"""GLB -> portable OBJ + MTL ZIP, stdlib only, for Caratzon parametric bracelet meshes.
Models are concept meshes, not manufacturing CAD. No secrets are included in exports.
"""
import json
import struct
import zipfile
from pathlib import Path

NAMES = ('metal_settings', 'diamonds', 'clasp_accent')
COLORS = ('metal', 'diamond', 'accent')

def _glb(path):
    data=Path(path).read_bytes()
    if len(data)<20 or data[:4]!=b'glTF' or struct.unpack_from('<I',data,4)[0]!=2:
        raise ValueError('Not a GLB 2.0 file')
    off=12; j=None; binary=None
    while off+8<=len(data):
        n,kind=struct.unpack_from('<I4s',data,off);off+=8
        if off+n>len(data):raise ValueError('GLB chunk invalid')
        val=data[off:off+n];off+=n
        if kind==b'JSON':j=json.loads(val)
        elif kind==b'BIN\0':binary=val
    if not j or binary is None:raise ValueError('Missing GLB data')
    return j,binary

def _accessor(g,b,idx):
    a=g['accessors'][idx];v=g['bufferViews'][a['bufferView']]
    if a.get('byteOffset',0)<0:raise ValueError('Bad accessor offset')
    stride={5126:4,5125:4,5123:2}[a['componentType']]
    cols={'SCALAR':1,'VEC3':3}[a['type']]
    format_char={5126:'f',5125:'I',5123:'H'}[a['componentType']]
    fmt='<'+format_char*cols
    step=v.get('byteStride',stride*cols)
    offset=v.get('byteOffset',0)+a.get('byteOffset',0)
    if offset+step*(a['count']-1)+stride*cols>len(b):raise ValueError('Accessor out of bounds')
    return [struct.unpack_from(fmt,b,offset+i*step) for i in range(a['count'])]

def export_package(glb_path,zip_path):
    g,b=_glb(glb_path)
    zip_path=Path(zip_path);zip_path.parent.mkdir(parents=True,exist_ok=True)
    name='caratzon_tennis_bracelet'
    metal=g.get('materials',[{}])[0].get('pbrMetallicRoughness',{}).get('baseColorFactor',[.8,.8,.8,1])[:3]
    mtl='''# Caratzon tennis bracelet V1 | concept mesh, not manufacturing CAD
newmtl metal
Ka 0.18 0.18 0.18
Kd %.5f %.5f %.5f
Ks 0.75 0.75 0.75
Ns 450
illum 2

newmtl diamond
Ka 0.16 0.16 0.16
Kd 0.88 0.93 0.98
Ks 0.95 0.95 0.95
Ns 850
illum 2

newmtl accent
Ka 0.12 0.12 0.12
Kd 0.55 0.57 0.60
Ks 0.70 0.70 0.70
Ns 400
illum 2
'''%tuple(metal)
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        with archive.open(name+'.obj','w',force_zip64=True) as out:
            def write(s):out.write(s.encode('ascii'))
            write('# CARATZON parametric tennis bracelet, concept only\n')
            write('mtllib '+name+'.mtl\n')
            vertex_base=0;normal_base=0
            for i,p in enumerate(g['meshes'][0]['primitives']):
                pos=_accessor(g,b,p['attributes']['POSITION'])
                normals=_accessor(g,b,p['attributes']['NORMAL'])
                faces=_accessor(g,b,p['indices'])
                if len(faces)%3:raise ValueError('Expected triangles')
                write('o '+NAMES[min(i,len(NAMES)-1)]+'\n')
                write('usemtl '+COLORS[min(i,len(COLORS)-1)]+'\n')
                for x,y,z in pos:write(f'v {x:.6f} {y:.6f} {z:.6f}\n')
                for x,y,z in normals:write(f'vn {x:.6f} {y:.6f} {z:.6f}\n')
                for k in range(0,len(faces),3):
                    ids=[int(faces[k+a][0]) for a in range(3)]
                    write('f '+' '.join(f'{vertex_base+n+1}//{normal_base+n+1}' for n in ids)+'\n')
                vertex_base+=len(pos);normal_base+=len(normals)
        archive.writestr(name+'.mtl',mtl)
        archive.writestr('README.txt','CARATZON tennis bracelet V1\nOBJ uses units of millimetres. Import OBJ and MTL from the same folder.\nMaterial appearance depends on the 3D application; OBJ/MTL does not encode true gems or physically accurate refraction.\nConceptual geometry only, NOT suitable for manufacturing without CAD review.\n')
    return zip_path

if __name__=='__main__':
    import tennis_geometry
    path=Path(__file__).resolve().parent/'sample.glb'
    tennis_geometry.generate({'length_mm':170,'stone_mm':3,'shape':'round','metal':'silver','clasp':'box'},path)
    print(export_package(path,path.with_suffix('.zip')))
