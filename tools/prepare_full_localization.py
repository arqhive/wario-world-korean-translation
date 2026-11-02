"""Prepare/test full localized components in RAM. Writes JSON/PNG evidence only.
No translated DOL, REL, RSC or ISO is saved. A future builder must obtain a new
explicit build instruction and select validated components from this recipe.
"""
import collections
import json
import struct
import numpy as np
from PIL import Image
from inspect_discs import ROOT, save
from inspect_rsc import parse
from research_code import offset
from decode_gx import decode
from encode_gx_localized import encode_changed
from full_text_components import main_table,dialogue,credits,link_rel
from prepare_full_font import prepare as prepare_font,encode,BASE,WRAPPER
import prepare_output_probe as probe


def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))


def prepare(font_weight='medium',include_alnum=False,include_symbols=False,lower_question_exclamation=False):
    f=prepare_font(font_weight,include_alnum,include_symbols,lower_question_exclamation);raw=f['raw'];sections=f['sections'];rows=f['rows'];mapping=f['mapping'];payload=f['payload']
    inv=read('metadata/disc_inventory_jp.json');manifest={r['path']:r for r in inv['files']}
    folder=ROOT/'work/full-localization';folder.mkdir(parents=True,exist_ok=True)
    originals={};modified={};ranges=collections.defaultdict(list);report={'font':'metadata/full_font_preparation.json','font_weight':font_weight,'gmarket_alnum':include_alnum,'gmarket_symbols':include_symbols,'lower_question_exclamation':lower_question_exclamation,'translation_sha256':f['report']['translation_sha256'],'components':[]}
    def original(path):
        if path not in originals:
            b=(ROOT/'work/extraction/jp/files'/path).read_bytes();assert probe.sha(b)==manifest[path]['sha256'];originals[path]=b;modified[path]=bytearray(b)
        return originals[path]
    main_table(raw,sections,rows,mapping,True)
    dol,stats=main_table(raw,sections,rows,mapping);dol=bytearray(dol)
    report['components'].append({'kind':'main_text',**stats,'source_roundtrip':'byte_exact'})
    assert all(probe.u32(raw,p)==0 for p in (8,0x50,0x98))
    file_offset=(len(dol)+31)&~31;dol.extend(b'\0'*(file_offset-len(dol)));dol.extend(payload)
    for p,v in [(8,file_offset),(0x50,BASE),(0x98,len(payload))]:struct.pack_into('>I',dol,p,v)
    allowed=[stats['range'],[8,12],[0x50,0x54],[0x98,0x9c]]
    for address,target,link,expected in [(0x8002ffbc,WRAPPER,True,0x4817089d),(0x8019ee48,BASE,False,0x906d8178)]:
        p=offset(sections,address);assert probe.u32(raw,p)==expected
        a=probe.PPC(address);a.branch(target,link);dol[p:p+4]=a.finish();allowed.append([p,p+4])
    changed=np.frombuffer(raw,dtype=np.uint8)!=np.frombuffer(bytes(dol[:len(raw)]),dtype=np.uint8)
    mask=np.zeros(len(raw),bool)
    for a,b in allowed:mask[a:b]=True
    assert not np.any(changed&~mask)
    cpu=probe.machine(bytes(dol),sections,payload,f['compressed'])
    assert probe.run(cpu,0x8019ee48,(BASE,))==BASE+len(payload)
    cpu.reg_write(probe.reg(1),probe.STACK);cpu.reg_write(probe.reg(3),probe.FONT_RAM);cpu.reg_write(probe.reg(4),probe.COMP_RAM)
    cpu.emu_start(0x8002ffbc,0x8002ffc0,count=20000000)
    assert bytes(cpu.mem_read(probe.FONT_RAM,len(f['patched_font'])))==f['patched_font']
    probe.run(cpu,0x80062004)
    for row in rows:
        if not row['id'].startswith('main/'):continue
        group,index=map(int,row['id'].split('/')[1:]);array=probe.u32(cpu.mem_read(0x801bf5e4+group*4,4),0);p=probe.u32(cpu.mem_read(array+index*4,4),0)
        expected=encode(row['translation'],mapping)+b'\0';assert bytes(cpu.mem_read(p,len(expected)))==expected
    report['main_cpu_initializer_verified_rows']=269
    report['dol']={'in_memory_sha256':probe.sha(dol),'size':len(dol),'original_bytes_outside_allowed_ranges':'unchanged','allowed_original_ranges':allowed,'font_section_size':len(payload)}
    # Stay inside existing RSC member allocations and preserve opaque tails/wrappers.
    for path,member in sorted({(r['file'],r['member']) for r in rows if r['id'].startswith('rsc/')}):
        b=original(path);entry=parse(b)[member];p=entry['header_offset']+32;src=b[p:p+entry['size']]
        rs=[r for r in rows if r['file']==path and r.get('member')==member]
        dialogue(src,rs,mapping,True);value,stats=dialogue(src,rs,mapping)
        modified[path][p:p+len(value)]=value;ranges[path].append([p,p+len(value)])
        report['components'].append({'kind':'tagged_dialogue','file':path,'member':member,'source_roundtrip':'byte_exact',**stats})
    rs=[r for r in rows if r['id'].startswith('credits/')];path=rs[0]['file'];b=original(path)
    credits(b,rs,mapping,True);value,stats=credits(b,rs,mapping);modified[path][:]=value
    # credits() independently restricts differences to its string region/addends.
    ranges[path].extend([[i,i+1] for i,(a,z) in enumerate(zip(b,value)) if a!=z])
    report['components'].append({'kind':'credits','file':path,'source_roundtrip':'byte_exact',**stats,
        'renderer_evidence':'JP ED REL constructor offset0x8c58 calls DOL0x8007ecc0/0x8007ee74; latter uses OS font width0x801a0e90 and glyph0x801a0b8c. Static call-chain verification; no ending playback.'})
    # System viewers cannot use our in-game font mapping. Keep their fields exact.
    report['external_viewer_text']={'policy':'original_bytes_preserved','ids':[r['id'] for r in rows if r['id'].startswith(('save/','banner/'))],
        'reason':'Game font patch is not available to external GameCube/Dolphin banner and memory-card viewers. Do not write mapped Hangul as Japanese kanji metadata.'}
    # Encode graphics at their original format and original member positions.
    tex=read('metadata/extraction_inventory.json')['textures'];assets=read('translation/graphics.json')['items']
    states=next(a for a in read('project.json')['assets'] if a['id']=='graphics-localization')['items']
    for item in assets:
        if item['action']!='replace_japanese_only':continue
        state=next(s for s in states if s['id']==item['key']);img=Image.open(ROOT/state['approved_path']).convert('RGBA')
        assert probe.sha((ROOT/state['approved_path']).read_bytes())==state['approved_sha256']
        for ref in item['references']:
            if ref['region']!='jp':continue
            path=ref['file'];b=original(path)
            if item['key']=='banner':p=32;length=6144;fmt=5;w=96;h=32
            else:
                t=next(t for t in tex if t['id']==ref['id']);assert len(t['levels'])==1
                e=parse(b)[ref['member']];p=e['header_offset']+32+t['levels'][0]['payload_offset'];length=t['levels'][0]['size'];fmt={'RGB5A3':5,'RGBA8':6}[t['format']];w=t['width'];h=t['height']
            src=b[p:p+length];original_image=decode(src,w,h,fmt)
            roundtrip,_,_=encode_changed(src,w,h,fmt,original_image,force_all=True);assert roundtrip==src
            value,decoded,stats=encode_changed(src,w,h,fmt,img);assert len(value)==length
            modified[path][p:p+length]=value;ranges[path].append([p,p+length])
            decoded.save(folder/(item['key']+'-encoded-preview.png'))
            # Encoding may quantize edits, but all PNG-mask-exterior pixels remain exact.
            mask=np.array(Image.open(ROOT/state['mask']))>0
            assert not np.any(np.array(decoded)[~mask]!=np.array(original_image)[~mask])
            report['components'].append({'kind':'graphics','id':item['key'],'file':path,'offset':p,'length':length,'format':fmt,
                'source_roundtrip':'byte_exact_using_original_RGB5A3_selector_and_padding_metadata',
                'outside_approved_png_mask_differences':0,**stats})
    for path,b in modified.items():
        original_bytes=originals[path];assert len(b)==len(original_bytes)
        mask=np.zeros(len(b),bool)
        for a,z in ranges[path]:mask[a:z]=True
        diff=np.frombuffer(original_bytes,dtype=np.uint8)!=np.frombuffer(bytes(b),dtype=np.uint8);assert not np.any(diff&~mask)
        if path.endswith('.RSC'):
            before=parse(original_bytes);after=parse(bytes(b))
            assert [{k:v for k,v in e.items() if k not in ('sha256','magic_hex')} for e in before]==[{k:v for k,v in e.items() if k not in ('sha256','magic_hex')} for e in after]
        if path=='opening.bnr':assert b[0x1820:]==original_bytes[0x1820:]
    # Read the prospective DOL disc range, validating no FST/system overlap.
    protected=[(0,inv['dol']['offset']+inv['dol']['size']),(inv['fst_offset'],inv['fst_offset']+inv['fst_size'])]+[(x['offset'],x['offset']+x['size']) for x in inv['files']]
    assert all(probe.DISC_DOL_OFFSET>=z or probe.DISC_DOL_OFFSET+len(dol)<=a for a,z in protected)
    with (ROOT/'Wario World (Japan).iso').open('rb') as disc:
        disc.seek(probe.DISC_DOL_OFFSET);filler=disc.read(len(dol))
    assert len(filler)==len(dol)
    report['prospective_dol_disc_range']={'offset':probe.DISC_DOL_OFFSET,'length':len(dol),'original_range_sha256':probe.sha(filler),'outside_FST_and_system_ranges':True}
    # Real OS width lookup for every translated character; common layout routine for main/credits.
    text_ram=0x81000000;result_ram=0x81010000;widths={};measurements=[]
    for char in sorted({c for r in rows for c in r['translation']} - set('\r\n@')):
        value=encode(char,mapping);cpu.mem_write(text_ram,value+b'\0');assert probe.run(cpu,0x801a0e90,(text_ram,result_ram))==text_ram+len(value)
        widths[char]=probe.u32(cpu.mem_read(result_ram,4),0)
    for row in rows:
        if not row['id'].startswith(('main/','credits/')):continue
        text=row['translation'];cpu.mem_write(text_ram,encode(text,mapping)+b'\0')
        probe.run(cpu,0x8007f0f4,(0,text_ram,result_ram,result_ram+4));actual=struct.unpack('>II',cpu.mem_read(result_ram,8))
        line_widths=[sum(widths[c] for c in line) for line in text.split('@')]
        expected=(((max(24,max(line_widths))+23)//24)*24,len(line_widths)*24);assert actual==expected
        measurements.append({'id':row['id'],'line_widths_px':line_widths,'texture_size_px':list(actual),'screen_fit':'unverified'})
    save(ROOT/'metadata/full_text_measurements.json',{'translation_sha256':f['report']['translation_sha256'],'font_payload_sha256':f['report']['payload_sha256'],'widths_px':widths,'messages':measurements,'note':'Actual font and common layout CPU measurements; not screen capacity limits. Tagged scenes need their own parser/layout validation.'})
    report['common_layout_cpu_verified_rows']=len(measurements)
    report['files']=[{'file':p,'size':len(b),'original_sha256':probe.sha(originals[p]),'prepared_sha256':probe.sha(b),'outside_component_ranges':'unchanged'} for p,b in sorted(modified.items())]
    report['mode']='In-memory preparation only; no patched DOL/REL/RSC/ISO written'
    report['limitations']=['Whole-game boot and scene rendering not tested.','External-viewer save/banner text remains original; Korean banner image is prepared.',
        'Credits call chain and relocation verified; no ending playback.','Tagged event bytes and pointers verified; full tagged renderer/GPU execution not tested.',
        'Screen limits and layout overflow remain unverified.']
    save(ROOT/'metadata/full_localization_preparation.json',report)
    return {'dol':bytes(dol),'files':{p:bytes(b) for p,b in modified.items()},'report':report}


if __name__=='__main__':
    result=prepare();print(json.dumps(result['report'],ensure_ascii=False,indent=2))
