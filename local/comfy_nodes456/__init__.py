"""Caratzon experimental Flux.2 Klein multi-prompt batch node.
Combines already encoded, independent conditioning tensors on the sample axis.
No prompts or user files are read from disk by this node.
"""
import torch
import torch.nn.functional as F

class CZ456BatchConditioning:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"c1":("CONDITIONING",),"c2":("CONDITIONING",)},
                "optional":{f"c{i}":("CONDITIONING",) for i in range(3,6)}}
    RETURN_TYPES=("CONDITIONING",)
    FUNCTION="combine"
    CATEGORY="Caratzon/Experimental"

    def combine(self,c1,c2,c3=None,c4=None,c5=None):
        cs=[c for c in (c1,c2,c3,c4,c5) if c is not None]
        if not all(isinstance(c,(list,tuple)) and len(c)==1 for c in cs):
            raise ValueError("Only plain single Flux.2 conditioning per customer is supported")
        pairs=[c[0] for c in cs]
        ts=[p[0] for p in pairs]
        if not all(torch.is_tensor(t) and t.ndim==3 and t.shape[0]==1 and t.shape[2]==ts[0].shape[2] for t in ts):
            raise ValueError("Incompatible conditioning tensors")
        lengths=[t.shape[1] for t in ts]
        # Flux.2 normally uses a 512-token minimum; avoid inventing padding for
        # differing long prompts. For already short tensors match its left pad.
        target=max(512,max(lengths))
        if target>512 and len(set(lengths))!=1:
            raise ValueError("Mixed long prompt lengths are not supported; shorten prompts")
        ts=[F.pad(t,(0,0,target-t.shape[1],0)) if t.shape[1]<target else t for t in ts]
        ds=[p[1] for p in pairs]
        if not all(set(d)==set(ds[0]) for d in ds):
            raise ValueError("Incompatible conditioning metadata")
        meta={}
        for key in ds[0]:
            vs=[d[key] for d in ds]
            if all(torch.is_tensor(v) for v in vs):
                if key=="attention_mask" and all(v.ndim==2 and v.shape[0]==1 and v.shape[1]==n for v,n in zip(vs,lengths)):
                    vs=[F.pad(v,(target-v.shape[1],0)) if v.shape[1]<target else v for v in vs]
                if not all(v.ndim>=1 and v.shape[0]==1 and v.shape[1:]==vs[0].shape[1:] for v in vs):
                    raise ValueError("Incompatible metadata: "+key)
                meta[key]=torch.cat(vs,dim=0)
            elif all(v is None for v in vs):meta[key]=None
            elif all(isinstance(v,(str,int,float,bool)) and v==vs[0] for v in vs):meta[key]=vs[0]
            else:raise ValueError("Unsupported conditioning metadata: "+key)
        # Each row remains its own customer's prompt, never concatenate along text.
        return ([[torch.cat(ts,dim=0),meta]],)

NODE_CLASS_MAPPINGS={"CZ456BatchConditioning":CZ456BatchConditioning}
NODE_DISPLAY_NAME_MAPPINGS={"CZ456BatchConditioning":"Caratzon 4.5.6 — Independent prompt batch (experimental)"}
