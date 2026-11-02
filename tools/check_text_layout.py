"""Fail-closed, read-only checker for measured plain '@' text.

Input: {messages:[{id, translation}]} or a list of those objects.
Optional limits: {ID: {max_line_width_px, max_lines, evidence}}.
Limits must be confirmed and expressed in unscaled text-texture pixels.
Returns 0 only when every nonempty translation has verified limits and fits;
1 for errors/overflow, 2 for incomplete coverage or untranslated input.
"""
import argparse
import json
from collections import Counter
from pathlib import Path
from inspect_discs import ROOT
from measure_text_layout import measured_shape


def check_row(row, metadata, limits):
    ident=row['id'];text=row.get('translation','')
    result={'id':ident,'status':'unverified','issues':[]}
    if not text:
        return {**result,'status':'untranslated','issues':['empty_translation']}
    original=next((r for r in metadata['measurements'] if r['id']==ident),None)
    if original is None:
        return {**result,'issues':['unmeasured_message']}
    if row.get('renderer','plain_at')!='plain_at':
        return {**result,'issues':['unimplemented_renderer_or_tags']}
    widths=metadata['original_widths_px']|metadata['probe_korean_widths_px']
    unknown=sorted(set(text)-set(widths)-{'@'})
    if unknown:
        result['unsupported_characters']=unknown
        result['issues'].append('glyph_not_available_or_width_unmeasured')
        # No guessed Hangul widths: this is a readiness check, not an estimate.
        return result
    shape=measured_shape(text,widths);result.update(shape)
    result['source_comparison']={
        'width_delta_px':shape['max_line_width_px']-original['max_line_width_px'],
        'line_delta':shape['line_count']-original['line_count'],
        'note':'Source dimensions are not capacity limits.'}
    if original['renderer_binding']=='pending':result['issues'].append('renderer_binding_unverified')
    if original['dynamic_content']:result['issues'].append('dynamic_content_unverified')
    if ident.startswith('main/19/') and shape['line_count']!=original['line_count']:
        result['issues'].append('selection_count_changed')
        result['status']='error'
    limit=limits.get(ident)
    if not limit or not limit.get('evidence') or not isinstance(limit.get('max_line_width_px'),int) or not isinstance(limit.get('max_lines'),int) or limit['max_line_width_px']<=0 or limit['max_lines']<=0:
        result['issues'].append('window_limits_unverified')
    else:
        if shape['max_line_width_px']>limit['max_line_width_px']:result['issues'].append('width_overflow')
        if shape['line_count']>limit['max_lines']:result['issues'].append('line_overflow')
        if any(x.endswith('_overflow') for x in result['issues']):result['status']='overflow'
    if not result['issues']:result['status']='pass'
    return result


def self_test(metadata):
    # Synthetic capacities test the actual fail-closed boundary behavior.
    ident='main/19/003';row={'id':ident,'translation':'시작@취소'}
    limits={ident:{'max_line_width_px':40,'max_lines':2,'evidence':'synthetic test, not game limit'}}
    assert check_row(row,metadata,limits)['status']=='pass'
    limits[ident]['max_line_width_px']=39
    assert check_row(row,metadata,limits)['status']=='overflow'
    limits[ident]['max_line_width_px']=40;limits[ident]['max_lines']=1
    assert 'line_overflow' in check_row(row,metadata,limits)['issues']
    assert check_row(row,metadata,{})['status']=='unverified'
    assert check_row({'id':ident,'translation':'없는글자'},metadata,limits)['status']=='unverified'
    assert 'selection_count_changed' in check_row({'id':ident,'translation':'시작'},metadata,limits)['issues']
    assert check_row({'id':'new/id','translation':'시작'},metadata,limits)['status']=='unverified'
    assert check_row({'id':ident,'translation':''},metadata,limits)['status']=='untranslated'
    print('8 fail-closed/boundary checks passed; no game limits certified.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',nargs='?',type=Path);p.add_argument('--limits',type=Path)
    p.add_argument('--self-test',action='store_true');p.add_argument('--output',type=Path)
    args=p.parse_args()
    metadata=json.loads((ROOT/'metadata/text_layout_measurements.json').read_text(encoding='utf8'))
    if args.self_test:self_test(metadata);return
    if args.input is None:p.error('input is required without --self-test')
    data=json.loads(args.input.read_text(encoding='utf8'))
    rows=data['messages'] if isinstance(data,dict) else data
    if len({r['id'] for r in rows})!=len(rows):p.error('duplicate message IDs')
    limits=json.loads(args.limits.read_text(encoding='utf8')) if args.limits else {}
    results=[check_row(r,metadata,limits) for r in rows]
    counts=dict(Counter(r['status'] for r in results))
    report={'units':metadata['units'],'summary':counts,'results':results}
    if args.output:
        resolved=args.output.resolve()
        work=(ROOT/'work').resolve()
        if not resolved.is_relative_to(work):p.error('--output must be inside project work/ to protect originals and sources')
        if resolved==args.input.resolve() or (args.limits and resolved==args.limits.resolve()):p.error('output must not overwrite input or limits')
        resolved.parent.mkdir(parents=True,exist_ok=True)
        resolved.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps(counts,ensure_ascii=False))
    else:print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(1 if counts.get('overflow') or counts.get('error') else (2 if not rows or any(r['status']!='pass' for r in results) else 0))


if __name__=='__main__':main()
