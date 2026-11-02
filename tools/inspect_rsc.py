"""Validate RSC member boundaries; payload formats remain opaque.

Reference: Venomalia/DolphinTextureExtraction-tool RSC.cs at commit
2b9619ced977277ad0be11dae7a1e13c031df822. No external code is executed.
"""
import collections
import hashlib
import json
import struct
from inspect_discs import ROOT,save


def parse(raw):
    assert len(raw)>=64
    pos=32;entries=[];seen=set()
    while True:
        assert pos not in seen and pos+32<=len(raw)
        seen.add(pos)
        words=struct.unpack_from('>8I',raw,pos)
        kind,size,nxt=words[:3];end=pos+32+size
        assert kind<=14 and end<=len(raw)
        limit=nxt or len(raw)
        assert end<=limit<=len(raw) and (not nxt or nxt>pos)
        data=raw[pos+32:end]
        entries.append(dict(index=len(entries),type=kind,header_offset=pos,
                            size=size,next_offset=nxt,reserved=list(words[3:]),
                            padding_size=limit-end,sha256=hashlib.sha256(data).hexdigest(),
                            magic_hex=data[:16].hex()))
        if not nxt:break
        pos=nxt
    # Repack the parsed container headers and preserve opaque payloads/padding.
    # This checks the wrapper structure only, not its inner asset formats.
    rebuilt=bytearray(raw[:32])
    for e in entries:
        assert len(rebuilt)==e['header_offset']
        rebuilt.extend(struct.pack('>8I',e['type'],e['size'],e['next_offset'],*e['reserved']))
        start=e['header_offset']+32
        rebuilt.extend(raw[start:start+e['size']+e['padding_size']])
    assert rebuilt==raw
    return entries


def main():
    output=[]
    for edition,name in [('jp','Wario World (Japan).iso'),('us','Wario World (USA).iso')]:
        inv=json.loads((ROOT/f'metadata/disc_inventory_{edition}.json').read_text(encoding='utf8'))
        records=[]
        with (ROOT/name).open('rb') as f:
            for e in inv['files']:
                if not e['path'].lower().endswith('.rsc'):continue
                f.seek(e['offset']);raw=f.read(e['size'])
                assert hashlib.sha256(raw).hexdigest()==e['sha256']
                entries=parse(raw)
                records.append(dict(path=e['path'],size=len(raw),members=entries,
                                    wrapper_roundtrip_equal=True))
        counts=collections.Counter(e['type'] for r in records for e in r['members'])
        print(edition,len(records),'archives',sum(counts.values()),'members',dict(counts))
        output.append(dict(edition=edition,archives=records,member_type_counts=dict(counts)))
    save(ROOT/'metadata/rsc_inventory.json',dict(
        reference='https://github.com/Venomalia/DolphinTextureExtraction-tool/blob/2b9619ced977277ad0be11dae7a1e13c031df822/lib/AuroraLip/Archives/Formats/RSC.cs',
        scope='Container boundaries and header repacking only; payloads and padding preserved verbatim. Not inner asset extraction/recompression or ISO rebuild.',
        editions=output))


if __name__=='__main__':main()
