"""Show untouched source PNGs beside proposed wording. Does not edit images."""
import hashlib
import html
import json
from pathlib import Path
from inspect_discs import ROOT


def esc(s):
    return html.escape(s if s is not None else '〈판독 보류〉')


def main():
    data=json.loads((ROOT/'translation/graphics.json').read_text(encoding='utf8'))
    labels={'replace_japanese_only':'일본어 부분 교체안', 'preserve_original':'사용자 지정 · 원형 보존', 'defer_language_identification':'언어·내용 확인 보류 · 원형 보존'}
    counts={k:sum(i['action']==k for i in data['items']) for k in labels}
    summary=f"일본어 교체 대상 {counts['replace_japanese_only']}개 · 원형 보존 {counts['preserve_original']}개 · 언어 확인 보류 {counts['defer_language_identification']}개. 영어 그래픽과 혼합 그림의 영문 부분은 그대로 둡니다."
    blocks=[]
    doc=['# 그래픽 원본·번역안','',
         '승인 상태는 `project.json`에서 관리한다. 아래 이미지는 수정하지 않은 원본이며 옆 문구는 검토용 번역안이다. 모양·배경 작업은 규칙과 개별 문구 승인 뒤 진행한다.', '',
         summary, '', '규칙: [graphics-rules.md](graphics-rules.md). 원래 크기/확대 보기: [검토 페이지](../work/graphics/proposals.html).', '']
    for item in data['items']:
        path=ROOT/item['png'];assert hashlib.sha256(path.read_bytes()).hexdigest()==item['original_png_sha256']
        title=f'{item["label"]} · {item["width"]}×{item["height"]} · {item["format"]}'
        relative='../'+item['png'].removeprefix('work/')
        rows=''.join(f'<tr><td>{esc(a)}</td><td>{esc(b)}</td></tr>' for a,b in zip(item['source_lines'],item['translation_lines']))
        badge=labels[item['action']]
        notes=''.join(f'<li>{esc(n)}</li>' for n in item.get('notes',[]))
        blocks.append(f'<section id="{esc(item["key"])}"><h2>{esc(title)}</h2><p class="badge">{badge}</p><div class="picture"><a href="{esc(relative)}" target="_blank"><img src="{esc(relative)}" width="{item["width"]}" height="{item["height"]}" alt="{esc(item["label"])} 원본"></a></div><table><thead><tr><th>읽은 원문</th><th>한국어 제안</th></tr></thead><tbody>{rows}</tbody></table><p>{esc(item["plan"])}</p><ul>{notes}</ul></section>')
        doc += ['## '+title,'',badge,'',f'![{item["label"]} 원본](../{item["png"]})','',
                '| 읽은 원문 | 한국어 제안 |','| --- | --- |']
        doc += [f'| {esc(a)} | {esc(b)} |' for a,b in zip(item['source_lines'],item['translation_lines'])]
        doc += ['',item['plan'],'']+item.get('notes',[])+['']
    page='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>와리오 월드 · 그래픽 번역안</title>
<style>body{background:#202124;color:#eee;font:17px/1.65 system-ui;margin:32px auto;padding:0 24px;max-width:1000px}header{border-bottom:1px solid #777}h1{font-size:30px}h2{font-size:22px}section{margin:40px 0;padding:22px;background:#303134;border-radius:10px}.badge{color:#f5ce62}.picture{overflow:auto;padding:16px;background:repeating-conic-gradient(#666 0% 25%,#999 0% 50%) 0/16px 16px}.picture img{display:block;max-width:none}body.zoom img{width:auto;height:auto;transform:scale(2);transform-origin:top left;margin-right:100%;margin-bottom:var(--extra,0)}table{border-collapse:collapse;width:100%;margin-top:18px}td,th{border-bottom:1px solid #666;text-align:left;padding:9px;vertical-align:top;width:50%}a{color:#91caff}button{font:inherit;padding:8px 16px;margin:10px 10px 15px 0}small{color:#ccc}</style>
<header><h1>와리오 월드 · 그래픽 번역안</h1><p>원본을 보고 문구와 보존 범위를 확인하는 단계입니다. 한글로 편집한 시안은 아직 없습니다.</p><p>__SCOPE_SUMMARY__</p><p><a href="../../docs/graphics-rules.md">그래픽 작업 규칙</a> · <a href="../../docs/graphics-proposals.md">문서로 보기</a></p><button id="native">원래 크기</button><button id="large">2배 확대</button><small>클릭하면 원본 PNG를 엽니다. 체크 무늬는 투명도 확인용이며 파일에 포함되지 않습니다.</small></header>'''+''.join(blocks)+'''<script>document.querySelector('#native').onclick=()=>document.querySelectorAll('img').forEach(i=>{i.style.width=i.getAttribute('width')+'px';i.style.height=i.getAttribute('height')+'px'});document.querySelector('#large').onclick=()=>document.querySelectorAll('img').forEach(i=>{i.style.width=2*i.getAttribute('width')+'px';i.style.height=2*i.getAttribute('height')+'px'});</script></html>'''
    page=page.replace('__SCOPE_SUMMARY__',esc(summary))
    page=page.replace('한국어 제안','교체안 / 보존 원문')
    doc=[line.replace('한국어 제안','교체안 / 보존 원문') for line in doc]
    out=ROOT/'work/graphics';out.mkdir(parents=True,exist_ok=True)
    (out/'proposals.html').write_text(page,encoding='utf8')
    (ROOT/'docs/graphics-proposals.md').write_text('\n'.join(doc).rstrip()+'\n',encoding='utf8')
    print(f'{len(data["items"])} original PNG hashes verified; proposals rendered without image changes.')


if __name__=='__main__':main()
