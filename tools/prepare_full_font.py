"""Prepare the complete Korean font in memory; never modifies the probe or ISO."""
import itertools
import string
import math
import json
import struct
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
from inspect_discs import ROOT, save
from research_code import load, offset
import prepare_output_probe as probe

BASE=probe.NEW_BASE
WRAPPER=BASE+0x40
RECORDS=BASE+0x400


def code_map(rows,raw):
    used=set()
    for data in [raw]+[p.read_bytes() for p in (ROOT/'work/extraction/jp/files/dll').glob('*.rel')]:
        a=np.frombuffer(data,dtype=np.uint8).astype(np.uint16)
        used.update(((a[:-1]<<8)|a[1:]).tolist())
    for row in rows:
        data=row['source'].encode('cp932')
        used.update(int.from_bytes(data[i:i+2],'big') for i in range(len(data)-1))
    chars=sorted({c for r in rows for c in r['translation'] if '\uac00'<=c<='\ud7a3'})
    available=[c for c in range(0x889f,0x9873) if 0x40<=(c&255)<=0xfc and c&255!=0x7f and c not in used]
    assert len(available)>=len(chars)
    return dict(zip(chars,available[-len(chars):])),len(available)


def encode(text,mapping):
    return b''.join(mapping[c].to_bytes(2,'big') if c in mapping else c.encode('cp932') for c in text)


def make_payload(records):
    # Consecutive destination bytes share a run header; no 16-bit byte-count limit.
    runs=[]
    for _,group in itertools.groupby(enumerate(sorted(records)),lambda pair:pair[1]-pair[0]):
        addresses=[a for _,a in group]
        runs.append((addresses[0],bytes(records[a] for a in addresses)))
    packed=bytearray()
    for address,data in runs:
        packed.extend(struct.pack('>II',address,len(data))+data)
        packed.extend(b'\0'*(-len(packed)%4))
    reserve=(0x400+len(packed)+31)&~31
    a=probe.PPC(BASE);a.load32(0,BASE+reserve);a.emit(0x7c030040)
    a.cond(0x40800000,'store');a.load32(3,BASE+reserve)
    a.label('store');a.d(36,3,13,-0x7e88);a.emit(0x4e800020);arena=a.finish()
    a=probe.PPC(WRAPPER)
    a.d(37,1,1,-32);a.emit(0x7c0802a6);a.d(36,0,1,36)
    a.branch(0x801a0858,True);a.d(36,3,1,8)
    a.d(11,0,3,0);a.cond(0x41820000,'return');a.d(32,6,13,-0x7778)
    guards={0x10:0x00180018,0x14:0x20000,0x18:0x00000015,0x1c:0x00150200,
            0x20:0x02000030,0x24:0xee4,0x28:0x120000,0x2c:0x0055aaff}
    for field,value in guards.items():
        a.d(32,7,6,field);a.load32(8,value);a.emit(31<<26|7<<16|8<<11|32<<1)
        a.cond(0x40820000,'return')
    a.load32(5,RECORDS);a.load32(10,len(runs))
    a.label('run');a.d(32,7,5,0);a.d(32,9,5,4);a.d(14,5,5,8)
    a.emit(31<<26|7<<21|6<<16|7<<11|266<<1);a.emit(0x7d2903a6)
    a.label('byte');a.d(34,8,5,0);a.d(38,8,7,0)
    a.d(14,5,5,1);a.d(14,7,7,1);a.cond(0x42000000,'byte')
    a.d(14,5,5,3);a.emit(0x54a5003a) # rlwinm r5,r5,0,0,29
    a.d(14,10,10,-1);a.d(11,0,10,0);a.cond(0x40820000,'run')
    a.label('return');a.d(32,3,1,8);a.d(32,0,1,36);a.emit(0x7c0803a6)
    a.d(14,1,1,32);a.emit(0x4e800020);wrapper=a.finish()
    assert len(arena)<=0x40 and len(wrapper)<=0x3c0
    payload=bytearray(reserve);payload[:len(arena)]=arena;payload[0x40:0x40+len(wrapper)]=wrapper;payload[0x400:0x400+len(packed)]=packed
    return bytes(payload),guards,len(runs)


def prepare(weight='medium',include_alnum=False,include_symbols=False,lower_question_exclamation=False):
    assert not lower_question_exclamation or include_symbols
    assert weight in ('medium','bold')
    font_path=ROOT/'work/references/gmarket'/f'GmarketSans{weight.title()}.otf'
    raw,sections=load('jp');inv=json.loads((ROOT/'metadata/disc_inventory_jp.json').read_text(encoding='utf-8'))
    assert probe.sha(raw)==inv['dol']['sha256']
    rows=json.loads((ROOT/'translation/messages.json').read_text(encoding='utf-8'))['messages']
    compressed=probe.FONT_FIXTURE.read_bytes()
    baseline=probe.machine(raw,sections,b'\0'*0x400,compressed)
    decoded=original=probe.yay0(compressed)
    assert probe.run(baseline,0x801a0858,(probe.FONT_RAM,probe.COMP_RAM))==len(original)
    original=bytes(baseline.mem_read(probe.FONT_RAM,len(original)))
    mapping,free=code_map(rows,raw);records={};bitmaps={};advances={};indices={}
    glyph_codes=dict(mapping);latin_details={};symbol_details={};symbol_chars=set();unsupported_symbols=[]
    if include_alnum:
        ascii_chars=string.digits+string.ascii_uppercase+string.ascii_lowercase
        for c in ascii_chars+''.join(chr(ord(c)+0xfee0) for c in ascii_chars):
            glyph_codes[c]=int.from_bytes(c.encode('cp932'),'big')
    if include_symbols:
        # Keep the control/delimiter glyphs and whitespace untouched. Text bytes
        # and parser behavior are never changed by this font option.
        symbol_chars=set(string.punctuation)-set('@#')
        for char in list(symbol_chars):
            full=chr(ord(char)+0xfee0)
            try:full.encode('cp932')
            except UnicodeEncodeError:continue
            symbol_chars.add(full)
        symbol_chars.update('…「」')
        for char in sorted(symbol_chars):
            code=int.from_bytes(char.encode('cp932'),'big')
            if probe.run(baseline,0x801a0464,(code,))==0:
                # CP932 extension quotes map to the missing-glyph slot in this
                # game. Never replace that shared fallback cell.
                assert all(char not in row['translation'] for row in rows)
                unsupported_symbols.append(char)
                continue
            glyph_codes[char]=code
    cmap=TTFont(font_path).getBestCmap()
    font=ImageFont.truetype(str(font_path),20)
    for char,code in glyph_codes.items():
        index=probe.run(baseline,0x801a0464,(code,));indices[char]=index
        if char in mapping:
            assert index==probe.glyph_index(code)
            bitmap=probe.glyph_bitmap(char,font_path=font_path);advance=20
        else:
            fullwidth=0xff01<=ord(char)<=0xff5e;display=chr(ord(char)-0xfee0) if fullwidth else char
            assert ord(display) in cmap, f'Missing Gmarket glyph: {display}'
            box=font.getbbox(display,anchor='ls');natural=font.getlength(display)
            left=max(0,-box[0]);ink_width=box[2]+left
            advance=24 if fullwidth else max(math.ceil(natural)+left,ink_width)
            x=(24-ink_width)//2+left if fullwidth else left
            glyph_baseline=18 if lower_question_exclamation and display in '!?' else 17
            assert 0<=x+box[0] and x+box[2]<=24 and 0<=glyph_baseline+box[1]<glyph_baseline+box[3]<=24
            bitmap=Image.new('L',(24,24),0)
            ImageDraw.Draw(bitmap).text((x,glyph_baseline),display,font=font,anchor='ls',fill=255)
            bitmap=bitmap.point(lambda v:(v//64)*85)
            assert bitmap.getbbox() is not None
            details=symbol_details if char in symbol_chars else latin_details
            details[char]={'code':f'{code:X}','index':index,'original_width':original[0x30+index],'width':advance,'baseline':glyph_baseline,'fullwidth':fullwidth}
        bitmaps[char]=bitmap;advances[char]=advance
        for y in range(24):
            for x in range(24):
                address,shift=probe.glyph_address(index,x,y)
                records[address]=records.get(address,0)|((bitmap.getpixel((x,y))//85)<<shift)
        records[0x30+index]=advance
    assert len(set(indices.values()))==len(indices),'Overlapping glyph indices'
    payload,guards,run_count=make_payload(records)
    assert BASE>=probe.u32(raw,0xd8)+probe.u32(raw,0xdc)
    assert all(BASE>=s['ram_address']+s['size'] or BASE+len(payload)<=s['ram_address'] for s in sections)
    assert all(probe.u32(decoded,k)==v for k,v in guards.items())
    cpu=probe.machine(raw,sections,payload,compressed)
    sentinels={i:0xabc00000+i for i in range(14,32)}
    for i,v in sentinels.items():cpu.reg_write(probe.reg(i),v)
    assert probe.run(cpu,WRAPPER,(probe.FONT_RAM,probe.COMP_RAM))==len(original)
    assert all(cpu.reg_read(probe.reg(i))==v for i,v in sentinels.items())
    patched=bytes(cpu.mem_read(probe.FONT_RAM,len(original)))
    expected=bytearray(original)
    for address,value in records.items():expected[address]=value
    assert patched==expected
    arena=[]
    for old in [0x802132f0,BASE,BASE+len(payload),0x80280000]:
        new=probe.run(cpu,BASE,(old,));assert new==max(old,BASE+len(payload));arena.append([old,new])
    bad=probe.machine(raw,sections,payload,compressed)
    malformed=bytearray(original);struct.pack_into('>I',malformed,0x10,0x00100010)
    bad.mem_write(probe.FONT_RAM,bytes(malformed));bad.mem_write(probe.R13-0x7778,struct.pack('>I',probe.FONT_RAM))
    fake=probe.PPC(0x801a0858);fake.load32(3,len(original));fake.emit(0x4e800020);bad.mem_write(0x801a0858,fake.finish())
    assert probe.run(bad,WRAPPER,(probe.FONT_RAM,probe.COMP_RAM))==len(original)
    assert bytes(bad.mem_read(probe.FONT_RAM,len(original)))==malformed
    text_ram=0x80a00000;dest=0x80a01000;width_ram=0x80a03000;widths={}
    # Execute original index, width, next-character and texture extraction for every glyph.
    for char,code in glyph_codes.items():
        assert probe.run(cpu,0x801a0464,(code,))==indices[char]
        encoded=encode(char,mapping);step=len(encoded)
        cpu.mem_write(text_ram,encoded+b'\0');cpu.mem_write(dest,b'\0'*512)
        assert probe.run(cpu,0x801a0b8c,(text_ram,dest,0,8,width_ram))==text_ram+step
        pic=probe.decode_i4(bytes(cpu.mem_read(dest,512)),32,32).crop((0,0,24,24))
        assert pic.tobytes()==bitmaps[char].tobytes()
        assert probe.run(cpu,0x801a0e90,(text_ram,width_ram))==text_ram+step
        widths[char]=probe.u32(cpu.mem_read(width_ram,4),0);assert widths[char]==advances[char]
    # Every used character outside the requested replacement set retains pixels/width.
    preserved=set(c for r in rows for c in r['translation'] if c not in glyph_codes and c not in '\r\n')
    for char in preserved:
        code=int.from_bytes(char.encode('cp932'),'big');index=probe.run(cpu,0x801a0464,(code,))
        for y in range(24):
            for x in range(24):
                address,shift=probe.glyph_address(index,x,y)
                assert ((original[address]>>shift)&3)==((patched[address]>>shift)&3)
        assert original[0x30+index]==patched[0x30+index]
    folder=ROOT/'work/full-localization';folder.mkdir(parents=True,exist_ok=True)
    sheet=Image.new('RGB',(24*24,((len(glyph_codes)+23)//24)*34+28),'#eeeeee');draw=ImageDraw.Draw(sheet)
    draw.text((4,5),f'{len(glyph_codes)} glyphs / CPU-verified / not a game screenshot',fill='black')
    for n,(char,im) in enumerate(bitmaps.items()):sheet.paste(Image.eval(im,lambda v:255-v),(n%24*24,n//24*34+28))
    sheet.save(folder/f'glyphs-{weight}{"-alnum" if include_alnum else ""}{"-symbols" if include_symbols else ""}{"-punct-down1" if lower_question_exclamation else ""}.png')
    report={'translation_sha256':probe.sha((ROOT/'translation/messages.json').read_bytes()),'font_sha256':probe.sha(font_path.read_bytes()),'font_weight':weight,'lower_question_exclamation':lower_question_exclamation,'font_path':str(font_path.relative_to(ROOT)),
            'glyph_count':len(mapping),'total_patched_glyph_count':len(glyph_codes),'alnum':latin_details,'symbols':symbol_details,'unsupported_unused_symbols_preserved':unsupported_symbols,'conservative_free_code_count':free,'mapping':{c:f'{v:04X}' for c,v in mapping.items()},
            'widths_px':widths,'payload_size':len(payload),'payload_sha256':probe.sha(payload),'run_count':run_count,
            'ram_start':hex(BASE),'ram_end':hex(BASE+len(payload)),'arena_cases':arena,
            'tests':{'all_glyph_pixels_widths_and_next_pointer':'pass','font_bytes_outside_records':'unchanged','nonvolatile_registers_stack':'preserved','header_guard':'pass','original_used_characters_outside_requested_set_preserved':len(preserved)},
            'limitations':['Unused codes exclude extracted source strings and all executable byte pairs, not unknown opaque text.',
                           'Original routines executed in CPU harness; IPL read uses local Dolphin fixture. No game boot or hardware proof.',
                           'Mapped glyphs exist inside the game only; external system banner/save viewers do not receive this font patch.']}
    save(ROOT/'metadata/full_font_preparation.json',report)
    return dict(raw=raw,sections=sections,rows=rows,mapping=mapping,payload=payload,report=report,compressed=compressed,patched_font=patched)


if __name__=='__main__':
    r=prepare();print(json.dumps({k:v for k,v in r['report'].items() if k not in ['mapping','widths_px']},ensure_ascii=False))
