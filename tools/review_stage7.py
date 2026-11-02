"""Read-only localization audit and proposed changes. Never applies translations or builds."""
import copy
import hashlib
import json
import re
from pathlib import Path
from PIL import Image
from check_translation import check, tokens

ROOT=Path(__file__).resolve().parents[1]


def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
def thash(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def save(p,v):(ROOT/p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    rows=read('translation/messages.json')['messages']
    terms=read('translation/glossary.json')['terms']
    originals={r['id']:r['source'] for r in read('work/extraction/jp/messages.json')['messages']}
    errors,warnings=check(rows,originals,terms)
    notes=read('metadata/translation_review_notes.json')['notes']
    byid={r['id']:r for r in rows}
    reviewed=[];unreviewed=[]
    for warning in warnings:
        row=byid[warning['id']]
        matches=[n for n in notes if n['warning']==warning and n['source_sha256']==thash(row['source']) and n['translation_sha256']==thash(row['translation'])]
        (reviewed if matches else unreviewed).append(warning)
    punctuation=[]
    for row in rows:
        if row['translation']==row['source']:continue
        text=re.sub(r'@C.{4}|@P|@N|@',' ',row['translation'])
        for rule,pattern in [('period_after_ellipsis_or_tilde',r'[…~]\.'),('ascii_ellipsis',r'\.{3}'),('fullwidth_basic_punctuation',r'[，．！？：；（）]')]:
            if re.search(pattern,text):punctuation.append({'id':row['id'],'rule':rule})
    proposals_path=ROOT/'translation/stage7_proposals.json'
    proposals=read('translation/stage7_proposals.json')['changes'] if proposals_path.exists() else []
    for ident,after,reason in ([] if proposals else [
        ('main/07/033','예쁜 에일 잔','エール(에일)을 일반적인 맥주로 넓힌 표현을 원문의 종류명으로 되돌림.'),
        ('main/07/039','작은 유리 상자','こばこ(작은 상자)의 크기 정보가 빠져 있어 복원.')]):
        row=byid[ident];term=next(t for t in terms if t['source']==row['source'])
        proposals.append({'id':ident,'source':row['source'],'before':row['translation'],'after':after,'reason':reason,
                          'source_sha256':thash(row['source']),'before_sha256':thash(row['translation']),
                          'glossary_change':{'id':term['id'],'before':term['korean'],'after':after},
                          'control_tokens_unchanged':tokens(row['translation'],row['renderer'])==tokens(after,row['renderer'])})
    for proposal in proposals:
        assert thash(byid[proposal['id']]['source'])==proposal['source_sha256']
        assert byid[proposal['id']]['translation'] in (proposal['before'],proposal['after'])
    applied=all(byid[p['id']]['translation']==p['after'] and next(t for t in terms if t['id']==p['glossary_change']['id'])['korean']==p['after'] for p in proposals)
    # Validate the proposed combination in memory, without touching live sources.
    candidate=copy.deepcopy(rows);candidate_terms=copy.deepcopy(terms)
    for proposal in proposals:
        next(r for r in candidate if r['id']==proposal['id'])['translation']=proposal['after']
        next(t for t in candidate_terms if t['id']==proposal['glossary_change']['id'])['korean']=proposal['after']
    candidate_errors,_=check(candidate,originals,candidate_terms)
    graphics=read('translation/graphics.json')['items']
    states=next(a for a in read('project.json')['assets'] if a['id']=='graphics-localization')['items']
    graphic_checks=[]
    for item in graphics:
        assert digest(item['png'])==item['original_png_sha256']
        result={'id':item['key'],'action':item['action'],'source_hash_matches':True}
        if item['action']=='replace_japanese_only':
            state=next(s for s in states if s['id']==item['key'])
            p=state['approved_path'];assert digest(p)==state['approved_sha256']
            with Image.open(ROOT/p) as im:
                assert im.size==(item['width'],item['height']);assert im.mode=='RGBA';assert im.format=='PNG';im.verify()
            with Image.open(ROOT/p) as im:im.load()
            result.update(png=p,size=[item['width'],item['height']],png_header_and_decode='pass',approved_hash_matches=True,target_texture_format=item['format'],texture_encoding='not_yet_validated')
        elif item['action']=='preserve_original':result['localized_copy_created']=False
        else:result['remaining']='Language identification deferred to gameplay by user.'
        graphic_checks.append(result)
    frozen=read('metadata/graphics_frozen_stage6.json')
    for p,h in frozen.items():assert digest(p)==h
    report={'source_sha256':digest('translation/messages.json'),'glossary_sha256':digest('translation/glossary.json'),
            'text_rows':len(rows),'errors':errors,'warnings':len(warnings),'warnings_with_current_hash_review':len(reviewed),
            'unreviewed_warnings':unreviewed,'punctuation_pattern_findings':punctuation,
            'layout_summary':read('work/translation/layout_stage7.json')['summary'],
            'graphics':graphic_checks,'frozen_files_and_backups_verified':len(frozen),
            'proposed_translation_changes':proposals,'candidate_integrity_errors':candidate_errors,
            'semantic_review_scope':'AI source/translation reading of all 363 entries; two treasure-name specificity/omission proposals. Not a proof of semantic perfection or runtime context.',
            'limitations':['Full Hangul glyph coverage and window capacities unavailable; all363 layout results unverified.',
                           'Punctuation automation covers explicit patterns only; sentence/voice judgments require reading.',
                           'PNG header/size checks do not validate GameCube texture headers, quantization, injection or runtime.',
                           'Wooden sign language and unresolved output contexts remain gameplay follow-ups.']}
    save('metadata/stage7_review.json',report)
    if not proposals_path.exists():save('translation/stage7_proposals.json',{'approval_source':'project.json','source_sha256':report['source_sha256'],'glossary_sha256':report['glossary_sha256'],'changes':proposals})
    lines=['# 7단계 검수 · 수정 대조표','',
           '승인·진행 상태는 `project.json`이 기준이다. 아래 두 수정안은 사용자 승인 후 본문과 용어집에 반영했다. ISO 빌드는 하지 않았다.' if applied else '승인·진행 상태는 `project.json`이 기준이다. 아래는 제안이며 본문과 용어집에는 아직 적용하지 않았다. ISO 빌드도 하지 않았다.','',
           '| ID | 일본어 원문 | 수정 전 | 수정 후 제안 | 이유 |','|---|---|---|---|---|']
    for p in proposals:lines.append(f"| {p['id']} | {p['source']} | {p['before']} | **{p['after']}** | {p['reason']} |")
    lines+=['','본문 두 항목과 대응하는 용어집 두 항목만 수정했다. 적용 근거는 `metadata/stage7_application.json`이다.' if applied else '두 항목은 승인된 용어집에도 같은 번역이 있으므로, 승인 시 해당 용어집 항목과 본문을 함께 바꾼다. 그 밖의 번역문은 유지한다.','',
            '## 검사 결과','',
            f'- 363항목: 태그·줄바꿈 순서·빈 번역·원문 ID/문자열 검사 오류 {len(errors)}건.',
            f'- 숫자·용어 경고 {len(warnings)}건: 기존 문맥 검토 기록과 현재 원문/번역 해시 일치 {len(reviewed)}건. 경고 자체를 삭제하거나 무조건 통과시키지 않았다.',
            f'- 명시 부호 패턴 검사: 말줄임표/물결 뒤 마침표, 점 3개, 전각 기본 부호 위반 {len(punctuation)}건. 문장 종결·호칭은 AI 대조 읽기 범위이며 기계적 의미 검증이 아니다.',
            '- 반영 후 태그·용어 무결성 검사 오류 0건.' if applied else '- 수정안은 메모리에서 태그·용어 무결성 검사 오류 0건. 실제 번역 JSON은 미수정.',
            '- 일본어 그래픽 4종: 확정 PNG 해시·헤더·크기·RGBA 검사 완료. 영어 보존 7종은 원본 해시 확인. 언어 미확정 목판 1종은 플레이 확인 대기.',
            f'- 확정 그림과 백업 {len(frozen)}파일 해시 확인. 게임 데이터·그림은 Git 추적 대상이 아니다.','',
            '## 남은 검증','',
            '- 전체 363항목의 화면 적합성 미확인: 한글 글리프 전체와 창별 한도가 아직 없다. 태그/줄 수 보존은 창에 들어간다는 뜻이 아니다.',
            '- PNG 규격 확인과 실제 RGB5A3/RGBA8 인코딩·헤더·재주입 검증은 구분한다. 후자는 빌드 준비/주입 단계에서 확인해야 한다.',
            '- 96×32 배너의 8픽셀 한글, 화자·색상 강조·미연결 창·목판은 실제 플레이 및 Dolphin 목록 확인이 남아 있다.',
            '- 번역 적용 빌드는 별도 명시 지시가 필요하다.','',
            '전체 1차 번역: [translation-review.md](translation-review.md). 검사 근거: `metadata/stage7_review.json`.','',
            '재현: `python -X utf8 tools/check_translation.py`, `python -X utf8 tools/check_text_layout.py translation/messages.json --output work/translation/layout_stage7.json` (미확인 종료 코드 2), `python -X utf8 tools/review_stage7.py`.']
    (ROOT/'docs/stage7-review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['text_rows','errors','warnings','warnings_with_current_hash_review','layout_summary','frozen_files_and_backups_verified','candidate_integrity_errors']},ensure_ascii=False))
    assert not errors and not candidate_errors and not unreviewed


if __name__=='__main__':main()
