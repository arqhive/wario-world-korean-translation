"""Verify extraction hashes and rebuild source text from saved JSON, in memory.

Roundtrip covers known text structures. Event/model bytes remain opaque;
texture PNG pixel verification does not imply CMPR recompression equality.
"""
import collections
import json
import struct
from PIL import Image
from inspect_discs import ROOT,save
from extract_stage4 import OUT,sha,readj


def main():
    inv=readj(ROOT/'metadata/extraction_inventory.json');results=[]
    for f in inv['files']:
        b=(ROOT/f['extracted']).read_bytes();assert len(b)==f['size'] and sha(b)==f['sha256']
    for reg in ['jp','us']:
        rows=readj(ROOT/'translation/messages.json')['messages'] if reg=='jp' else readj(OUT/reg/'messages.json')['messages']
        assert len({r['id'] for r in rows})==len(rows)
        grouped=collections.defaultdict(list)
        for r in rows:grouped[(r['file'],r.get('member'))].append(r)
        for (file,member),subset in grouped.items():
            path=OUT/reg/'files'/file if member is None else ROOT/f'work/roundtrip/{reg}'/file/f'{member:03}.bin'
            raw=path.read_bytes();new=bytearray(raw)
            if member is not None:
                rt=next(r for r in inv['dialogue_roundtrips'] if (r['region'],r['file'],r['member'])==(reg,file,member))
                struct.pack_into('>5I',new,0,int.from_bytes(b'0827','big'),rt['count'],5,rt['event_count'],rt['event_offset_words'])
                for r in subset:struct.pack_into('>I',new,20+4*r['index'],r['offset']//4)
            for r in subset:
                term=b'#' if file=='main.dol' else b'\0'
                data=r['source'].encode('cp932')+term;assert len(data)==r['byte_length']+1
                new[r['offset']:r['offset']+len(data)]=data
            assert new==raw,(reg,file,member)
            results.append({'region':reg,'file':file,'member':member,'messages':len(subset),'json_source_roundtrip_equal':True,'sha256':sha(raw)})
    unique={}
    for t in inv['textures']:
        for level in t['levels']:unique[level['png']]=level
    for path,l in unique.items():
        with Image.open(ROOT/path) as im:
            assert im.mode=='RGBA' and im.size==(l['width'],l['height']) and sha(im.tobytes())==l['rgba_sha256'],path
    # Compare independently extracted old I4 grayscale PNGs against new RGBA channels.
    old_i4=0
    old=readj(ROOT/'metadata/asset_roundtrip.json')
    current={(t['region'],t['file'],t['member'],t['texture']):t for t in inv['textures'] if t['tpl_offset']==0}
    for ed in old['editions']:
        reg=ed['summary']['edition']
        for t in ed['textures']:
            if t['pixel_roundtrip']=='not_tested':continue
            oldpath=ROOT/f'work/roundtrip/{reg}'/t['archive']/f'{t["member"]:03}_{t["texture"]:03}_i4.png'
            a=Image.open(oldpath).tobytes();b=Image.open(ROOT/current[(reg,t['archive'],t['member'],t['texture'])]['levels'][0]['png']).split()
            assert all(c.tobytes()==a for c in b);old_i4+=1
    out={'files_hash_verified':len(inv['files']),'text_roundtrips':results,
         'unique_png_pixels_verified':len(unique),'independent_i4_crosschecks':old_i4,
         'scope':'Known text structures from saved JSON match original binary; binary outside text preserved. Full asset compression rebuild and runtime display not tested.'}
    save(ROOT/'metadata/extraction_verification.json',out)
    print(json.dumps({k:v for k,v in out.items() if k!='text_roundtrips'},ensure_ascii=False))


if __name__=='__main__':main()
