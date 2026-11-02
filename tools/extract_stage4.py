"""Read-only JP/US extraction with embedded TPL and structured dialogue support.

Game binaries/pixels/candidate scans stay in ignored work/. Translation sources
and provenance inventories are tracked; existing translations are preserved.
No ISO, modified DOL, patched archive or translated graphics are produced.
"""
import collections
import hashlib
import json
import re
import struct
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from inspect_discs import ROOT, INPUTS, save
from verify_asset_roundtrip import FORMATS, BLOCKS
from decode_gx import decode

OUT=ROOT/'work/extraction'
MAGIC=bytes.fromhex('0020af30')
def sha(b):return hashlib.sha256(b).hexdigest()
def rel(p):return p.relative_to(ROOT).as_posix()
def readj(p):return json.loads(p.read_text(encoding='utf8'))


def tagged_tokens(s):
    result=[];pos=0
    while pos<len(s):
        if s[pos]!='@':pos+=1;continue
        assert pos+1<len(s)
        tag=s[pos+1];length=6 if tag=='C' else 2
        assert tag in 'CPNRGB0S_' and pos+length<=len(s),(pos,s[pos:pos+8])
        result.append(s[pos:pos+length]);pos+=length
    return result


def dialogue(raw,path,member):
    assert raw[:4]==b'0827'
    count,stride,events,event_offset=struct.unpack_from('>4I',raw,4)
    assert stride==5 and 20+4*count<=len(raw)
    starts=[4*n for n in struct.unpack_from(f'>{count}I',raw,20)]
    assert starts==sorted(set(starts))
    if starts:assert starts[0]==20+4*count
    rows=[];rebuilt=bytearray(raw)
    struct.pack_into('>4I',rebuilt,4,count,stride,events,event_offset)
    for i,start in enumerate(starts):
        end=raw.index(0,start);assert end<(starts[i+1] if i+1<count else len(raw))
        b=raw[start:end];s=b.decode('cp932');assert s.encode('cp932')==b
        rows.append({'id':f'rsc/{Path(path).stem}/{member:03}/{i:03}','file':path,
                     'member':member,'index':i,'offset':start,'byte_length':len(b),
                     'source':s,'translation':'','speaker':None,'renderer':'tagged',
                     'tags':tagged_tokens(s),'speaker_note':'Not stored in this string table; do not infer identity from pronouns.'})
        struct.pack_into('>I',rebuilt,20+4*i,start//4)
        rebuilt[start:end+1]=s.encode('cp932')+b'\0'
    assert rebuilt==raw
    return rows,{'file':path,'member':member,'count':count,'event_count':events,
                 'event_offset_words':event_offset,'sha256':sha(raw),'structured_string_roundtrip':True,
                 'scope':'Header/pointers/text serialized; event bytes and padding preserved opaque.'}


def texture(raw,start,path,member,kind,region,cache):
    magic,count,table=struct.unpack_from('>3I',raw,start)
    assert magic==0x0020af30 and 0<count<10000 and start+table+8*count<=len(raw)
    records=[]
    for index in range(count):
        ih,ph=struct.unpack_from('>II',raw,start+table+8*index);ih+=start
        assert ih+36<=len(raw)
        h,w,fmt,data=struct.unpack_from('>HHII',raw,ih);data+=start
        assert 0<w<=2048 and 0<h<=2048 and fmt in (0,1,2,3,5,6,14) and ph==0
        bw,bh,bs=BLOCKS[fmt];levels=[];pos=data;lw=w;lh=h
        for lod in range(raw[ih+34]+1):
            size=((lw+bw-1)//bw)*((lh+bh-1)//bh)*bs
            assert pos+size<=len(raw),(path,member,index,lod)
            b=raw[pos:pos+size];digest=sha(b)
            key=sha(struct.pack('>III',fmt,lw,lh)+b)
            png=OUT/'texture_objects'/f'{key}.png'
            if key not in cache:
                im=decode(b,lw,lh,fmt);png.parent.mkdir(parents=True,exist_ok=True);im.save(png)
                with Image.open(png) as reread:
                    assert reread.size==(lw,lh) and reread.mode=='RGBA' and reread.tobytes()==im.tobytes()
                cache[key]=sha(im.tobytes())
            levels.append({'lod':lod,'width':lw,'height':lh,'payload_offset':pos,
                           'size':size,'encoded_sha256':digest,'rgba_sha256':cache[key],'png':rel(png)})
            pos+=size;lw=max(1,lw//2);lh=max(1,lh//2)
        records.append({'id':f"{region}/{path}/{member:03}/{start:08x}/{index:03}",
                        'region':region,'file':path,'member':member,'member_type':kind,
                        'tpl_offset':start,'texture':index,'format':FORMATS[fmt],
                        'width':w,'height':h,'min_lod':raw[ih+33],'max_lod':raw[ih+34],
                        'levels':levels,'visual_classification':'unreviewed',
                        'roundtrip':'PNG save/reload pixel equality; no texture recompression claim'})
    return records


def banner(raw):
    assert raw[:4]==b'BNR1' and len(raw)==0x1960
    names=['short_title','short_maker','long_title','long_maker','description'];sizes=[32,32,64,64,128]
    rows=[];p=0x1820;rebuilt=bytearray(raw)
    for name,size in zip(names,sizes):
        part=raw[p:p+size];end=part.index(0);text=part[:end].decode('cp932')
        assert text.encode('cp932')==part[:end]
        rows.append({'id':'banner/'+name,'file':'opening.bnr','offset':p,'field_size':size,
                     'byte_length':end,'source':text,'translation':'','speaker':None,'renderer':'system_banner'})
        rebuilt[p:p+end+1]=text.encode('cp932')+b'\0';p+=size
    assert rebuilt==raw
    return rows


def credits(raw,path):
    start=raw.index(b'WARIO WORLD STAFF CREDITS\0');end=raw.index(b'reserved by NINTENDO.\0',start)+len(b'reserved by NINTENDO.\0')
    rows=[];p=start;rebuilt=bytearray(raw)
    while p<end:
        stop=raw.index(0,p,end);text=raw[p:stop].decode('ascii')
        rows.append({'id':f'credits/{len(rows):03}','file':path,'offset':p,'byte_length':stop-p,
                     'source':text,'translation':'','speaker':None,'renderer':'credits_pending',
                     'note':'Staff names/copyright also inventoried; localization policy not approved.'})
        rebuilt[p:stop+1]=text.encode('ascii')+b'\0';p=stop+1
    assert rebuilt==raw
    return rows


def candidates(raw,path,covered):
    result=[]
    patterns=[('cp932',rb'(?:[\x20-\x7e]|[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]){6,}'),
              ('ascii',rb'[\x20-\x7e]{6,}')]
    for enc,pattern in patterns:
        for m in re.finditer(pattern,raw):
            if any(a<=m.start() and m.end()<=z for a,z in covered):continue
            try:s=m.group().decode(enc)
            except UnicodeDecodeError:continue
            if enc=='cp932':
                kana=sum('\u3040'<=c<='\u30ff' for c in s)
                if kana<3 or kana<len(s)*.25:continue
            elif not re.search(r'[A-Za-z]{4}',s):continue
            result.append({'file':path,'offset':m.start(),'encoding':enc,'text':s,
                           'classification':'candidate_only; binary false positives expected'})
    return result


def sheets(records):
    chosen={}
    for r in records:
        if r['region']=='jp':chosen.setdefault(r['levels'][0]['png'],r)
    # Independent textures/UI first, then embedded model and other textures.
    unique=sorted(chosen.values(),key=lambda r:(r['member_type']!=1,r['file'],r['member'],r['texture']))
    pages=[];font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',12)
    for n in range(0,len(unique),64):
        page=Image.new('RGB',(1280,1280),(65,65,65));draw=ImageDraw.Draw(page)
        rows=[]
        for j,r in enumerate(unique[n:n+64]):
            x=(j%8)*160;y=(j//8)*160
            im=Image.open(ROOT/r['levels'][0]['png']).convert('RGBA');im.thumbnail((152,128))
            # Contact-sheet compositing only; extracted native PNG is untouched.
            bg=Image.new('RGBA',im.size,(150,150,150,255));bg.alpha_composite(im)
            page.paste(bg.convert('RGB'),(x+(160-im.width)//2,y+(130-im.height)//2))
            label=f'{n+j:04} {Path(r["file"]).stem}/{r["member"]}/{r["texture"]}'
            draw.text((x+2,y+132),label,font=font,fill='white');draw.text((x+2,y+146),f'{r["width"]}x{r["height"]} {r["format"]}',font=font,fill='white')
            rows.append({'number':n+j,'asset_id':r['id'],'png':r['levels'][0]['png']})
        dest=OUT/'sheets'/f'jp-{n//64:02}.jpg';dest.parent.mkdir(parents=True,exist_ok=True);page.save(dest,quality=94)
        pages.append({'sheet':rel(dest),'items':rows})
    save(OUT/'sheets/index.json',pages)
    return pages


def main():
    cache={};alltex=[];regions={};raw_inventory=[];unclassified=[];roundtrips=[]
    archives=readj(ROOT/'metadata/rsc_inventory.json')['editions']
    for region,filename in INPUTS:
        inv=readj(ROOT/f'metadata/disc_inventory_{region}.json')
        rows=readj(ROOT/f'work/analysis/{region}/confirmed_messages.json')['messages']
        rows=[{**r,'renderer':'plain_at'} for r in rows]
        rs=next(e for e in archives if e['edition']==region)['archives']
        bypath={a['path']:a for a in rs};scan=[];sig=[]
        with (ROOT/filename).open('rb') as disc:
            sources=[{'path':'main.dol',**{k:inv['dol'][k] for k in ['offset','size','sha256']}}]+inv['files']
            for entry in sources:
                path=entry['path'];disc.seek(entry['offset']);raw=disc.read(entry['size']);assert sha(raw)==entry['sha256']
                dest=OUT/region/'files'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
                raw_inventory.append({'region':region,'file':path,'size':len(raw),'sha256':sha(raw),'extracted':rel(dest)})
                if path.endswith('.RSC'):
                    for member in bypath[path]['members']:
                        start=member['header_offset']+32;b=raw[start:start+member['size']]
                        assert sha(b)==member['sha256'];covered=[]
                        if member['type']==14:
                            new,rt=dialogue(b,path,member['index']);rows.extend(new);roundtrips.append({'region':region,**rt})
                            covered=[(r['offset'],r['offset']+r['byte_length']) for r in new]
                        p=0;tpls=0
                        while (p:=b.find(MAGIC,p))>=0:
                            alltex.extend(texture(b,p,path,member['index'],member['type'],region,cache));tpls+=1;p+=4
                        # Non-TPL types can contain both geometry and embedded TPL.
                        unclassified.append({'region':region,'file':path,'member':member['index'],'type':member['type'],
                                             'size':len(b),'sha256':sha(b),'embedded_tpls':tpls,
                                             'payload':'dialogue/event container' if member['type']==14 else ('TPL' if member['type']==1 else 'opaque beyond located TPLs'),
                                             'extracted':f'work/roundtrip/{region}/{path}/{member["index"]:03}.bin'})
                        if region=='jp':scan.extend(candidates(b,f'{path}::{member["index"]}',covered))
                elif path=='opening.bnr':
                    rows.extend(banner(raw));im=decode(raw[0x20:0x1820],96,32,5)
                    im.save(OUT/region/'banner.png')
                elif path.endswith('ED.rel'):rows.extend(credits(raw,path))
                if region=='jp' and not path.endswith('.RSC'):
                    covered=[(r['offset'],r['offset']+r['byte_length']) for r in rows if r['file']==path]
                    scan.extend(candidates(raw,path,covered))
                for magic,name in [(b'THP\0','THP'),(b'RETRO','unknown RETRO signature'),(b'\x89PNG\r\n\x1a\n','PNG'),(b'\xff\xd8\xff','JPEG')]:
                    start=0
                    while (start:=raw.find(magic,start))>=0:
                        sig.append({'file':path,'offset':start,'signature':name,'validation':'signature candidate only'});start+=len(magic)
        # Check serialized source JSON by reading it back and comparing encoded source bytes.
        save(OUT/region/'messages.json',{'messages':rows})
        reread=readj(OUT/region/'messages.json')['messages']
        assert [(r['id'],r['source'].encode('cp932')) for r in rows]==[(r['id'],r['source'].encode('cp932')) for r in reread]
        regions[region]=rows
        save(OUT/region/'string_candidates.json',scan);save(OUT/region/'signature_candidates.json',sig)
        print(region,'messages',len(rows),'textures',sum(r['region']==region for r in alltex),'candidates',len(scan),flush=True)
    jp=regions['jp'];us={r['id']:r for r in regions['us']};target=ROOT/'translation/messages.json'
    existing={r['id']:r for r in readj(target)['messages']} if target.exists() else {}
    for row in jp:
        if row['id'].startswith('credits/'):
            match=next((r for r in regions['us'] if r['id'].startswith('credits/') and r['source']==row['source']),None)
            row['english_reference']=match['source'] if match else None
            row['alignment']='exact source text match in credits; indices differ across regions'
        else:
            row['english_reference']=us.get(row['id'],{}).get('source')
            row['alignment']='same structural ID; semantic correspondence pending review'
        if row['id'] in existing:
            old=existing[row['id']];assert old['source']==row['source']
            row['translation']=old.get('translation','');row['speaker']=old.get('speaker')
    assert not (set(existing)-{r['id'] for r in jp}), 'Do not discard existing rows'
    save(target,{'source_language':'Japanese edition (English credits/banner preserved as found)',
                 'full_game_coverage':False,'messages':jp})
    pages=sheets(alltex)
    # Cross-edition counterpart by exact container identity, including nested offset.
    bykey={(r['region'],r['file'],r['member'],r['tpl_offset'],r['texture']):r for r in alltex}
    for r in alltex:
        other=bykey.get(('us' if r['region']=='jp' else 'jp',r['file'],r['member'],r['tpl_offset'],r['texture']))
        r['other_region_exact_key_match']=other['id'] if other else None
        r['same_base_pixels_as_other_region']=r['levels'][0]['rgba_sha256']==other['levels'][0]['rgba_sha256'] if other else None
    previous=ROOT/'metadata/extraction_inventory.json'
    if previous.exists():
        prior={r['id']:r for r in readj(previous)['textures']}
        for r in alltex:
            old=prior.get(r['id'],{})
            for key in ['visual_classification','visual_note','review_evidence','localization_proposal']:
                if key in old and old.get('levels',[{}])[0].get('rgba_sha256')==r['levels'][0]['rgba_sha256']:r[key]=old[key]
    save(previous,{'files':raw_inventory,'members':unclassified,'textures':alltex,'dialogue_roundtrips':roundtrips,
         'contact_sheet_index':rel(OUT/'sheets/index.json'),'unique_decoded_levels':len(cache),
         'scope':'All FST files plus main DOL in both editions; every validated TPL magic within every RSC payload. Opaque geometry/effect/event payloads are not fully interpreted.'})
    print('unique PNG levels',len(cache),'JP contact sheets',len(pages),flush=True)


if __name__=='__main__':main()
