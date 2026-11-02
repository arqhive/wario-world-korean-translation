"""Read-only DOL address/disassembly helpers."""
import json
import struct
import sys
from capstone import Cs,CS_ARCH_PPC,CS_MODE_32,CS_MODE_BIG_ENDIAN
from inspect_discs import ROOT


def load(region):
    return ((ROOT/f'work/analysis/{region}/main.dol').read_bytes(),
            json.loads((ROOT/f'metadata/disc_inventory_{region}.json').read_text(encoding='utf8'))['dol']['sections'])


def offset(sections,address):
    s=next(s for s in sections if s['ram_address']<=address<s['ram_address']+s['size'])
    return s['file_offset']+address-s['ram_address']


def main():
    region,mode=sys.argv[1:3];b,ss=load(region);a=int(sys.argv[3],0)
    if mode=='disasm':
        end=int(sys.argv[4],0);cs=Cs(CS_ARCH_PPC,CS_MODE_32|CS_MODE_BIG_ENDIAN);cs.skipdata=True
        for i in cs.disasm(b[offset(ss,a):offset(ss,end)],a):print(f'{i.address:08X} {i.mnemonic:9} {i.op_str}')
    elif mode=='xref':
        for s in ss:
            if s['kind']!='text':continue
            for n in range(0,s['size'],4):
                word=struct.unpack_from('>I',b,s['file_offset']+n)[0]
                if word>>26!=18:continue
                disp=word&0x03fffffc
                if disp&0x02000000:disp-=0x04000000
                pc=s['ram_address']+n
                dest=disp if word&2 else pc+disp
                if dest==a:print(hex(pc),'bl' if word&1 else 'b')


if __name__=='__main__':main()
