"""In-memory full text insertion recipes. No patched files are written."""
import struct
from inspect_discs import ROOT
from research_code import offset
from prepare_full_font import encode
import prepare_output_probe as probe


def main_table(raw,sections,rows,mapping,source=False):
    start=offset(sections,0x801b4e40);end=offset(sections,0x801b7364)
    data=bytearray(88);struct.pack_into('>I',data,0,21)
    for group in range(21):
        struct.pack_into('>I',data,4+4*group,len(data)//4)
        for row in [r for r in rows if r['id'].startswith(f'main/{group:02}/')]:
            text=row['source'] if source else row['translation']
            value=text.encode('cp932') if source else encode(text,mapping)
            assert b'#' not in value and b'\0' not in value
            data.extend(value+b'#')
        if group<20:data.extend(b'\0'*(4-len(data)%4))
    assert len(data)<=end-start,(len(data),end-start)
    packed=data+b'\0'*(end-start-len(data))
    out=bytearray(raw);out[start:end]=packed
    if source:assert out==raw,'Original main table roundtrip failed'
    return bytes(out),{'range':[start,end],'used_bytes':len(data),'capacity':end-start,'rows':269}


def dialogue(raw,rows,mapping,source=False):
    assert raw[:4]==b'0827'
    count,stride,events,eoff=struct.unpack_from('>4I',raw,4)
    assert stride==5 and count==len(rows)
    # Event-bearing CED has opaque animation data BEFORE the event index table.
    # Preserve the entire tail after the original aligned final string, not just eoff.
    last=max(rows,key=lambda r:r['index'])
    last_end=last['offset']+last['byte_length']+1
    limit=(last_end+3)&~3 if events else len(raw)
    assert (events==0 and eoff==0) or 20+4*count<=limit<=eoff*4<=len(raw)
    out=bytearray(raw);pos=20+4*count;region=bytearray()
    for row in sorted(rows,key=lambda r:r['index']):
        position=pos+len(region);assert position%4==0
        struct.pack_into('>I',out,20+4*row['index'],position//4)
        value=row['source'].encode('cp932') if source else encode(row['translation'],mapping)
        region.extend(value+b'\0')
        # Last string can end at non-aligned end of a no-event payload.
        if row['index']<count-1:region.extend(b'\0'*(-len(region)%4))
    assert pos+len(region)<=limit,(len(region),limit-pos)
    out[pos:limit]=region+b'\0'*(limit-pos-len(region))
    assert out[limit:]==raw[limit:]
    if source:assert out==raw,'Dialogue source roundtrip failed'
    for row in rows:
        p=struct.unpack_from('>I',out,20+4*row['index'])[0]*4
        expected=row['source'].encode('cp932') if source else encode(row['translation'],mapping)
        assert out[p:out.index(0,p)]==expected
    return bytes(out),{'rows':count,'text_capacity':limit-pos,'text_used':len(region),'event_count':events,'event_offset':eoff*4 if events else None,'opaque_tail_offset':limit,'event_bytes_preserved':True}


def relocations(raw):
    io,size=struct.unpack_from('>II',raw,0x28)
    for p in range(io,io+size,8):
        module,pos=struct.unpack_from('>II',raw,p);section=None;loc=0
        while True:
            delta,kind,target,addend=struct.unpack_from('>HBBI',raw,pos);loc+=delta
            if kind==202:section=target;loc=0
            elif kind==203:break
            elif kind not in [0,201]:yield dict(record=pos,module=module,section=section,offset=loc,type=kind,target=target,addend=addend)
            pos+=8


def rel_sections(raw):
    n,start=struct.unpack_from('>II',raw,12)
    return [(p&~3,size) for p,size in [struct.unpack_from('>II',raw,start+8*i) for i in range(n)]]


def link_rel(raw,base=0x80500000):
    out=bytearray(raw);sections=rel_sections(raw);module=struct.unpack_from('>I',raw,0)[0]
    for r in relocations(raw):
        pos=sections[r['section']][0]+r['offset']
        assert r['module'] in (0,module)
        value=r['addend'] if r['module']==0 else base+sections[r['target']][0]+r['addend']
        if r['type']==1:struct.pack_into('>I',out,pos,value)
        elif r['type']==4:struct.pack_into('>H',out,pos,value&65535)
        elif r['type']==6:struct.pack_into('>H',out,pos,((value+0x8000)>>16)&65535)
        elif r['type']==10:
            disp=value-(base+pos);assert -(1<<25)<=disp<(1<<25) and disp%4==0
            old=struct.unpack_from('>I',raw,pos)[0];struct.pack_into('>I',out,pos,(old&0xfc000003)|(disp&0x3fffffc))
        else:raise ValueError(r)
    return bytes(out),sections


def credits(raw,rows,mapping,source=False):
    rows=sorted(rows,key=lambda r:r['offset']);start=rows[0]['offset'];end=rows[-1]['offset']+rows[-1]['byte_length']+1
    out=bytearray(raw);packed=bytearray();positions={}
    for row in rows:
        positions[row['offset']]=start+len(packed)
        packed.extend((row['source'].encode('ascii') if source else encode(row['translation'],mapping))+b'\0')
    assert len(packed)<=end-start
    out[start:end]=packed+b'\0'*(end-start-len(packed))
    sections=rel_sections(raw);target=next(i for i,(p,n) in enumerate(sections) if p<=start<end<=p+n)
    module=struct.unpack_from('>I',raw,0)[0];refs=[]
    for r in relocations(raw):
        old=sections[target][0]+r['addend']
        if r['module']==module and r['target']==target and start<=old<end:
            assert old in positions and r['type']==1,'Unexpected interior/non-pointer credit reference'
            struct.pack_into('>I',out,r['record']+4,positions[old]-sections[target][0]);refs.append((r,old))
    assert len(refs)==len(rows)==45
    assert {old for _,old in refs}==set(positions)
    linked,_=link_rel(bytes(out));base=0x80500000
    for r,old in refs:
        at=sections[r['section']][0]+r['offset'];pointer=struct.unpack_from('>I',linked,at)[0]-base
        row=next(r for r in rows if r['offset']==old)
        expected=row['source'].encode('ascii') if source else encode(row['translation'],mapping)
        assert linked[pointer:linked.index(0,pointer)]==expected
    allowed=set(range(start,end))
    for r,_ in refs:allowed.update(range(r['record']+4,r['record']+8))
    assert all(i in allowed or a==b for i,(a,b) in enumerate(zip(raw,out)))
    if source:assert out==raw,'Credits source roundtrip failed'
    return bytes(out),{'rows':45,'capacity':end-start,'used_bytes':len(packed),'updated_relocation_addends':len(refs),'linked_pointer_readback':'pass','outside_text_and_addends':'unchanged'}
