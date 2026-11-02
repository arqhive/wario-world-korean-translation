"""Integration checks on private image copies; no emulator or original writes."""
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile
from file_patcher import scan,plan,run,file_sha,VERSION,DISC_MAX,RELEASE_NAME,BUILD_NAME
from inspect_discs import ROOT,save


def main():
    parent=ROOT/'work/file-patcher-tests';parent.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='run-',dir=parent))
    release=ROOT/'dist'/RELEASE_NAME;bundle=release/'patch-data.zip';exe=release/'WarioWorld_KO_Patcher.exe'
    source=ROOT/'Wario World (Japan).iso';variant=folder/'[배치 변경] 원본.gcm'
    assert not variant.exists();shutil.copyfile(source,variant)
    inv=json.loads((ROOT/'metadata/disc_inventory_jp.json').read_text(encoding='utf-8'))
    banner=next(x for x in inv['files'] if x['path']=='opening.bnr')
    # Move banner into the usual DOL destination, alter filler and trim the tail.
    filler=0x01000000
    assert all(filler+32<=a or filler>=b for a,b in scan(source)['occupied'])
    with variant.open('r+b') as f:
        f.seek(banner['offset']);data=f.read(banner['size']);f.seek(0x00cd8000);f.write(data)
        f.seek(inv['fst_offset']+banner['index']*12+4);f.write(struct.pack('>I',0x00cd8000))
        f.seek(filler);f.write(b'PADDING VARIANT TEST')
        last=max(x['offset']+x['size'] for x in inv['files'] if x['path']!='opening.bnr');f.truncate((last+31)&~31)
    original_hash=file_sha(source);variant_hash=file_sha(variant);assert variant_hash!=original_hash
    m,disc,changes,at=plan(variant,bundle,lambda _:None);assert at!=0x00cd8000
    gui_report=folder/'gui.json';report=folder/'exe-result.json';result=folder/'[검증] 한글.iso'
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    subprocess.run([str(exe),'--self-test-gui','--report',str(gui_report)],check=True,timeout=60,startupinfo=startup)
    subprocess.run([str(exe),'--input',str(variant),'--output',str(result),'--report',str(report)],check=True,timeout=120,startupinfo=startup)
    built=json.loads(report.read_text(encoding='utf-8'));assert built['unexpected_changes']==0 and file_sha(variant)==variant_hash
    assert built['size']==DISC_MAX and result.stat().st_size==DISC_MAX
    assert file_sha(source)==original_hash
    passes=['Windows executable: relocated banner + different filler + trimmed input','Standard output disc size','Fallback DOL placement','Input unchanged','Hidden GUI widgets/Tcl initialization']
    def rejects(label,call):
        try:call()
        except (ValueError,zipfile.BadZipFile,KeyError):passes.append(label)
        else:raise AssertionError('Unexpected success: '+label)
    rejects('Existing output refused',lambda:run(source,result,bundle,lambda _:None))
    rejects('Original path refused',lambda:run(source,source,bundle,lambda _:None))
    rejects('North American edition refused',lambda:plan(ROOT/'Wario World (USA).iso',bundle,lambda _:None))
    rejects('Already patched input refused',lambda:plan(result,bundle,lambda _:None))
    corrupt=folder/'corrupt-patch.zip'
    with zipfile.ZipFile(bundle) as old,zipfile.ZipFile(corrupt,'x') as new:
        for name in old.namelist():
            b=old.read(name)
            if name=='patches/00.wwd':b=b[:-1]+bytes([b[-1]^1])
            new.writestr(name,b)
    rejects('Corrupt delta refused',lambda:plan(source,corrupt,lambda _:None))
    with variant.open('r+b') as f:f.seek(0x00cd8000+40);b=f.read(1);f.seek(-1,1);f.write(bytes([b[0]^1]))
    rejects('Modified internal file refused',lambda:plan(variant,bundle,lambda _:None))
    truncated=folder/'truncated.iso'
    with source.open('rb') as f:truncated.write_bytes(f.read(128))
    rejects('Truncated image refused',lambda:plan(truncated,bundle,lambda _:None))
    assert not list(folder.glob('*.partial-*'))
    original_result=json.loads((ROOT/'metadata/file_patcher_original_test.json').read_text(encoding='utf-8'))
    reference=json.loads((ROOT/'metadata'/(BUILD_NAME+'_build.json')).read_text(encoding='utf-8'))
    assert original_result['output_sha256']==reference['sha256'];passes.append('Original-layout result exactly matches build ISO')
    save(ROOT/'metadata/file_patcher_tests.json',{'version':VERSION,'passed':passes,'count':len(passes),
         'exe_sha256':file_sha(exe),'bundle_sha256':file_sha(bundle),'variant_result':built,
         'gui':json.loads(gui_report.read_text(encoding='utf-8')),'limitations':['No real alternate dump supplied; layout/filler/trim differences were deliberately constructed.','GUI widgets initialized hidden; no manual click-through or visual UI inspection.','No game playback/hardware verification.']})
    print(json.dumps({'passed':passes,'count':len(passes)},ensure_ascii=False))


if __name__=='__main__':main()
