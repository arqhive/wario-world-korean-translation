"""Generate a source/first-draft review table; does not alter translation or build."""
import collections
import html
import json
from inspect_discs import ROOT


def display(s):
    if not s.strip():return '〈원문 공백 유지〉'
    return html.escape(s).replace('|','&#124;').replace('\r','').replace('\n','<br>')


def main():
    rows=json.loads((ROOT/'translation/messages.json').read_text(encoding='utf-8'))['messages']
    groups=collections.defaultdict(list)
    for r in rows:
        key='/'.join(r['id'].split('/')[:-1])
        groups[key].append(r)
    report=['# 일본판 원문 · 한국어 1차 번역 대조표','',
        '승인·현재 상태는 `project.json`이 기준이다. 번역 원본은 `translation/messages.json`이다. 이번 작업은 빈 번역 칸을 채운 첫 번역이며 기존 확정 본문 번역의 수정본이 아니다.', '',
        f'전체 {len(rows)}항목: 번역 {sum(r["source"]!=r["translation"] for r in rows)}, 원문 유지 {sum(r["source"]==r["translation"] for r in rows)}. 유지 항목은 인명·회사명·권리 문구·공백·물음표·날짜/시간 자리표시자다.', '',
        '원문의 정보·조건·강조·말투를 보존하고 임의 설명을 추가하지 않는 원칙으로 작성했다. 사람 검수 전 초안이며 의미 보존을 기계 검사만으로 보증하지 않는다.', '',
        '`@`는 일반 출력기의 줄 구분, `@P`는 별도 대사의 줄 구분, `@N`은 페이지 구분, `@C` 뒤 4문자는 색 인수다. 표에서는 검사할 수 있도록 그대로 보인다. 원문 줄·페이지 수를 유지했으며 실제 화면 적합성은 미확인이다.', '',
        '오프닝 main/15는 여러 항목이 하나의 문장을 이룬다. 연속해서 읽어 검토한다. 보물 이름은 승인된 일본판 용어집을 적용했다. GBA 연결 안내는 GC 화면에 나오는 문구로 이번 범위에 포함했다.', '',
        '검사 근거: `metadata/translation_checks.json`, 경고 검토: `metadata/translation_review_notes.json`. 글리프·창 한도 검사는 `work/translation/layout_v01.json`에 모두 미확인으로 기록했다.', '',
        '실행 문맥 확인: 요정별 화자 연결, 제어 태그 색 범위의 화면 표시, 시점에 따른 「이/그/저」, 모호한 동작·배너/크레디트 한글 출력은 플레이·주입 단계에서 확인한다. 그때 원문 의미를 줄여 해결하지 않는다.', '']
    for group,items in groups.items():
        report += ['## '+group,'','| ID | 일본판 원문 | 한국어 초안 |','| --- | --- | --- |']
        report += [f'| {r["id"]} | {display(r["source"])} | {display(r["translation"])} |' for r in items]
        report += ['']
    (ROOT/'docs/translation-review.md').write_text('\n'.join(report).rstrip()+'\n',encoding='utf-8')
    print(f'Rendered {len(rows)} rows without altering source JSON.')


if __name__=='__main__':main()
