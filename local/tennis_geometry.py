"""CARATZON Tennis Bracelet V1: dependency-free parametric GLB concept generator.
No image diffusion or ComfyUI GPU is used. Do not treat as casting-grade CAD.
"""
import json, math, struct, bisect
from pathlib import Path

PI=math.pi

def add(a,b): return (a[0]+b[0],a[1]+b[1],a[2]+b[2])
def sub(a,b): return (a[0]-b[0],a[1]-b[1],a[2]-b[2])
def scale(a,k): return (a[0]*k,a[1]*k,a[2]*k)
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm(a):
    l=math.sqrt(sum(v*v for v in a))
    return scale(a,1/l) if l>1e-9 else (0.,1.,0.)

class Mesh:
    def __init__(self): self.pos=[];self.norm=[];self.indices=[]
    def face(self,p,q,r):
        n=norm(cross(sub(q,p),sub(r,p)))
        k=len(self.pos)
        self.pos.extend([p,q,r]);self.norm.extend([n,n,n]);self.indices.extend((k,k+1,k+2))
    def quad(self,a,b,c,d):self.face(a,b,c);self.face(a,c,d)
    def box(self,center,size):
        x,y,z=center;w,h,d=[v/2 for v in size]
        pts=[(x-w,y-h,z-d),(x+w,y-h,z-d),(x+w,y+h,z-d),(x-w,y+h,z-d),(x-w,y-h,z+d),(x+w,y-h,z+d),(x+w,y+h,z+d),(x-w,y+h,z+d)]
        for a,b,c,d0 in [(0,3,2,1),(4,5,6,7),(0,4,7,3),(1,2,6,5),(3,7,6,2),(0,1,5,4)]:self.quad(pts[a],pts[b],pts[c],pts[d0])
    def cylinder(self,a,b,r1,r2=None,sides=10):
        if r2 is None:r2=r1
        direction=norm(sub(b,a)); helper=(1.,0.,0.) if abs(direction[0])<.85 else (0.,0.,1.)
        u=norm(cross(direction,helper));v=norm(cross(direction,u))
        around=lambda c,r,i:add(c,add(scale(u,r*math.cos(i*2*PI/sides)),scale(v,r*math.sin(i*2*PI/sides))))
        for i in range(sides):
            j=(i+1)%sides; a0=around(a,r1,i);a1=around(a,r1,j);b0=around(b,r2,i);b1=around(b,r2,j)
            self.quad(a0,a1,b1,b0);self.face(a,a1,a0);self.face(b,b0,b1)
    def gem(self,center,size,shape='round'):
        # Stone face up (+Y). Faceted gemstone with crown and pavilion.
        sides=16 if shape=='round' else 4
        theta=PI/4 if shape=='square' else 0
        radius=size*.50 if sides==16 else size*.69
        y0=center[1]
        def ring(y,r):return [(center[0]+r*math.cos(2*PI*i/sides+theta),y,center[2]+r*math.sin(2*PI*i/sides+theta)) for i in range(sides)]
        girdle=ring(y0,radius);table=ring(y0+size*.20,radius*.55)
        point=(center[0],y0-size*.32,center[2]);top=(center[0],y0+size*.20,center[2])
        for i in range(sides):
            j=(i+1)%sides
            self.quad(girdle[i],table[i],table[j],girdle[j]);self.face(table[i],top,table[j]);self.face(point,girdle[i],girdle[j])


def aligned_samples(length, count):
    # Ellipse in XZ plane; arclength-equal sampling, clasp occupies one slot.
    ratio=.72;a=length/(PI*(3*(1+ratio)-math.sqrt((3+ratio)*(1+3*ratio))))
    b=a*ratio;steps=8192;cum=[0.];coords=[]
    for i in range(steps+1):
        t=2*PI*i/steps;coords.append((a*math.cos(t),0.,b*math.sin(t)))
        if i: cum.append(cum[-1]+math.dist(coords[i],coords[i-1]))
    arr=[]
    for k in range(count):
        target=cum[-1]*(k+.5)/count;j=max(1,bisect.bisect_left(cum,target))
        frac=(target-cum[j-1])/(cum[j]-cum[j-1])
        t=2*PI*(j-1+frac)/steps
        p=(a*math.cos(t),0.,b*math.sin(t))
        tangent=norm((-a*math.sin(t),0.,b*math.cos(t)))
        radial=norm((math.cos(t),0.,math.sin(t)))
        arr.append((p,tangent,radial))
    return arr

def generate(params,target):
    length=float(params['length_mm']);size=float(params['stone_mm'])
    shape=params['shape'];metal=params['metal'];clasp=params['clasp']
    if not 130<=length<=230 or not 1.5<=size<=5 or shape not in ('round','square') or metal not in ('silver','gold','rose') or clasp not in ('box','lobster'):
        raise ValueError('Invalid tennis bracelet parameters')
    count=max(18,min(150,round(length/(size*(1.30 if shape=='round' else 1.40)))))
    path=aligned_samples(length,count)
    m=Mesh();stones=Mesh();accent=Mesh()
    # Metal setting per link: low-profile cup and bridge links. No irregular image-to-mesh reconstruction.
    for i,(p,t,radial) in enumerate(path):
        if i==0:continue  # reserved clasp segment
        stone_pos=add(p,(0,size*.36,0))
        m.cylinder(add(p,(0,-size*.13,0)),add(p,(0,size*.21,0)),size*.36, size*.40,12)
        stones.gem(stone_pos,size,shape)
        for sx in (-1,1):
            for sz in (-1,1):
                if shape=='square':
                    off=add(scale(t,sx*size*.39),scale(radial,sz*size*.39))
                else: off=add(scale(t,sx*size*.32),scale(radial,sz*size*.32))
                a=add(p,add(off,(0,size*.12,0)))
                b=add(a,(0,size*.39,0))
                m.cylinder(a,b,size*.065,size*.045,8)
        # Connector pin between segments, positioned below stones.
        nxt=path[(i+1)%count][0]
        if (i+1)%count!=0:
            a=add(p,(0,-size*.20,0));b=add(nxt,(0,-size*.20,0))
            m.cylinder(a,b,size*.15,sides=10)
    # Clasp near first path point: structural box / lobster-concept enclosure.
    p0,t0,_=path[0];box_center=add(p0,(0,-size*.08,0))
    if clasp=='box':
        m.box(box_center,(size*1.3,size*.60,size*.85))
        accent.box(add(box_center,(0,size*.31,0)),(size*.75,size*.075,size*.45))
        for s in (-1,1):
            a=add(box_center,(s*size*.62,0,0));b=add(a,(s*size*.24,0,0))
            m.cylinder(a,b,size*.09,sides=12)
    else:
        m.cylinder(add(box_center,(0,-size*.2,0)),add(box_center,(0,size*.28,0)),size*.34,sides=16)
        m.cylinder(add(box_center,(-size*.28,0,0)),add(box_center,(size*.30,0,0)),size*.08,sides=12)
    # Colors from source material selection; glTF metallic-roughness only.
    colors={'silver':[.79,.82,.86,1.], 'gold':[.92,.66,.20,1.], 'rose':[.85,.49,.40,1.]}
    materials=[{'pbrMetallicRoughness':{'baseColorFactor':colors[metal],'metallicFactor':.92,'roughnessFactor':.17},'doubleSided':True},
               {'pbrMetallicRoughness':{'baseColorFactor':[.91,.96,1.,1.],'metallicFactor':.03,'roughnessFactor':.06},'doubleSided':True},
               {'pbrMetallicRoughness':{'baseColorFactor':[.55,.57,.60,1.],'metallicFactor':.85,'roughnessFactor':.28},'doubleSided':True}]
    binary=bytearray();accessors=[];views=[];primitives=[]
    def buffer(data,target,component_type,item_type,count,mins=None,maxs=None):
        while len(binary)%4:binary.append(0)
        off=len(binary);binary.extend(data)
        vid=len(views);views.append({'buffer':0,'byteOffset':off,'byteLength':len(data),'target':target})
        aid=len(accessors);a={'bufferView':vid,'componentType':component_type,'count':count,'type':item_type}
        if mins is not None:a['min']=mins;a['max']=maxs
        accessors.append(a);return aid
    for mat,mesh in enumerate((m,stones,accent)):
        if not mesh.pos:continue
        vertices=[x for p in mesh.pos for x in p];normals=[x for p in mesh.norm for x in p]
        pos=buffer(struct.pack('<%sf'%len(vertices),*vertices),34962,5126,'VEC3',len(mesh.pos),[min(p[k] for p in mesh.pos) for k in range(3)],[max(p[k] for p in mesh.pos) for k in range(3)])
        no=buffer(struct.pack('<%sf'%len(normals),*normals),34962,5126,'VEC3',len(mesh.norm))
        ix=buffer(struct.pack('<%sI'%len(mesh.indices),*mesh.indices),34963,5125,'SCALAR',len(mesh.indices))
        primitives.append({'attributes':{'POSITION':pos,'NORMAL':no},'indices':ix,'material':mat,'mode':4})
    gltf={'asset':{'version':'2.0','generator':'Caratzon Parametric Tennis Bracelet V1'},'scene':0,'scenes':[{'nodes':[0]}],
          'nodes':[{'mesh':0,'name':'Tennis Bracelet (concept only)'}],'meshes':[{'primitives':primitives}],
          'buffers':[{'byteLength':len(binary)}],'bufferViews':views,'accessors':accessors,'materials':materials,
          'extras':{'stone_count':count-1,'nominal_length_mm':length,'stone_diameter_mm':size,'warning':'Concept model only - NOT manufacturing CAD'}}
    j=json.dumps(gltf,separators=(',',':')).encode('utf8');j+=b' ' * ((-len(j))%4)
    binary+=b'\0' *((-len(binary))%4)
    total=12+8+len(j)+8+len(binary)
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('wb') as f:
        f.write(struct.pack('<4sII',b'glTF',2,total));f.write(struct.pack('<I4s',len(j),b'JSON'));f.write(j)
        f.write(struct.pack('<I4s',len(binary),b'BIN\0'));f.write(binary)
    return {'stone_count':count-1,'bytes':total}

if __name__=='__main__':
    r=generate({'length_mm':170,'stone_mm':3,'shape':'round','metal':'silver','clasp':'box'},Path(__file__).parent/'test_bracelet.glb')
    print(r)
