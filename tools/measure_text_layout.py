"""Read-only measurements using the JP game's real font and layout routines.

Writes evidence, never a DOL/ISO. All units are text-texture pixels, not
scaled screenshots. Original content dimensions are NOT window limits.
"""
import json
import struct
from inspect_discs import ROOT, save
from research_code import load, offset
from prepare_output_probe import machine, run, FONT_FIXTURE, FONT_RAM, COMP_RAM, sha

TEXT = 0x81000000  # isolated CPU scratch addresses, never patch locations
RESULT = TEXT + 0x10000
LABELS = ['스탬프 이름', '스탬프 설명', '화면 모드', '디스크 오류', '월드 이름',
          '스테이지 이름', '보스 열쇠', '보물 이름', '복귀 메뉴', '도움말',
          '마늘 판매·수집 안내', '확인 질문', '아니요·예', '컨티뉴', '진동 설정',
          '도입 이야기', '엔딩 대사', 'GBA 연결', '날짜·시간', '저장 선택지', '메모리 카드']
# Direct constructor call evidence: group, caller, pointer array, item count.
DIRECT = [(0,0x8005db10,0x801d0960,3),(1,0x8005db24,0x801d096c,3),
          (4,0x8005ea34,0x801d0998,13),(5,0x8005ea48,0x801d09cc,13),
          (6,0x800600a4,0x801d0a00,5),(7,0x8005c2d8,0x801d0a14,65),
          (8,0x800610b8,0x801d0b18,2),(9,0x8005b4c4,0x801d0b28,41),
          (10,0x8009e564,0x801d0bcc,4),(11,0x80061438,0x801d0bdc,3),
          (12,0x80061448,0x801fec40,2),(8,0x80061424,0x801d0b20,2),
          (13,0x80063298,0x801d0bf8,3),(13,0x800632b0,0x801d0c04,3),
          (13,0x800632c4,0x801d0be8,4),(18,0x800b4178,0x801d0cb0,6),
          (19,0x800b4210,0x801d0cc8,6),(20,0x800b40d4,0x801d0ce0,43),
          (2,0x8015a90c,0x801d0978,3),(3,0x80030390,0x801d0984,5)]


def measured_shape(text, widths):
    lines = [sum(widths[c] for c in line) for line in text.split('@')]
    return {'line_widths_px': lines, 'max_line_width_px': max(lines),
            'line_count': len(lines), 'texture_width_px': ((max(24,max(lines))+23)//24)*24,
            'texture_height_px': len(lines)*24}


def main():
    raw, sections = load('jp')
    rows = json.loads((ROOT/'work/analysis/jp/confirmed_messages.json').read_text(encoding='utf8'))['messages']
    compressed = FONT_FIXTURE.read_bytes()
    cpu = machine(raw, sections, b'\0'*0x4000, compressed)
    run(cpu, 0x801a0858, (FONT_RAM,COMP_RAM))
    widths = {}
    chars = sorted((set(''.join(r['source'] for r in rows)) | set('0123456789!?.,:; -()')) - {'@'})
    for c in chars:
        encoded = c.encode('cp932')
        cpu.mem_write(TEXT, encoded+b'\0')
        end = run(cpu,0x801a0e90,(TEXT,RESULT))
        assert end == TEXT+len(encoded), (c,hex(end))
        widths[c] = struct.unpack('>I',cpu.mem_read(RESULT,4))[0]
    measurements = []
    for row in rows:
        expected = measured_shape(row['source'], widths)
        cpu.mem_write(TEXT, row['source'].encode('cp932')+b'\0')
        run(cpu,0x8007f0f4,(0,TEXT,RESULT,RESULT+4))
        actual = struct.unpack('>II',cpu.mem_read(RESULT,8))
        assert actual == (expected['texture_width_px'],expected['texture_height_px']), (row['id'],actual,expected)
        measurements.append({'id':row['id'],**expected,'screen_fit':'unverified',
                             'renderer_binding':'verified_constructor_chain' if row.get('group') in {d[0] for d in DIRECT} and row['id'].startswith('main/') else 'pending',
                             'dynamic_content':row['id'].startswith('main/18/')})
    # Verify the installed probe's Korean advance without altering any disk data.
    probe = json.loads((ROOT/'metadata/output_probe_preparation.json').read_text(encoding='utf8'))
    ko_widths = {}
    for c, m in probe['mapping'].items():
        cpu.mem_write(FONT_RAM+0x30+m['index'], bytes([20]))
        cpu.mem_write(TEXT, bytes.fromhex(m['code'])+b'\0')
        assert run(cpu,0x801a0e90,(TEXT,RESULT)) == TEXT+2
        ko_widths[c] = struct.unpack('>I',cpu.mem_read(RESULT,4))[0]
        assert ko_widths[c] == 20
    groups=[]
    for g in range(21):
        rs=[m for m in measurements if m['id'].startswith(f'main/{g:02d}/')]
        pointer=struct.unpack_from('>I',raw,offset(sections,0x801bf5e4)+g*4)[0]
        direct=[{'caller':hex(a),'pointer_array':hex(p),'count':n} for gg,a,p,n in DIRECT if gg==g]
        for d in direct:
            start=(int(d['pointer_array'],16)-pointer)//4
            assert pointer+start*4 == int(d['pointer_array'],16) and 0<=start<start+d['count']<=len(rs)
            d['first_index']=start
        groups.append({'group':g,'label':LABELS[g],'entries':len(rs),
                       'source_max_line_px':max(m['max_line_width_px'] for m in rs),
                       'source_max_lines':max(m['line_count'] for m in rs),
                       'source_texture_envelope_px':[max(m['texture_width_px'] for m in rs),max(m['texture_height_px'] for m in rs)],
                       'direct_constructors':direct,'window_width_limit_px':None,'window_line_limit':None,
                       'limit_note':'Original-content envelope only; dynamic texture allocation is not a screen-fit limit.'})
    # Synthetic boundaries independently exercise the original layout routine.
    boundary_cases=['','@','a@','@@a','a@@b','a'*200,'あ@い@う']
    for s in boundary_cases:
        for c in set(s)-{'@'}-widths.keys():
            cpu.mem_write(TEXT,c.encode('cp932')+b'\0');run(cpu,0x801a0e90,(TEXT,RESULT))
            widths[c]=struct.unpack('>I',cpu.mem_read(RESULT,4))[0]
        expected=measured_shape(s,widths)
        cpu.mem_write(TEXT,s.encode('cp932')+b'\0');run(cpu,0x8007f0f4,(0,TEXT,RESULT,RESULT+4))
        assert struct.unpack('>II',cpu.mem_read(RESULT,8)) == (expected['texture_width_px'],expected['texture_height_px'])
    report={'edition':'GWWJ01 rev0','dol_sha256':sha(raw),'font_fixture_sha256':sha(compressed),
            'units':'unscaled text-texture pixels; not display/window pixels',
            'routine':'0x8007F0F4','glyph_width_routine':'0x801A0E90','line_pitch_px':24,
            'allocation':'width rounded up to 24, minimum 24; height = 24 * (count(@)+1)',
            'cpu_matches':len(measurements),'boundary_case_matches':len(boundary_cases),
            'automatic_wrap':'Not present in measured plain-text layout/raster routines',
            'original_widths_px':widths,'probe_korean_widths_px':ko_widths,
            'other_hangul':'Not installed by v02; do not treat arbitrary Hangul as supported',
            'groups':groups,'measurements':measurements,
            'probe_measurements':{k:measured_shape(v,widths|ko_widths) for k,v in probe['messages'].items()},
            'full_game_coverage':False,'screen_fit_verified':False}
    save(ROOT/'metadata/text_layout_measurements.json', report)
    print(json.dumps({'cpu_matches':len(measurements),'boundary_matches':len(boundary_cases),
                      'sample_widths':{c:widths[c] for c in ' 0!?、。あ'},
                      'probe':report['probe_measurements'],
                      'groups':[{k:g[k] for k in ['group','label','source_max_line_px','source_max_lines']} for g in groups]},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
