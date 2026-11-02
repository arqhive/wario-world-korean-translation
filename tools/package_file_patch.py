"""Create per-file XOR differences from verified local images, not full game files."""
import json
import struct
import zlib
import zipfile
from pathlib import Path
import numpy as np
from inspect_discs import ROOT,save
from file_patcher import scan,region,sha,file_sha,apply_delta,VERSION,RELEASE_NAME,BUILD_NAME


def delta(old,new):
    baseline=bytearray(old[:len(new)]);baseline.extend(b'\0'*(len(new)-len(baseline)))
    xor=np.bitwise_xor(np.frombuffer(baseline,dtype=np.uint8),np.frombuffer(new,dtype=np.uint8));positions=np.flatnonzero(xor)
    spans=[]
    for i in positions:
        i=int(i)
        if spans and i-spans[-1][1]<=8:spans[-1][1]=i+1
        else:spans.append([i,i+1])
    raw=bytearray(b'WWD1'+struct.pack('>III',len(old),len(new),len(spans)))
    for a,b in spans:raw.extend(struct.pack('>II',a,b-a));raw.extend(xor[a:b].tobytes())
    packed=zlib.compress(bytes(raw),9)
    assert apply_delta(old,packed,len(new))==new
    return packed,len(positions),len(spans)


def main():
    source=ROOT/'Wario World (Japan).iso';target=ROOT/'build'/(BUILD_NAME+'.iso')
    evidence=json.loads((ROOT/'metadata'/(BUILD_NAME+'_build.json')).read_text(encoding='utf-8'))
    assert file_sha(source)==evidence['original_sha256'] and file_sha(target)==evidence['sha256']
    a=scan(source);b=scan(target);assert a['files']==b['files']
    manifest={'format':'wario-file-delta-v1','version':VERSION,'game_id':'GWWJ01','revision':0,
        'apploader_sha256':a['apploader_sha256'],'files':{},'dol':{},'patches':[],
        'reference_original_iso_sha256':evidence['original_sha256'],'reference_patched_iso_sha256':evidence['sha256'],
        'note':'Whole-image reference hashes are informational. Compatibility uses every internal file and original DOL/Apploader.'}
    payloads={};summary=[]
    with source.open('rb') as src,target.open('rb') as dst:
        for name,r in list(a['files'].items())+[('@main.dol',a['dol'])]:
            other=b['dol'] if name=='@main.dol' else b['files'][name]
            old=region(src,r['offset'],r['size']);new=region(dst,other['offset'],other['size'])
            details={'size':len(old),'sha256':sha(old)}
            if name=='@main.dol':manifest['dol']=details
            else:manifest['files'][name]=details
            if old==new:continue
            packed,count,runs=delta(old,new);p=f'patches/{len(payloads):02}.wwd';payloads[p]=packed
            manifest['patches'].append({'target':name,'size':len(new),'sha256':sha(new),'delta':p,'delta_sha256':sha(packed)})
            summary.append({'target':name,'old_size':len(old),'new_size':len(new),'xor_nonzero_bytes':count,'runs':runs,'delta_size':len(packed)})
    assert len(payloads)==14,[s["target"] for s in summary]
    out=ROOT/'dist'/RELEASE_NAME;out.mkdir(parents=True,exist_ok=True)
    bundle=out/'patch-data.zip'
    with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_STORED) as z:
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        for p,blob in payloads.items():z.writestr(p,blob)
    save(ROOT/'metadata/file_patch_package.json',{'version':VERSION,'bundle':str(bundle.relative_to(ROOT)),
         'sha256':file_sha(bundle),'size':bundle.stat().st_size,'format':'per-file compressed sparse XOR delta',
         'internal_targets':summary,'full_game_files_included':False})
    print('Patch bundle:',bundle,'bytes:',bundle.stat().st_size)


if __name__=='__main__':main()
