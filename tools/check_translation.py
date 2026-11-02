"""Read-only source/translation integrity checks; never certifies meaning or fit."""
import collections
import json
import re
import unicodedata
from inspect_discs import ROOT, save


def tokens(text, renderer):
    return re.findall(r'@C.{4}|@P|@N|@|\r\n|(?<!\r)\n', text) if renderer == 'tagged' else re.findall(r'@|\r\n|(?<!\r)\n', text)


def check(rows, originals, glossary):
    errors=[];warnings=[]
    ids=[r['id'] for r in rows]
    if len(set(ids))!=len(ids):errors.append({'issue':'duplicate_ids'})
    if set(ids)!=set(originals):errors.append({'issue':'source_id_set_changed'})
    for r in rows:
        ident=r['id'];src=r['source'];ko=r['translation'];renderer=r['renderer']
        if ident not in originals or src!=originals[ident]:errors.append({'id':ident,'issue':'source_changed'})
        if not ko:errors.append({'id':ident,'issue':'empty_translation'})
        if tokens(src,renderer)!=tokens(ko,renderer):errors.append({'id':ident,'issue':'control_or_line_sequence_changed'})
        if not src.strip() or src=='?' or ident in ['main/18/000','main/18/001','main/18/002','main/18/005']:
            if ko!=src:errors.append({'id':ident,'issue':'placeholder_changed'})
        if re.search('[ぁ-ヿ一-鿿]',ko):warnings.append({'id':ident,'issue':'japanese_characters_remain'})
        a=re.findall(r'\d+',unicodedata.normalize('NFKC',re.sub(r'@C.{4}','',src)))
        b=re.findall(r'\d+',unicodedata.normalize('NFKC',re.sub(r'@C.{4}','',ko)))
        if a!=b:warnings.append({'id':ident,'issue':'numeric_text_differs','source':a,'translation':b})
        if re.search(r'[…~][.]',ko):errors.append({'id':ident,'issue':'period_after_ellipsis_or_tilde'})
        for term in glossary:
            if term['source'] in src and term['korean'] not in ko:
                warnings.append({'id':ident,'issue':'glossary_candidate','source_term':term['source'],'expected':term['korean']})
    return errors,warnings


def main():
    # Structured source extracted independently; includes IDs from both text readers.
    original=json.loads((ROOT/'work/extraction/jp/messages.json').read_text(encoding='utf-8'))
    rows=json.loads((ROOT/'translation/messages.json').read_text(encoding='utf-8'))['messages']
    glossary=json.loads((ROOT/'translation/glossary.json').read_text(encoding='utf-8'))['terms']
    originals={r['id']:r['source'] for r in original['messages']}
    errors,warnings=check(rows,originals,glossary)
    report={'rows':len(rows),'nonempty_translations':sum(bool(r['translation']) for r in rows),
            'unchanged_entries':sum(r['source']==r['translation'] for r in rows),
            'errors':errors,'warnings':warnings,'warning_counts':dict(collections.Counter(w['issue'] for w in warnings)),
            'limitations':['Not a semantic or omission proof','Glossary substring matches require contextual review',
                          'Does not certify glyph availability, window fit or binary reinsertion']}
    save(ROOT/'metadata/translation_checks.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='warnings'},ensure_ascii=False))
    raise SystemExit(bool(errors))


if __name__=='__main__':main()
