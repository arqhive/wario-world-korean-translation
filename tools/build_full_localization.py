"""Build explicitly requested test ISO; original discs and older builds are immutable."""
import argparse
import hashlib
import json
import shutil
import struct
from pathlib import Path
import numpy as np
from inspect_discs import ROOT, save
from prepare_full_localization import prepare, read
from prepare_output_probe import sha
from file_patcher import scan as scan_disc, relayout
from research_code import load

CHUNK=8*1024*1024


def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def select(prepared,skip_main=False,omit=()):
    assert set(omit)<=prepared['files'].keys(),'Unknown component file'
    dol=bytearray(prepared['dol'])
    if skip_main:
        raw,_=load('jp');a,b=prepared['report']['components'][0]['range'];dol[a:b]=raw[a:b]
    return bytes(dol),{p:b for p,b in prepared['files'].items() if p not in omit}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--name',default='WarioWorld_KO_FullTest_v01')
    parser.add_argument('--skip-main',action='store_true')
    parser.add_argument('--omit-file',action='append',default=[])
    parser.add_argument('--desktop',action='store_true')
    parser.add_argument('--font-weight',choices=['medium','bold'],default='medium')
    parser.add_argument('--gmarket-alnum',action='store_true')
    parser.add_argument('--gmarket-symbols',action='store_true')
    parser.add_argument('--lower-question-exclamation',action='store_true')
    args=parser.parse_args()
    assert args.name and all(c.isascii() and (c.isalnum() or c in '_-') for c in args.name)
    state=read('project.json')
    assert state['decisions']['full_localization_build_requested'] is True
    assert state['decisions']['external_viewer_text_original_preservation_approved'] is True
    output=ROOT/'build'/(args.name+'.iso');partial=output.with_suffix('.iso.partial')
    desktop=Path.home()/'Desktop'/output.name
    assert not output.exists() and not partial.exists(),'Never overwrite existing builds'
    if args.desktop:assert desktop.parent.is_dir() and not desktop.exists()
    source=ROOT/'Wario World (Japan).iso';original=next(x for x in read('metadata/originals.json')['files'] if x['edition']=='jp')
    assert source.stat().st_size==original['size_bytes'] and digest(source)==original['sha256']
    prepared=prepare(args.font_weight,args.gmarket_alnum,args.gmarket_symbols,args.lower_question_exclamation);dol,files=select(prepared,args.skip_main,args.omit_file)
    inv=read('metadata/disc_inventory_jp.json');entries={r['path']:r for r in inv['files']}
    disc=scan_disc(source);dol_at=disc['dol']['offset'];fst_at,fst,moved=relayout(disc,len(dol))
    where=lambda p:moved.get(p,entries[p]['offset'])
    changes=[(0x420,struct.pack('>II',dol_at,fst_at)),(dol_at,dol),(fst_at,fst)]
    changes.extend((where(p),b) for p,b in files.items())
    with source.open('rb') as f:
        for p in moved:
            if p not in files:f.seek(entries[p]['offset']);changes.append((moved[p],f.read(entries[p]['size'])))
    changes.sort()
    assert all(a+len(b)<=c for (a,b),(c,_) in zip(changes,changes[1:]))
    assert all(len(b)==entries[p]['size'] for p,b in files.items())
    def patch(block,pos):
        out=bytearray(block)
        for start,data in changes:
            lo=max(pos,start);hi=min(pos+len(block),start+len(data))
            if lo<hi:out[lo-pos:hi-pos]=data[lo-start:hi-start]
        return bytes(out)
    output.parent.mkdir(parents=True,exist_ok=True)
    with source.open('rb') as inp,partial.open('xb') as out:
        pos=0
        while block:=inp.read(CHUNK):out.write(patch(block,pos));pos+=len(block)
    assert partial.stat().st_size==source.stat().st_size
    oldhash=hashlib.sha256();newhash=hashlib.sha256();different=0;pos=0
    with source.open('rb') as inp,partial.open('rb') as built:
        while old:=inp.read(CHUNK):
            new=built.read(len(old));assert new==patch(old,pos),f'Unexpected disc change at {pos:#x}'
            different+=int(np.count_nonzero(np.frombuffer(old,dtype=np.uint8)!=np.frombuffer(new,dtype=np.uint8)))
            oldhash.update(old);newhash.update(new);pos+=len(old)
        assert not built.read(1)
    assert oldhash.hexdigest()==original['sha256']
    checks=[]
    with partial.open('rb') as built:
        built.seek(0x420);assert struct.unpack('>II',built.read(8))==(dol_at,fst_at)
        built.seek(dol_at);assert built.read(len(dol))==dol
        assert {p:(r['offset'],r['size']) for p,r in scan_disc(partial)['files'].items()}=={r['path']:(where(r['path']),r['size']) for r in inv['files']}
        for row in inv['files']:
            built.seek(where(row['path']));b=built.read(row['size']);actual=sha(b)
            expected=sha(files[row['path']]) if row['path'] in files else row['sha256']
            assert actual==expected,row['path']
            if row['path'] in files:
                checks.append({'file':row['path'],'size':len(b),'original_sha256':row['sha256'],'built_sha256':actual,'size_delta':0})
            if row['path']=='opening.bnr':
                src=(ROOT/'work/extraction/jp/files/opening.bnr').read_bytes()
                assert b[:32]==src[:32] and b[0x1820:]==src[0x1820:]
    # Publish only after complete disk and per-file readback succeeds.
    partial.rename(output)
    if args.desktop:
        with output.open('rb') as inp,desktop.open('xb') as out:shutil.copyfileobj(inp,out,CHUNK)
        assert digest(desktop)==newhash.hexdigest()
    report={'output':str(output),'size_bytes':output.stat().st_size,'sha256':newhash.hexdigest(),
        'original_sha256':oldhash.hexdigest(),'original_unchanged':True,'dol_sha256':sha(dol),
        'translation_sha256':prepared['report']['translation_sha256'],'font_payload_sha256':read('metadata/full_font_preparation.json')['payload_sha256'],
        'font_weight':args.font_weight,'gmarket_alnum':args.gmarket_alnum,'gmarket_symbols':args.gmarket_symbols,'lower_question_exclamation':args.lower_question_exclamation,'font_sha256':read('metadata/full_font_preparation.json')['font_sha256'],
        'changed_files':checks,'unchanged_fst_files':len(inv['files'])-len(files),
        'allowed_ranges':[{'offset':o,'length':len(b)} for o,b in changes],
        'differing_bytes':different,'unexpected_differing_bytes':0,'banner_strings':'original_bytes_preserved',
        'main_text_enabled':not args.skip_main,'omitted_files':args.omit_file,
        'desktop_copy':str(desktop) if args.desktop else None,'runtime':'not_tested'}
    save(ROOT/'metadata'/(args.name+'_build.json'),report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
