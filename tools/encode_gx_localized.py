"""Encode approved RGB5A3/RGBA8 edits, retaining original bytes for untouched texels."""
import struct
import numpy as np
from PIL import Image
from decode_gx import decode, expand


def encode_changed(original,width,height,fmt,image,force_all=False):
    assert fmt in (5,6) and image.size==(width,height) and image.mode=='RGBA'
    old=np.array(decode(original,width,height,fmt));new=np.array(image)
    changed=np.any(old!=new,axis=2);out=bytearray(original);nx=(width+3)//4
    for y,x in np.argwhere(np.ones_like(changed) if force_all else changed):
        r,g,b,a=map(int,new[y,x]);block=((int(y)//4)*nx+int(x)//4)*(32 if fmt==5 else 64);n=(int(y)%4)*4+int(x)%4
        if fmt==6:
            out[block+2*n:block+2*n+2]=bytes((a,r));out[block+32+2*n:block+34+2*n]=bytes((g,b))
        else:
            q5=[(v*31+127)//255 for v in (r,g,b)];q4=[(v*15+127)//255 for v in (r,g,b)];q3=(a*7+127)//255
            opaque=0x8000|(q5[0]<<10)|(q5[1]<<5)|q5[2]
            alpha=(q3<<12)|(q4[0]<<8)|(q4[1]<<4)|q4[2]
            op=[int(expand(v,5)) for v in q5]+[255];al=[v*17 for v in q4]+[int(expand(q3,3))]
            # Select representable color by squared RGBA error, preserving opaque precision.
            score=lambda values:sum((u-v)**2 for u,v in zip(values,(r,g,b,a)))
            if not changed[y,x]:
                # RGB5A3 has two equivalent encodings for some opaque colors.
                # Preserve the original selector as roundtrip metadata, not payload bytes.
                selector=struct.unpack_from('>H',original,block+n*2)[0]&0x8000
                value=opaque if selector else alpha
            else:value=opaque if score(op)<=score(al) else alpha
            struct.pack_into('>H',out,block+n*2,value)
    decoded=decode(bytes(out),width,height,fmt);pixels=np.array(decoded)
    assert np.array_equal(pixels[~changed],old[~changed])
    if fmt==6:assert np.array_equal(pixels,new)
    return bytes(out),decoded,{'changed_input_pixels':int(changed.sum()),'unmodified_pixel_differences_after_encoding':0,
                               'max_channel_quantization_error':np.abs(pixels.astype(int)-new.astype(int)).max(axis=(0,1)).tolist()}
