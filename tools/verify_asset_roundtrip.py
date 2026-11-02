"""Disk extraction/reassembly of RSC wrappers and inventory of type-1 TPLs.

Opaque payloads are preserved, not interpreted as fully supported assets.
Additionally decode and re-encode every unpadded I4 base texture through PNG.
Never writes an ISO. Game binaries and images stay under ignored work/.
"""
import collections
import hashlib
import json
import struct
from PIL import Image
from inspect_discs import ROOT, INPUTS, save
from inspect_rsc import parse

FORMATS = {0:'I4', 1:'I8', 2:'IA4', 3:'IA8', 4:'RGB565', 5:'RGB5A3',
           6:'RGBA8', 8:'C4', 9:'C8', 10:'C14X2', 14:'CMPR'}
BLOCKS = {0:(8,8,32), 1:(8,4,32), 2:(8,4,32), 3:(4,4,32),
          4:(4,4,32), 5:(4,4,32), 6:(4,4,64), 8:(8,8,32),
          9:(8,4,32), 10:(4,4,32), 14:(8,8,32)}


def roundtrip_i4(data, width, height, path):
    pixels = bytearray(width*height)
    p = 0
    for by in range(0,height,8):
        for bx in range(0,width,8):
            for y in range(8):
                for x in range(0,8,2):
                    v = data[p]; p += 1
                    pos = (by+y)*width+bx+x
                    pixels[pos] = (v>>4)*17
                    pixels[pos+1] = (v&15)*17
    Image.frombytes('L',(width,height),bytes(pixels)).save(path)
    with Image.open(path) as im:
        assert im.mode == 'L' and im.size == (width,height)
        decoded = im.tobytes()
    rebuilt = bytearray()
    for by in range(0,height,8):
        for bx in range(0,width,8):
            for y in range(8):
                for x in range(0,8,2):
                    pos = (by+y)*width+bx+x
                    a,b = decoded[pos:pos+2]
                    assert a%17 == b%17 == 0
                    rebuilt.append((a//17)*16+b//17)
    assert rebuilt == data


def inspect_tpl(raw, archive, member, folder):
    magic,count,table = struct.unpack_from('>3I',raw)
    assert magic == 0x0020af30 and table+8*count<=len(raw)
    records = []
    for index in range(count):
        ih,ph = struct.unpack_from('>2I',raw,table+index*8)
        assert ih+36<=len(raw)
        height,width,fmt,data = struct.unpack_from('>HHII',raw,ih)
        assert fmt in BLOCKS and width and height
        bw,bh,bs = BLOCKS[fmt]
        size = ((width+bw-1)//bw)*((height+bh-1)//bh)*bs
        assert data+size<=len(raw)
        if ph:
            assert ph+12<=len(raw)
            colors,unpacked,pad,pfmt,pdata = struct.unpack_from('>HBBII',raw,ph)
            assert pfmt in (0,1,2) and pdata+colors*2<=len(raw)
        else:
            colors = pfmt = None
        rec = dict(archive=archive, member=member, texture=index, width=width,height=height,
                   format=FORMATS[fmt], image_offset=data, base_level_bytes=size,
                   base_level_sha256=hashlib.sha256(raw[data:data+size]).hexdigest(),
                   palette_entries=colors,palette_format=pfmt,
                   min_lod=raw[ih+33],max_lod=raw[ih+34],
                   contains_text='unreviewed', pixel_roundtrip='not_tested')
        if fmt==0 and width%8==0 and height%8==0:
            roundtrip_i4(raw[data:data+size],width,height,folder/f'{member:03}_{index:03}_i4.png')
            rec['pixel_roundtrip']='base-level I4 -> grayscale PNG -> tiled I4: byte-identical'
        records.append(rec)
    return records


def main():
    results = []
    for region,filename in INPUTS:
        inv = json.loads((ROOT/f'metadata/disc_inventory_{region}.json').read_text(encoding='utf8'))
        archives = []; textures = []
        with (ROOT/filename).open('rb') as disc:
            for entry in inv['files']:
                if not entry['path'].endswith('.RSC'):
                    continue
                disc.seek(entry['offset']); raw = disc.read(entry['size'])
                assert hashlib.sha256(raw).hexdigest()==entry['sha256']
                members = parse(raw)
                folder = ROOT/f'work/roundtrip/{region}'/entry['path']
                folder.mkdir(parents=True,exist_ok=True)
                (folder/'header.bin').write_bytes(raw[:32])
                for m in members:
                    p = m['header_offset']+32
                    (folder/f"{m['index']:03}.bin").write_bytes(raw[p:p+m['size']])
                    m['padding_hex'] = raw[p+m['size']:p+m['size']+m['padding_size']].hex()
                save(folder/'manifest.json',members)
                manifest = json.loads((folder/'manifest.json').read_text(encoding='utf8'))
                rebuilt = bytearray((folder/'header.bin').read_bytes())
                for m in manifest:
                    payload = (folder/f"{m['index']:03}.bin").read_bytes()
                    assert len(payload)==m['size'] and len(rebuilt)==m['header_offset']
                    rebuilt.extend(struct.pack('>8I',m['type'],len(payload),m['next_offset'],*m['reserved']))
                    rebuilt.extend(payload)
                    rebuilt.extend(bytes.fromhex(m['padding_hex']))
                    if m['type']==1:
                        textures.extend(inspect_tpl(payload,entry['path'],m['index'],folder))
                assert rebuilt==raw
                (folder/'repacked.rsc').write_bytes(rebuilt)
                assert hashlib.sha256((folder/'repacked.rsc').read_bytes()).hexdigest()==entry['sha256']
                archives.append(dict(path=entry['path'],members=len(members),disk_wrapper_roundtrip_equal=True))
        stats = dict(edition=region, archives=len(archives),members=sum(a['members'] for a in archives),
                     tpl_containers=len({(t['archive'],t['member']) for t in textures}),
                     textures=len(textures),formats=dict(collections.Counter(t['format'] for t in textures)),
                     i4_base_levels_roundtripped=sum(t['pixel_roundtrip']!='not_tested' for t in textures),
                     unique_base_level_hashes=len({t['base_level_sha256'] for t in textures}))
        results.append(dict(summary=stats,archives=archives,textures=textures))
        print(stats,flush=True)
    save(ROOT/'metadata/asset_roundtrip.json',dict(scope='All RSC wrappers via disk manifests and unchanged payload files; TPL base-level bounds and selected I4 pixel roundtrips only. Other texture formats, mip levels, non-TPL payloads and full ISO rebuild are not validated.',editions=results))


if __name__=='__main__':
    main()
