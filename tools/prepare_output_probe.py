"""Prepare and CPU-test a JP output probe without writing a patched DOL/ISO.

Own PPC emitter and bitmap packing; original routines run inside Unicorn.
Dolphin's local free font is a read-only test fixture, never a patch payload.
"""
import hashlib
import json
import struct
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn import ppc_const as R
from inspect_discs import ROOT, save
from research_code import load, offset

FONT_FIXTURE=Path('C:/Users/hgyst/Desktop/Dolphin-x64/Sys/GC/font_japanese.bin')
FONT_TTF=ROOT/'work/references/gmarket/GmarketSansMedium.otf'
REFERENCE_TTF=ROOT/'work/references/droid/DroidSansFallback.ttf'
FONT_ADVANCE=20
FONT_BASELINE=18
NEW_BASE=0x80215300
RESERVE=0x4000
WRAPPER=NEW_BASE+0x40
RECORDS=NEW_BASE+0x400
DISC_DOL_OFFSET=0x00cd8000
R13=0x80206800
FONT_RAM=0x80800000       # CPU harness only, not a game allocation
COMP_RAM=0x80900000
STOP=0x81300000
STACK=0x813ff000
PROBE={'main/11/000':'확인할까요?', 'main/19/003':'시작@취소'}


def sha(data):return hashlib.sha256(data).hexdigest()
def reg(n):return getattr(R,f'UC_PPC_REG_{n}')
def u32(data,pos):return struct.unpack_from('>I',data,pos)[0]


def yay0(data):
    assert data[:4]==b'Yay0'
    size,links,chunks=struct.unpack_from('>3I',data,4)
    assert size==0x90ee4
    masks=16; bits=0; mask=0; out=bytearray()
    while len(out)<size:
        if not bits:
            mask=u32(data,masks);masks+=4;bits=32
        if mask&0x80000000:
            out.append(data[chunks]);chunks+=1
        else:
            link=struct.unpack_from('>H',data,links)[0];links+=2
            count=link>>12;distance=(link&4095)+1
            if count:count+=2
            else:count=data[chunks]+18;chunks+=1
            assert distance<=len(out) and len(out)+count<=size
            for _ in range(count):out.append(out[-distance])
        mask=(mask<<1)&0xffffffff;bits-=1
    return bytes(out)


def glyph_index(code):
    lo=(code&255)-0x40
    return ((code>>8)-0x88)*188+lo-(lo>=64)+0x2be


def glyph_address(index,x,y):
    sheet,cell=divmod(index,441)
    row,col=divmod(cell,21)
    x+=col*24;y+=row*24
    address=0xee4+sheet*65536+(y//8)*1024+(x//8)*16+(y%8)*2+(x%8)//4
    return address,6-2*(x%4)


def glyph_bitmap(char,font_path=FONT_TTF,baseline=FONT_BASELINE):
    font=ImageFont.truetype(str(font_path),20)
    bbox=font.getbbox(char,anchor='ls')
    assert 0<=bbox[0]<=bbox[2]<=24 and 0<=baseline+bbox[1]<baseline+bbox[3]<=24
    assert font.getlength(char)<=FONT_ADVANCE
    result=Image.new('L',(24,24),0)
    ImageDraw.Draw(result).text((0,baseline),char,font=font,anchor='ls',fill=255)
    result=result.point(lambda value:(value//64)*85)
    assert result.getbbox() is not None
    return result


class PPC:
    def __init__(self,base):self.base=base;self.words=[];self.labels={};self.fixups=[]
    @property
    def pc(self):return self.base+4*len(self.words)
    def emit(self,word):self.words.append(word)
    def d(self,op,rt,ra,imm):self.emit(op<<26|rt<<21|ra<<16|(imm&65535))
    def load32(self,rt,value):self.d(15,rt,0,value>>16);self.d(24,rt,rt,value&65535)
    def branch(self,target,link=False):
        disp=target-self.pc;assert -(1<<25)<=disp<(1<<25) and disp%4==0
        self.emit(0x48000000|(disp&0x03fffffc)|int(link))
    def cond(self,opcode,label):self.fixups.append((len(self.words),opcode,label));self.emit(0)
    def label(self,name):self.labels[name]=self.pc
    def finish(self):
        for index,op,label in self.fixups:
            disp=self.labels[label]-(self.base+index*4)
            assert -32768<=disp<32768 and disp%4==0
            self.words[index]=op|(disp&0xfffc)
        return struct.pack(f'>{len(self.words)}I',*self.words)


def build_payload(records):
    # Protect this new section from OS arena clearing and later heap allocation.
    a=PPC(NEW_BASE);a.load32(0,NEW_BASE+RESERVE)
    a.emit(0x7c030040)  # cmplw r3,r0
    a.cond(0x40800000,'store') # bge
    a.load32(3,NEW_BASE+RESERVE)
    a.label('store');a.d(36,3,13,-0x7e88);a.emit(0x4e800020)
    arena=a.finish();assert len(arena)<=0x40
    a=PPC(WRAPPER)
    a.d(37,1,1,-32);a.emit(0x7c0802a6);a.d(36,0,1,36)
    a.branch(0x801a0858,True);a.d(36,3,1,8)
    a.d(11,0,3,0);a.cond(0x41820000,'return')
    a.d(32,6,13,-0x7778)
    guards={0x10:0x00180018,0x14:0x20000,0x18:0x00000015,
            0x1c:0x00150200,0x20:0x02000030,0x24:0xee4,
            0x28:0x120000,0x2c:0x0055aaff}
    for field,value in guards.items():
        a.d(32,7,6,field);a.load32(8,value)
        a.emit(31<<26|7<<16|8<<11|32<<1) # cmplw r7,r8
        a.cond(0x40820000,'return')
    a.load32(5,RECORDS);a.d(14,9,0,len(records));a.emit(0x7d2903a6)
    a.label('loop');a.d(32,7,5,0);a.d(34,8,5,4)
    a.emit(31<<26|7<<21|6<<16|7<<11|266<<1) # add r7,r6,r7
    a.d(38,8,7,0);a.d(14,5,5,8);a.cond(0x42000000,'loop')
    a.label('return');a.d(32,3,1,8);a.d(32,0,1,36)
    a.emit(0x7c0803a6);a.d(14,1,1,32);a.emit(0x4e800020)
    wrapper=a.finish();assert len(wrapper)<=0x3c0
    payload=bytearray(RESERVE);payload[:len(arena)]=arena;payload[0x40:0x40+len(wrapper)]=wrapper
    record_data=b''.join(struct.pack('>IB3x',address,value) for address,value in sorted(records.items()))
    assert 0x400+len(record_data)<=len(payload)
    payload[0x400:0x400+len(record_data)]=record_data
    return bytes(payload),guards


def machine(raw,sections,payload,compressed):
    uc=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN)
    uc.mem_map(0x80000000,0x1800000)
    for s in sections:uc.mem_write(s['ram_address'],raw[s['file_offset']:s['file_offset']+s['size']])
    uc.mem_write(NEW_BASE,payload)
    uc.reg_write(reg(13),R13);uc.reg_write(reg(2),0x80207240)
    uc.mem_write(R13-0x7e78,b'\x00\x01')
    def rom_read(uc,addr,size,user):
        if addr!=0x801a07cc:return
        dst,n,rom=(uc.reg_read(reg(i)) for i in (3,4,5))
        assert n==0x4d000 and rom==0x1aff00
        uc.mem_write(dst,compressed+b'\0'*(n-len(compressed)))
        uc.reg_write(R.UC_PPC_REG_PC,uc.reg_read(R.UC_PPC_REG_LR))
    uc.hook_add(UC_HOOK_CODE,rom_read,begin=0x801a07cc,end=0x801a07cc)
    return uc


def run(uc,address,args=(),budget=20000000):
    uc.reg_write(reg(1),STACK)
    for i,v in enumerate(args,3):uc.reg_write(reg(i),v)
    uc.reg_write(R.UC_PPC_REG_LR,STOP)
    uc.emu_start(address,STOP,count=budget)
    assert uc.reg_read(R.UC_PPC_REG_PC)==STOP, 'CPU routine did not return'
    assert uc.reg_read(reg(1))==STACK
    return uc.reg_read(reg(3))


def decode_i4(data,w,h):
    im=Image.new('L',(w,h));pixels=im.load()
    for y in range(h):
        for x in range(w):
            n=(y//8)*(w//8)*32+(x//8)*32+(y%8)*4+(x%8)//2
            pixels[x,y]=((data[n]>>(4 if x%2==0 else 0))&15)*17
    return im


def prepare():
    raw,sections=load('jp')
    inv=json.loads((ROOT/'metadata/disc_inventory_jp.json').read_text(encoding='utf8'))
    assert sha(raw)==inv['dol']['sha256']
    compressed=FONT_FIXTURE.read_bytes();decompressed=yay0(compressed)
    rows=json.loads((ROOT/'work/analysis/jp/confirmed_messages.json').read_text(encoding='utf8'))['messages']
    # Conservative exclusion: scan all extracted executable bytes, including code.
    executable_bytes=[raw]+[p.read_bytes() for p in (ROOT/'work/analysis/jp/dll').glob('*.rel')]
    chars=sorted(set(''.join(PROBE.values()))-set('@?'))
    codes=[c for c in range(0x889f,0x9873) if 0x40<=(c&255)<=0xfc and (c&255)!=0x7f
           and all(c.to_bytes(2,'big') not in data for data in executable_bytes)]
    assert len(codes)>=len(chars)
    mapping=dict(zip(chars,codes[-len(chars):]));records={};bitmaps={}
    for char,code in mapping.items():
        index=glyph_index(code);bitmap=glyph_bitmap(char);bitmaps[char]=bitmap
        for y in range(24):
            for x in range(24):
                address,shift=glyph_address(index,x,y)
                records[address]=records.get(address,0)|((bitmap.getpixel((x,y))//85)<<shift)
        records[0x30+index]=FONT_ADVANCE
    payload,guards=build_payload(records)
    assert all(u32(decompressed,k)==v for k,v in guards.items())
    baseline=machine(raw,sections,payload,compressed)
    assert run(baseline,0x801a0858,(FONT_RAM,COMP_RAM))==len(decompressed)
    original_font=bytes(baseline.mem_read(FONT_RAM,len(decompressed)))
    reference_differences={}
    for char in 'よろしいですか表示確認':
        code=int.from_bytes(char.encode('cp932'),'big')
        index=run(baseline,0x801a0464,(code,))
        original=Image.new('L',(24,24))
        for y in range(24):
            for x in range(24):
                address,shift=glyph_address(index,x,y)
                original.putpixel((x,y),((original_font[address]>>shift)&3)*85)
        expected=glyph_bitmap(char,REFERENCE_TTF,19)
        reference_differences[char]=sum(a!=b for a,b in zip(original.tobytes(),expected.tobytes()))
        assert reference_differences[char]==0
        assert original_font[0x30+index]==FONT_ADVANCE
    cpu=machine(raw,sections,payload,compressed)
    sentinels={i:0xabc00000+i for i in range(14,32)}
    for i,v in sentinels.items():cpu.reg_write(reg(i),v)
    assert run(cpu,WRAPPER,(FONT_RAM,COMP_RAM))==len(decompressed)
    assert all(cpu.reg_read(reg(i))==v for i,v in sentinels.items())
    patched=bytes(cpu.mem_read(FONT_RAM,len(decompressed)))
    assert all(patched[a]==v for a,v in records.items())
    assert all(a in records or x==y for a,(x,y) in enumerate(zip(original_font,patched)))
    # The font guard must return harmlessly on an unsupported header.
    malformed=bytearray(original_font);struct.pack_into('>I',malformed,0x10,0x00100010)
    bad=machine(raw,sections,payload,compressed)
    bad.mem_write(FONT_RAM,bytes(malformed));bad.mem_write(R13-0x7778,struct.pack('>I',FONT_RAM))
    fake=PPC(0x801a0858);fake.load32(3,len(decompressed));fake.emit(0x4e800020)
    bad.mem_write(0x801a0858,fake.finish())
    assert run(bad,WRAPPER,(FONT_RAM,COMP_RAM))==len(decompressed)
    assert bytes(bad.mem_read(FONT_RAM,len(decompressed)))==malformed
    arena_results=[]
    for old in [0x802132f0,NEW_BASE,NEW_BASE+RESERVE,0x80280000]:
        result=run(cpu,NEW_BASE,(old,))
        assert result==max(old,NEW_BASE+RESERVE)
        assert u32(cpu.mem_read(R13-0x7e88,4),0)==result
        arena_results.append([hex(old),hex(result)])
    # Rendering uses the game's original glyph extraction and width routines.
    previews={};text_ram=0x80a00000;dest=0x80a01000;width_ram=0x80a03000
    for char,code in mapping.items():
        cpu.mem_write(text_ram,code.to_bytes(2,'big')+b'\0')
        cpu.mem_write(dest,b'\0'*512)
        assert run(cpu,0x801a0b8c,(text_ram,dest,0,8,width_ram))==text_ram+2
        assert u32(cpu.mem_read(width_ram,4),0)==FONT_ADVANCE
        picture=decode_i4(bytes(cpu.mem_read(dest,512)),32,32).crop((0,0,24,24))
        assert picture.tobytes()==bitmaps[char].tobytes()
        assert run(cpu,0x801a0e90,(text_ram,width_ram))==text_ram+2
        assert u32(cpu.mem_read(width_ram,4),0)==FONT_ADVANCE
        previews[char]=picture
    # Original digits and punctuation must render identically before/after.
    for char in '0123456789!?':
        images=[]
        for c in (baseline,cpu):
            c.mem_write(text_ram,char.encode()+b'\0');c.mem_write(dest,b'\0'*512)
            assert run(c,0x801a0b8c,(text_ram,dest,0,8,width_ram))==text_ram+1
            images.append((bytes(c.mem_read(dest,512)),bytes(c.mem_read(width_ram,4))))
        assert images[0]==images[1]
    # Repack just the changed groups inside their original allocation limits.
    dol=bytearray(raw);group_changes=[]
    for group in sorted({int(k.split('/')[1]) for k in PROBE}):
        members=[r for r in rows if r['group']==group]
        start=members[0]['offset'];last=members[-1]
        end=last['offset']+last['byte_length']+1
        encoded=[]
        for row in members:
            source=PROBE.get(row['id'],row['source'])
            data=b''.join(mapping[c].to_bytes(2,'big') if c in mapping else c.encode('cp932') for c in source)
            encoded.append(data+b'#')
        new=b''.join(encoded);assert len(new)<=end-start
        dol[start:end]=new+b'\0'*(end-start-len(new))
        assert bytes(dol[start:start+len(new)]).split(b'#')[:-1]==[b[:-1] for b in encoded]
        group_changes.append(dict(group=group,start=hex(start),allocated_bytes=end-start,new_bytes=len(new)))
    # Pure memory DOL recipe; does not create a patched executable on disk.
    assert all(u32(raw,p)==0 for p in (8,0x50,0x98)), 'Text section 2 is occupied'
    file_offset=(len(dol)+31)&~31
    dol.extend(b'\0'*(file_offset-len(dol)));dol.extend(payload)
    for pos,value in [(8,file_offset),(0x50,NEW_BASE),(0x98,RESERVE)]:struct.pack_into('>I',dol,pos,value)
    for address,target,link,expected in [(0x8002ffbc,WRAPPER,True,0x4817089d),
                                         (0x8019ee48,NEW_BASE,False,0x906d8178)]:
        at=offset(sections,address);assert u32(raw,at)==expected,(hex(address),hex(u32(raw,at)))
        a=PPC(address);a.branch(target,link);dol[at:at+4]=a.finish()
    assert NEW_BASE>=u32(raw,0xd8)+u32(raw,0xdc)
    assert all(NEW_BASE>=s['ram_address']+s['size'] or NEW_BASE+RESERVE<=s['ram_address'] for s in sections)
    # Future ISO recipe: move DOL into a gap outside all FST files/system tables.
    # Gap bytes are nonzero disc filler, not assumed empty or zero-filled.
    protected=[(0,inv['dol']['offset']+inv['dol']['size']),
               (inv['fst_offset'],inv['fst_offset']+inv['fst_size'])]
    protected += [(f['offset'],f['offset']+f['size']) for f in inv['files']]
    assert all(DISC_DOL_OFFSET>=end or DISC_DOL_OFFSET+len(dol)<=start for start,end in protected)
    with (ROOT/'Wario World (Japan).iso').open('rb') as disc:
        disc.seek(DISC_DOL_OFFSET);filler=disc.read(len(dol))
    assert len(filler)==len(dol)
    integrated=machine(bytes(dol),sections,payload,compressed)
    assert run(integrated,0x8019ee48,(NEW_BASE,))==NEW_BASE+RESERVE
    integrated.reg_write(reg(1),STACK)
    integrated.reg_write(reg(3),FONT_RAM);integrated.reg_write(reg(4),COMP_RAM)
    integrated.emu_start(0x8002ffbc,0x8002ffc0,count=20000000)
    assert integrated.reg_read(R.UC_PPC_REG_PC)==0x8002ffc0
    assert bytes(integrated.mem_read(FONT_RAM,len(patched)))==patched
    run(integrated,0x80062004)
    for row in rows:
        if row['group']=='save':continue
        array=u32(integrated.mem_read(0x801bf5e4+row['group']*4,4),0)
        pointer=u32(integrated.mem_read(array+row['index']*4,4),0)
        source=PROBE.get(row['id'],row['source'])
        expected=b''.join(mapping[c].to_bytes(2,'big') if c in mapping else c.encode('cp932') for c in source)
        assert bytes(integrated.mem_read(pointer,len(expected)+1))==expected+b'\0'
    lines=[]
    for label,text in [('Original prompt','よろしいですか？'),('Korean prompt','확인할까요?'),
                       ('Korean menu','시작  취소'),('Mixed baseline','시작 123!?')]:
        line=Image.new('L',(320,24),0);x=0
        for char in text:
            encoded=mapping[char].to_bytes(2,'big') if char in mapping else char.encode('cp932')
            integrated.mem_write(text_ram,encoded+b'\0');integrated.mem_write(dest,b'\0'*512)
            assert run(integrated,0x801a0b8c,(text_ram,dest,0,8,width_ram))==text_ram+len(encoded)
            advance=u32(integrated.mem_read(width_ram,4),0)
            tile=decode_i4(bytes(integrated.mem_read(dest,512)),32,32).crop((0,0,24,24))
            line.paste(tile,(x,0));x+=advance
        lines.append((label,line,x))
    return dict(raw=raw,dol=bytes(dol),payload=payload,mapping=mapping,previews=previews,
                original_font=original_font,patched_font=patched,records=records,
                font_fixture_sha256=sha(compressed),ttf_sha256=sha(FONT_TTF.read_bytes()),
                groups=group_changes,arena_results=arena_results,file_offset=file_offset,lines=lines,
                overwritten_filler_sha256=sha(filler),reference_differences=reference_differences)


def main():
    result=prepare();folder=ROOT/'work/output-probe';folder.mkdir(parents=True,exist_ok=True)
    chars=list(result['mapping']);sheet=Image.new('RGB',(360,260),'#eeeeee')
    draw=ImageDraw.Draw(sheet);draw.text((8,6),'CPU glyph preview - not a game screenshot',fill='black')
    for i,(label,line,width) in enumerate(result['lines']):
        y=30+i*56;draw.text((8,y),f'{label} ({width}px advance)',fill='black')
        sheet.paste(Image.eval(line,lambda v:255-v).convert('RGB'),(8,y+18))
    sheet.save(folder/'cpu-glyph-preview.png')
    sheet.resize((sheet.width*3,sheet.height*3),Image.Resampling.NEAREST).save(folder/'cpu-glyph-preview-3x.png')
    report=dict(edition='GWWJ01 revision 0',scope='Preparation and isolated CPU tests only; no patched DOL or ISO saved',
        messages=PROBE,mapping={c:dict(code=f'{v:04X}',index=glyph_index(v)) for c,v in result['mapping'].items()},
        version='v02',glyph_count=len(chars),font='Gmarket Sans Medium, 20px, baseline 18, 24x24 cell, 20px game advance (19px font advance), four grayscale levels',
        reference_match=dict(source='Unchanged Japanese font cross-check using separate Droid reference; not a Gmarket similarity test or hardware IPL test',
                             japanese_glyph_differing_pixels=result['reference_differences']),
        source_font_sha256=result['ttf_sha256'],dolphin_fixture_sha256=result['font_fixture_sha256'],
        injected_section=dict(slot=2,ram_address=hex(NEW_BASE),size=RESERVE,file_offset=hex(result['file_offset'])),
        hooks=[dict(address='0x8002FFBC',purpose='Original font initialization then guarded glyph replacement'),
               dict(address='0x8019EE48',purpose='Clamp arena low to protect new section before arena clearing/heap allocation')],
        group_changes=result['groups'],arena_cases=result['arena_results'],
        planned_iso_changes=[dict(offset='0x420',length=4,purpose='DOL pointer to 0x00CD8000'),
                             dict(offset=hex(DISC_DOL_OFFSET),length=len(result['dol']),
                                  purpose='Relocated patched DOL in non-FST gap; nonzero filler overwritten',
                                  original_range_sha256=result['overwritten_filler_sha256'])],
        dolphin_version='2609 (local executable --version)',
        tests={'original_font_init':'executed; only IPL read mocked using read-only local Dolphin font',
               'glyph_rendering':'all 9 Korean glyphs pixel-identical through original PPC glyph extraction',
               'digits_punctuation':'0123456789!? pixels and widths unchanged',
               'unknown_header':'guard skips all writes', 'callee_saved_registers_stack':'preserved',
               'font_outside_target_bytes':'unchanged', 'font_width_next_pointer':'20px, advances 2 bytes',
               'patched_entry_points':'font call and arena setter branches executed',
               'game_message_initializer':'all 269 main pointers and strings match expected after original initialization',
               'originals':'recorded DOL hash checked; no original modified'},
        in_memory_dol_sha256=sha(result['dol']),in_memory_dol_size=len(result['dol']),
        unverified=['Full emulator boot and screen placement','Game-path scene reachability','Real IPL font header compatibility','Hardware','Disc relocation/build not yet performed'])
    save(ROOT/'metadata/output_probe_preparation.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
