"""Capacity guards and texture boundary checks; never writes game binaries."""
import copy
import json
from PIL import Image
from inspect_discs import ROOT, save
from inspect_rsc import parse
from prepare_full_font import prepare, encode
from full_text_components import main_table, dialogue, credits
from encode_gx_localized import encode_changed
from decode_gx import decode


def main():
    f=prepare();rows=f['rows'];mapping=f['mapping'];passed=[]
    def rejects(name,call):
        try:call()
        except (AssertionError, UnicodeEncodeError, KeyError):passed.append(name)
        else:raise AssertionError(name+' unexpectedly accepted')
    altered=copy.deepcopy(rows);next(r for r in altered if r['id'].startswith('main/'))['translation']='가'*20000
    rejects('main capacity overflow',lambda:main_table(f['raw'],f['sections'],altered,mapping))
    rs=copy.deepcopy([r for r in rows if r['id'].startswith('rsc/')]);path=rs[0]['file'];member=rs[0]['member'];rs=[r for r in rs if r['file']==path and r['member']==member]
    b=(ROOT/'work/extraction/jp/files'/path).read_bytes();entry=parse(b)[member];p=entry['header_offset']+32;raw=b[p:p+entry['size']]
    bad=bytearray(raw);bad[:4]=b'BAD!'
    rejects('dialogue invalid header',lambda:dialogue(bytes(bad),rs,mapping))
    rs[0]['translation']='가'*20000
    rejects('dialogue capacity overflow',lambda:dialogue(raw,rs,mapping))
    rs=copy.deepcopy([r for r in rows if r['id'].startswith('credits/')]);b=(ROOT/'work/extraction/jp/files'/rs[0]['file']).read_bytes();rs[0]['translation']='가'*20000
    rejects('credits capacity overflow',lambda:credits(b,rs,mapping))
    rejects('unmapped Hangul',lambda:encode('힣',mapping))
    # Non-multiple-of-four sizes exercise edge-tile padding. Every original
    # texel is reencoded, including both RGB5A3 representation branches.
    for fmt,tile_bytes in [(5,32),(6,64)]:
        w,h=5,7;raw=bytes((i*37+11)%256 for i in range(4*tile_bytes));image=decode(raw,w,h,fmt)
        encoded,_,_=encode_changed(raw,w,h,fmt,image,force_all=True);assert encoded==raw
        changed=image.copy();changed.putpixel((4,6),(255,0,0,255));encoded,decoded,_=encode_changed(raw,w,h,fmt,changed)
        assert decoded.getpixel((4,6))==(255,0,0,255)
        n=8;block=3*tile_bytes;allowed={block+n*2,block+n*2+1}
        if fmt==6:allowed.update((block+32+n*2,block+33+n*2))
        assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(raw,encoded)))
        rejects(f'format {fmt} wrong image size',lambda:encode_changed(raw,w,h,fmt,Image.new('RGBA',(4,4))))
        passed.append(f'format {fmt} edge texel and padding preservation')
    report={'passed':passed,'count':len(passed),'scope':'In-memory rejection and texture boundary tests; not game execution'}
    save(ROOT/'metadata/full_preparation_guard_tests.json',report);print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
