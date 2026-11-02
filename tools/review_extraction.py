"""Apply recorded contact-sheet observations and build a local review gallery.

Observations made by the main session on 2026-10-13, all 27 JP contact sheets.
Thumbnail review cannot establish absence of tiny or model-generated lettering.
"""
import collections
import html
import json
from inspect_discs import ROOT,save
from extract_stage4 import OUT,readj

WORDS={37:'CLEAR!!',68:'일본어 안내판',79:'타이틀 로고',80:'PRESS START',81:'OPTION',
       100:'GAME OVER',243:'작은 타이틀 로고',589:'서커스 포스터 A',590:'서커스 포스터 B',
       1611:'Wario 장식 명판 — 작은 글씨 추가 판독',1616:'목제 안내판 — 원문 추가 판독'}
BRANDS={47:'Treasure/Nintendo',78:'저작권 표시',82:'Nintendo',83:'Dolby'}
SYMBOLS={33:'100',34:'10',97:'숫자·통화 HUD',554:'깃발 W',594:'시계 숫자',642:'버튼 B',644:'버튼 B',
         672:'문장 W',1049:'문장 W',1131:'시계 숫자',1248:'1',1249:'2',1250:'3',1251:'4',
         1465:'복장 W',1486:'복장 W',1563:'자석 N/S',1608:'문장 W',1629:'문장 W',1630:'문장 W',
         1641:'복장 W',1646:'문장 W',1678:'문장 W'}


def main():
    inv=readj(ROOT/'metadata/extraction_inventory.json');pages=readj(OUT/'sheets/index.json')
    items={i['number']:i for p in pages for i in p['items']};by_png={i['png']:n for n,i in items.items()}
    for r in inv['textures']:
        n=by_png.get(r['levels'][0]['png'])
        if n is None:continue
        if n in WORDS:category='word_art_candidate';note=WORDS[n];proposal='용어집·그래픽 규칙 승인 후 개별 번역안 검토'
        elif n in BRANDS:category='brand_or_copyright';note=BRANDS[n];proposal='원형 보존 권고; 범위 승인 대기'
        elif n in SYMBOLS:category='symbol_or_number';note=SYMBOLS[n];proposal='원형 보존 권고; 범위 승인 대기'
        else:category='no_readable_words_seen_in_thumbnail';note='축소 비교표에서 명확한 번역 단어를 발견하지 못함. 작은 글씨·장식 문자·실제 모델 배치는 미확인.';proposal='플레이에서 추가 발견 시 재분류'
        r['visual_classification']=category;r['visual_note']=note;r['localization_proposal']=proposal
        r['review_evidence']={'sheet':pages[n//64]['sheet'],'number':n,'scale':'thumbnail contact sheet',
                              'native_png_inspected':n in [333,335,1611,1616,1672],
                              'cross_region_note':'Same PNG pixels may share visual review; in-game use is not inferred.'}
    inv['visual_review']={'unique_jp_base_textures_reviewed':len(items),'contact_sheets':len(pages),
                           'word_art_candidates':len(WORDS),'no_absence_guarantee':True}
    save(ROOT/'metadata/extraction_inventory.json',inv)
    # Remove obvious binary hits from the raw candidate list without deleting it.
    ranges=collections.defaultdict(list);known=collections.defaultdict(list)
    for t in inv['textures']:
        if t['region']=='jp':ranges[f'{t["file"]}::{t["member"]}'].append((t['tpl_offset'],max(l['payload_offset']+l['size'] for l in t['levels'])))
    for r in readj(ROOT/'translation/messages.json')['messages']:
        f=r['file']+(f'::{r["member"]}' if 'member' in r else '')
        known[f].append((r['offset'],r['offset']+r['byte_length']+1))
    kept=[];discard=collections.Counter()
    for r in readj(OUT/'jp/string_candidates.json'):
        f=r['file'];s=r['text'];a=r['offset'];z=a+len(s.encode(r['encoding']))
        overlap=sum(max(0,min(z,end)-max(a,start)) for start,end in known[f])
        if overlap>=(z-a)*.9:discard['already_structurally_extracted']+=1
        elif any(start<=a<end for start,end in ranges[f]):discard['inside_validated_tpl']+=1
        elif f.endswith(('.dsp','.samp')):discard['encoded_audio_candidate']+=1
        elif len(s)>2000 or len(set(s))<5:discard['repetition_or_long_binary_run']+=1
        elif r['encoding']=='ascii' and (len(s)<12 or sum(c.isalpha() or c.isspace() for c in s)<len(s)*.9):discard['low_language_signal']+=1
        else:kept.append(r)
    save(OUT/'jp/triaged_candidates.json',{'triage_reasons':dict(discard),'candidates':kept,
         'note':'Heuristic review queue, not additional confirmed dialogue. GBA internals remain a separate scope.'})
    # All native images are linked; only contact sheets have scaled/composited previews.
    by_id={t['id']:t for t in inv['textures']};cards=[]
    order=sorted(items,key=lambda n:(n not in WORDS,n not in BRANDS,n))
    for n in order:
        i=items[n];r=by_id[i['asset_id']];label=WORDS.get(n,BRANDS.get(n,SYMBOLS.get(n,'')))
        url=i['png'].removeprefix('work/extraction/')
        caption=f"{n:04d} {label} · {r['file']} / {r['member']} / {r['texture']} · {r['width']}×{r['height']}"
        cards.append(f'<a class="card" data-words="{int(n in WORDS)}" href="{html.escape(url)}" target="_blank"><img loading="lazy" src="{html.escape(url)}"><p>{html.escape(caption)}</p></a>')
    body='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>와리오 월드 그래픽 조사</title>
<style>body{font:16px system-ui;background:#202124;color:#eee;margin:28px}header{position:sticky;top:0;background:#202124;padding:12px 0}input,button{font:inherit;padding:9px;margin-right:10px}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}.card{background:#35363a;color:inherit;padding:12px;text-decoration:none}.card img{width:100%;height:190px;object-fit:contain;background:repeating-conic-gradient(#777 0% 25%,#aaa 0% 50%) 0/18px 18px}.card p{font-size:13px;overflow-wrap:anywhere}small{color:#bbb}</style>
<header><h1>와리오 월드 · 그래픽 조사</h1><p>중복을 묶은 일본판 1,687장. 글자 그림 후보 11장을 먼저 표시합니다. 이미지를 누르면 원본 크기 PNG를 엽니다.</p><input id="q" placeholder="번호·경로·이름 검색"><button id="toggle">전체 보기</button><small>추출본 · 번역안과 수정 승인은 다음 단계에서 진행</small></header><main>'''+''.join(cards)+'''</main><script>
let only=true;const cards=[...document.querySelectorAll('.card')];function filter(){const q=document.querySelector('#q').value.toLowerCase();cards.forEach(c=>c.hidden=!((!only||c.dataset.words==='1')&&c.textContent.toLowerCase().includes(q)));cards.forEach(c=>c.style.display=c.hidden?'none':'block')}document.querySelector('#q').oninput=filter;document.querySelector('#toggle').onclick=function(){only=!only;this.textContent=only?'전체 보기':'글자 후보만 보기';filter()};filter();</script></html>'''
    (OUT/'gallery.html').write_text(body,encoding='utf8')
    print('word art',len(WORDS),'remaining heuristic candidates',len(kept),dict(collections.Counter(r['file'].split('/')[0] for r in kept)))


if __name__=='__main__':main()
