"""Execute the original JP PPC glyph mapper with font encoding mocked to SJIS.

Synthetic CPU memory is isolated. This does not load an emulator/game or prove
font rendering. The encoding getter alone is replaced by `li r3,1; blr`.
"""
import struct
import hashlib
import json
from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN
from unicorn.ppc_const import UC_PPC_REG_1, UC_PPC_REG_3, UC_PPC_REG_LR, UC_PPC_REG_PC
from inspect_discs import ROOT, save
from research_code import load


def main():
    raw, sections = load('jp')
    expected_hash = json.loads((ROOT/'metadata/disc_inventory_jp.json').read_text(encoding='utf8'))['dol']['sha256']
    assert hashlib.sha256(raw).hexdigest() == expected_hash
    uc = Uc(UC_ARCH_PPC, UC_MODE_32 | UC_MODE_BIG_ENDIAN)
    uc.mem_map(0x80000000, 0x400000)
    for section in sections:
        o, size = section['file_offset'], section['size']
        uc.mem_write(section['ram_address'], raw[o:o+size])
    uc.mem_write(0x801A0774, struct.pack('>2I', 0x38600001, 0x4e800020))
    slots = []
    for code in range(0x889f, 0x9873):
        if not 0x40 <= (code & 255) <= 0xfc or (code & 255) == 0x7f:
            continue
        uc.reg_write(UC_PPC_REG_1, 0x803FF000)
        uc.reg_write(UC_PPC_REG_3, code)
        uc.reg_write(UC_PPC_REG_LR, 0x80300000)
        uc.emu_start(0x801A0464, 0x80300000, count=200)
        assert uc.reg_read(UC_PPC_REG_PC) == 0x80300000
        index = uc.reg_read(UC_PPC_REG_3)
        low = (code & 255)-0x40
        expected = ((code >> 8)-0x88)*188+low-(low>=64)+0x2be
        assert index == expected
        slots.append((code, index))
    indices = [index for _,index in slots]
    assert len(set(indices)) == len(indices)
    assert indices == list(range(indices[0], indices[-1]+1))
    result = dict(edition='jp', method='Unicorn PPC32 big-endian; original mapper instructions; SJIS encoding getter mocked',
        mapper_va='0x801A0464', source_code_range=['0x889f','0x9872'],
        unique_contiguous_slots=len(slots), glyph_index_range=[indices[0], indices[-1]],
        requested_common_hangul_syllables=2350, sufficient_index_capacity=len(slots)>=2350,
        original_font_allocation_bytes=0x90ee4,
        limits=['Index mapping only; actual font header, glyph pixels, metrics and initialization hook remain untested.',
                'Synthetic CPU addresses are test-only and must not be used as patch allocation addresses.',
                'Replacing Japanese glyphs requires an explicit character map and preserving every untranslated glyph.'])
    save(ROOT/'metadata/font_mapper_verification.json', result)
    print(result)


if __name__ == '__main__':
    main()
