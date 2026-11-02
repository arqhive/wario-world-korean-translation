"""Extract confirmed DOL message tables and roundtrip through disk JSON.

No translation, DOL output, or ISO output. Unexamined executable strings are
not part of the message totals. Addresses are specific to recorded originals.
"""
import collections
import hashlib
import json
import struct
from inspect_discs import ROOT, save
from research_code import load, offset

LAYOUTS = {
    'jp': (0x801B4E40, 0x801BF5CC, 0x801B4DE0, 0x801B7364),
    'us': (0x801B3E78, 0x801BE78C, 0x801B3E20, 0x801B6532),
}


def extract(region):
    raw, sections = load(region)
    inv = json.loads((ROOT/f'metadata/disc_inventory_{region}.json').read_text(encoding='utf8'))
    assert hashlib.sha256(raw).hexdigest() == inv['dol']['sha256']
    base, count_addr, title_base, end_addr = LAYOUTS[region]
    start = offset(sections, base)
    count = struct.unpack_from('>I', raw, start)[0]
    assert count == 21
    counts = raw[offset(sections, count_addr):offset(sections, count_addr)+count]
    starts = [start+4*x for x in struct.unpack_from(f'>{count}I', raw, start+4)]
    assert starts == sorted(set(starts)) and starts[0] == start+4*(count+1)
    limits = starts[1:] + [offset(sections, end_addr)]
    rows = []
    for group, (p, limit, n) in enumerate(zip(starts, limits, counts)):
        for index in range(n):
            end = raw.index(b'#', p, limit)
            data = raw[p:end]
            text = data.decode('cp932', errors='strict')
            assert text.encode('cp932') == data, 'Non-canonical CP932 requires byte token handling'
            assert b'\0' not in data
            rows.append(dict(id=f'main/{group:02}/{index:03}', file='main.dol',
                             group=group, index=index, offset=p, byte_length=len(data),
                             source=text, translation='', speaker=None))
            p = end+1
        assert not any(raw[p:limit]), 'Unexpected intergroup padding'
    tb = offset(sections, title_base)
    assert struct.unpack_from('>2I', raw, tb) == (1, 2)
    p = tb+8
    for index in range(3):
        end = raw.index(b'#', p, start)
        data = raw[p:end]
        source = data.decode('cp932')
        assert source.encode('cp932') == data
        rows.append(dict(id=f'save/{index:03}', file='main.dol', group='save',
                         index=index, offset=p, byte_length=len(data),
                         source=source, translation='', speaker=None))
        p = end+1
    path = ROOT/f'work/analysis/{region}/confirmed_messages.json'
    save(path, dict(edition=region, encoding='cp932', terminator='#', messages=rows))
    reread = json.loads(path.read_text(encoding='utf8'))['messages']
    # Reassemble confirmed tables from structured integers and decoded strings.
    # Everything outside these tables remains opaque; this is not a full DOL rebuild.
    rebuilt = bytearray(raw)
    struct.pack_into(f'>{count+1}I', rebuilt, start, count,
                     *((p-start)//4 for p in starts))
    struct.pack_into('>2I', rebuilt, tb, 1, 2)
    for row in reread:
        data = row['source'].encode('cp932') + b'#'
        assert len(data) == row['byte_length']+1
        rebuilt[row['offset']:row['offset']+len(data)] = data
    assert rebuilt == raw
    chars = collections.Counter(c for r in rows for c in r['source'])
    return rows, dict(edition=region, group_count=count, main_messages=sum(counts),
        save_messages=3, total_confirmed=len(rows), group_sizes=list(counts),
        encoded_bytes=sum(r['byte_length'] for r in rows),
        unicode_codepoints=sum(chars.values()),
        visible_nonspace_codepoints=sum(v for c,v in chars.items() if not c.isspace() and c!='@'),
        unique_nonspace_codepoints=sum(1 for c in chars if not c.isspace() and c!='@'),
        ascii_punctuation={c:v for c,v in chars.items() if 0x21<=ord(c)<=0x7e and not c.isalnum()},
        max_at_delimited_segment_codepoints=max(len(s) for r in rows for s in r['source'].split('@')),
        table_start_va=hex(base), count_array_va=hex(count_addr),
        disk_json_table_roundtrip_equal=True, original_dol_sha256=hashlib.sha256(raw).hexdigest(),
        scope='Confirmed 21-group table and 3 save strings only. @ is a delimiter candidate, not a fully decoded control grammar. Counts are not whole-game totals.')


def main():
    results = [extract(r) for r in LAYOUTS]
    jp, us = (r[0] for r in results)
    assert [r['id'] for r in jp] == [r['id'] for r in us]
    save(ROOT/'work/analysis/message_comparison.json', [dict(id=a['id'], japanese=a['source'],
        english=b['source'], translation='', alignment='Same table group/index; semantic review pending')
        for a,b in zip(jp,us)])
    save(ROOT/'metadata/message_analysis.json', dict(editions=[r[1] for r in results],
        alignment='272 structurally corresponding entries; not a claim of all-game extraction'))
    for _, stats in results:
        print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
