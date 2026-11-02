"""Exploratory byte scans; candidate strings are not confirmed messages."""
import json
import re
from inspect_discs import ROOT


def main():
    rs=json.loads((ROOT/'metadata/rsc_inventory.json').read_text(encoding='utf8'))['editions']
    for ed in rs:
        region=ed['edition']
        inv=json.loads((ROOT/f'metadata/disc_inventory_{region}.json').read_text(encoding='utf8'))
        name='Wario World (Japan).iso' if region=='jp' else 'Wario World (USA).iso'
        with (ROOT/name).open('rb') as f:
            print(region)
            for a in ed['archives']:
                if a['path'] not in ['rsc/UNIV.RSC','rsc/CTT.RSC']:continue
                off=next(x['offset'] for x in inv['files'] if x['path']==a['path']);print(a['path'])
                for m in a['members']:
                    f.seek(off+m['header_offset']+32);b=f.read(m['size'])
                    out=ROOT/'work/analysis'/region/a['path'].replace('/','_')/(f"{m['index']:03}.bin")
                    out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(b)
                    if m['type'] in [0,1,10,13]:print(m['index'],m['type'],len(b),b[:48].hex(' '))
                    pats=re.findall(rb'(?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]){8,}',b)
                    if pats:print('SJIS',m['index'],len(pats),[p.decode('cp932',errors='replace')[:90] for p in pats[:2]])
                    pats=re.findall(rb'[A-Za-z][A-Za-z ,!?.]{15,}',b)
                    if pats:print('ASCII',m['index'],len(pats),pats[:2])


if __name__=='__main__':main()
