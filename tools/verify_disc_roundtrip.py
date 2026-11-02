"""Extract disc parts, reserialize FST/DOL tables, reconstruct a comparison stream.

The stream is compared byte-for-byte and hashed; no playable ISO is produced.
Known RSC wrappers are taken from the independently repacked files. Unknown
data, boot code and gaps are deliberately opaque and preserved verbatim.
"""
import hashlib
import json
import struct
from inspect_discs import ROOT, INPUTS, save

CHUNK = 8*1024*1024


def extract_range(source, target, start, size):
    source.seek(start)
    with target.open('wb') as out:
        while size:
            data=source.read(min(size,CHUNK))
            assert data
            out.write(data); size-=len(data)


def main():
    results=[]
    for region,filename in INPUTS:
        inv=json.loads((ROOT/f'metadata/disc_inventory_{region}.json').read_text(encoding='utf8'))
        original=next(r for r in json.loads((ROOT/'metadata/originals.json').read_text(encoding='utf8'))['files'] if r['path']==filename)
        folder=ROOT/f'work/disc-roundtrip/{region}'
        folder.mkdir(parents=True,exist_ok=True)
        parts=[dict(start=inv['dol']['offset'],size=inv['dol']['size'],kind='dol',name='main.dol'),
               dict(start=inv['fst_offset'],size=inv['fst_size'],kind='fst',name='fst.bin')]
        parts += [dict(start=f['offset'],size=f['size'],kind='file',name=f['path']) for f in inv['files']]
        parts.sort(key=lambda p:p['start'])
        covered=[]; pos=0
        for p in parts:
            assert p['start']>=pos, 'Overlaps need explicit shared-extent handling'
            if p['start']>pos:
                covered.append(dict(start=pos,size=p['start']-pos,kind='opaque',name='gap'))
            covered.append(p);pos=p['start']+p['size']
        size=(ROOT/filename).stat().st_size
        if pos<size:
            covered.append(dict(start=pos,size=size-pos,kind='opaque',name='tail'))
        with (ROOT/filename).open('rb') as source:
            for i,p in enumerate(covered):
                p['disk_file']=f'{i:03}.bin'
                extract_range(source,folder/p['disk_file'],p['start'],p['size'])
        save(folder/'parts.json',covered)
        # Persist structured FST fields and each independently decoded name.
        fstpart=next(p for p in covered if p['kind']=='fst')
        fst=(folder/fstpart['disk_file']).read_bytes()
        count=struct.unpack_from('>I',fst,8)[0]
        names=fst[12*count:]
        entries=[]
        for i in range(count):
            w,a,b=struct.unpack_from('>3I',fst,12*i)
            nameoff=w&0xffffff
            end=names.index(0,nameoff)
            name=names[nameoff:end].decode('shift_jis')
            assert name.encode('shift_jis')==names[nameoff:end]
            entries.append(dict(kind=w>>24,name_offset=nameoff,name=name,a=a,b=b))
        save(folder/'fst.json',dict(entries=entries,name_table_hex=names.hex()))
        model=json.loads((folder/'fst.json').read_text(encoding='utf8'))
        strings=bytearray.fromhex(model['name_table_hex']); headers=bytearray()
        for e in model['entries']:
            data=e['name'].encode('shift_jis')+b'\0'
            strings[e['name_offset']:e['name_offset']+len(data)]=data
            headers.extend(struct.pack('>3I',(e['kind']<<24)|e['name_offset'],e['a'],e['b']))
        rebuilt_fst=headers+strings
        assert rebuilt_fst==fst
        (folder/'fst.rebuilt.bin').write_bytes(rebuilt_fst)
        fstpart['reassembled_file']='fst.rebuilt.bin'
        # Decode/re-encode DOL section header integers and confirmed message strings.
        dolpart=next(p for p in covered if p['kind']=='dol')
        dol=bytearray((folder/dolpart['disk_file']).read_bytes())
        words=list(struct.unpack_from('>57I',dol))
        save(folder/'dol_header.json',words)
        words=json.loads((folder/'dol_header.json').read_text(encoding='utf8'))
        struct.pack_into('>57I',dol,0,*words)
        messages=json.loads((ROOT/f'work/analysis/{region}/confirmed_messages.json').read_text(encoding='utf8'))
        for row in messages['messages']:
            data=row['source'].encode('cp932')+b'#'
            assert len(data)==row['byte_length']+1
            dol[row['offset']:row['offset']+len(data)]=data
        assert hashlib.sha256(dol).hexdigest()==inv['dol']['sha256']
        (folder/'dol.rebuilt.bin').write_bytes(dol)
        dolpart['reassembled_file']='dol.rebuilt.bin'
        for p in covered:
            if p['kind']=='file' and p['name'].endswith('.RSC'):
                p['rsc_reassembled_file']=str(ROOT/f'work/roundtrip/{region}'/p['name']/'repacked.rsc')
        save(folder/'parts.json',covered)
        reread=json.loads((folder/'parts.json').read_text(encoding='utf8'))
        rebuilt_hash=hashlib.sha256(); original_hash=hashlib.sha256(); compared=0
        with (ROOT/filename).open('rb') as source:
            for p in reread:
                path=ROOT/p['rsc_reassembled_file'] if 'rsc_reassembled_file' in p else folder/p.get('reassembled_file',p['disk_file'])
                assert path.stat().st_size==p['size'] and compared==p['start']
                with path.open('rb') as component:
                    while data:=component.read(CHUNK):
                        original_data=source.read(len(data))
                        assert data==original_data, f'Byte mismatch near {compared:#x}'
                        rebuilt_hash.update(data); original_hash.update(original_data);compared+=len(data)
            assert not source.read(1)
        assert compared==size and rebuilt_hash.hexdigest()==original_hash.hexdigest()==original['sha256']
        result=dict(edition=region,compared_bytes=compared,differing_bytes=0,
                    reconstructed_stream_sha256=rebuilt_hash.hexdigest(),original_sha256=original_hash.hexdigest(),
                    extracted_fst_files=len(inv['files']),reserialized_rsc_archives=70,
                    method='Disk parts -> reserialized FST, DOL header/messages, RSC wrappers -> ordered stream -> byte comparison and SHA-256',
                    limits='Original offsets retained. Opaque boot/code/unknown payloads/gaps preserved. No relocation, translated build, runtime or hardware validation; no output ISO written.')
        results.append(result);print(result,flush=True)
    save(ROOT/'metadata/disc_roundtrip.json',dict(editions=results))


if __name__=='__main__':
    main()
