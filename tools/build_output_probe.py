"""Explicitly requested JP probe build. Never modifies originals or overwrites outputs."""
import hashlib
import json
import struct
from inspect_discs import ROOT,save,hashes
from prepare_output_probe import prepare,DISC_DOL_OFFSET,sha

OUTPUT=ROOT/'build/WarioWorld_KO_OutputTest_v02_Gmarket.iso'
CHUNK=8*1024*1024


def main():
    state=json.loads((ROOT/'project.json').read_text(encoding='utf8'))
    assert state['decisions']['build_requested'] is True, 'An explicit user build instruction is required'
    assert not OUTPUT.exists(), 'Refusing to overwrite an existing test image'
    source=ROOT/'Wario World (Japan).iso'
    original=next(x for x in json.loads((ROOT/'metadata/originals.json').read_text(encoding='utf8'))['files'] if x['path']==source.name)
    inv=json.loads((ROOT/'metadata/disc_inventory_jp.json').read_text(encoding='utf8'))
    recipe=json.loads((ROOT/'metadata/output_probe_preparation.json').read_text(encoding='utf8'))
    prepared=prepare();dol=prepared['dol']
    assert sha(dol)==recipe['in_memory_dol_sha256']
    assert prepared['ttf_sha256']==recipe['source_font_sha256']
    assert prepared['font_fixture_sha256']==recipe['dolphin_fixture_sha256']
    assert prepared['overwritten_filler_sha256']==recipe['planned_iso_changes'][1]['original_range_sha256']
    with source.open('rb') as f:
        original_hashes=hashes(f,0,source.stat().st_size)
    assert original_hashes['sha256']==original['sha256']
    changes=[(0x420,struct.pack('>I',DISC_DOL_OFFSET)),(DISC_DOL_OFFSET,dol)]
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    with source.open('rb') as inp,OUTPUT.open('xb') as out:
        pos=0
        while block:=inp.read(CHUNK):
            changed=bytearray(block)
            for start,data in changes:
                lo=max(pos,start);hi=min(pos+len(block),start+len(data))
                if lo<hi:changed[lo-pos:hi-pos]=data[lo-start:hi-start]
            out.write(changed);pos+=len(block)
    assert OUTPUT.stat().st_size==source.stat().st_size
    # Reopen both complete images; differences outside the two approved ranges fail.
    oldhash=hashlib.sha256();newhash=hashlib.sha256();different=0;pos=0
    with source.open('rb') as inp,OUTPUT.open('rb') as built:
        while old:=inp.read(CHUNK):
            new=built.read(len(old));assert len(new)==len(old)
            oldhash.update(old);newhash.update(new)
            expected=bytearray(old)
            for start,data in changes:
                lo=max(pos,start);hi=min(pos+len(old),start+len(data))
                if lo<hi:
                    assert new[lo-pos:hi-pos]==data[lo-start:hi-start]
                    different+=sum(a!=b for a,b in zip(old[lo-pos:hi-pos],new[lo-pos:hi-pos]))
                    expected[lo-pos:hi-pos]=data[lo-start:hi-start]
            assert new==expected, f'Unexpected disc change near {pos:#x}'
            pos+=len(old)
        assert not built.read(1)
    assert oldhash.hexdigest()==original['sha256']
    with OUTPUT.open('rb') as f:
        f.seek(0x420);assert struct.unpack('>I',f.read(4))[0]==DISC_DOL_OFFSET
        f.seek(DISC_DOL_OFFSET);assert f.read(len(dol))==dol
        for entry in inv['files']:
            assert hashes(f,entry['offset'],entry['size'])['sha256']==entry['sha256'],entry['path']
    report=dict(output=str(OUTPUT),size_bytes=OUTPUT.stat().st_size,sha256=newhash.hexdigest(),
        original_sha256=oldhash.hexdigest(),modified_dol_sha256=sha(dol),
        allowed_ranges=[dict(offset=hex(o),size=len(b)) for o,b in changes],
        differing_bytes=different,unexpected_differing_bytes=0,unchanged_fst_files=len(inv['files']),
        original_unchanged=True,recipe='metadata/output_probe_preparation.json',
        runtime='Not established by this builder; tracked in project.json')
    save(ROOT/'metadata/output_probe_build_v02.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
