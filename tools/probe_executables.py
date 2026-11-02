"""Executable extraction and conservative string candidates, not a text parser."""
import json
import re
from inspect_discs import ROOT,save


def main():
    for region,name in [('jp','Wario World (Japan).iso'),('us','Wario World (USA).iso')]:
        inv=json.loads((ROOT/f'metadata/disc_inventory_{region}.json').read_text(encoding='utf8'))
        source=[dict(path='main.dol',offset=inv['dol']['offset'],size=inv['dol']['size'])]+[x for x in inv['files'] if x['path'].endswith('.rel')]
        rows=[]
        with (ROOT/name).open('rb') as f:
            for item in source:
                f.seek(item['offset']);b=f.read(item['size'])
                out=ROOT/'work/analysis'/region/item['path'];out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(b)
                for encoding,pattern in [('cp932',rb'(?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]){5,}'),('ascii',rb'[A-Za-z][A-Za-z ,!?\x27.]{15,}')]:
                    for m in re.finditer(pattern,b):
                        try:s=m.group().decode(encoding)
                        except UnicodeDecodeError:continue
                        if encoding=='cp932' and sum('\u3040'<=c<='\u30ff' for c in s)<len(s)//2:continue
                        rows.append(dict(file=item['path'],offset=m.start(),encoding=encoding,text=s))
                print(region,item['path'],'candidates',sum(x['file']==item['path'] for x in rows))
        save(ROOT/'work/analysis'/region/'executable_candidates.json',rows)
        print('examples',rows[:18])


if __name__=='__main__':main()
