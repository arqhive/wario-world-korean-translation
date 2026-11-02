"""Package only explicitly allowed patcher files; verify the extracted executable."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from file_patcher import VERSION,RELEASE_NAME,file_sha
from inspect_discs import ROOT,save


def main():
    name=RELEASE_NAME
    folder=ROOT/'dist'/name;archive=ROOT/'dist'/(name+'.zip')
    assert not archive.exists(), 'Preserve existing release ZIP; choose a new version.'
    copies={'file_patcher.py':'tools/file_patcher.py','README.md':'docs/release-readme.md',
            'THIRD_PARTY.txt':'licenses/patcher/THIRD_PARTY.txt','licenses/GmarketSans-OFL.txt':'licenses/GmarketSans-OFL.txt'}
    for n in ['OpenSSL-LICENSE.txt','PyInstaller-COPYING.txt','Python-LICENSE.txt','Tcl-Tk-license.terms']:
        copies['licenses/'+n]='licenses/patcher/'+n
    for dst,src in copies.items():
        (folder/dst).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/src,folder/dst)
    names=sorted(list(copies)+['WarioWorld_KO_Patcher.exe','patch-data.zip'])
    hashes={n:file_sha(folder/n) for n in names}
    (folder/'SHA256SUMS.txt').write_text(''.join(f'{h}  {n}\n' for n,h in hashes.items()),encoding='utf-8')
    names.append('SHA256SUMS.txt')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n in names:
            info=zipfile.ZipInfo(name+'/'+n,date_time=(2026,11,2,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,(folder/n).read_bytes())
    parent=ROOT/'work/release-unpack-tests';parent.mkdir(parents=True,exist_ok=True)
    checkdir=Path(tempfile.mkdtemp(prefix='run-',dir=parent))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert set(z.namelist())=={name+'/'+n for n in names}
        z.extractall(checkdir) # Archive just created from the fixed allowlist above.
    unpacked=checkdir/name
    for n,h in hashes.items():assert file_sha(unpacked/n)==h
    report=checkdir/'compatibility.json'
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    subprocess.run([str(unpacked/'WarioWorld_KO_Patcher.exe'),'--input',str(ROOT/'Wario World (Japan).iso'),
                    '--check','--report',str(report)],check=True,timeout=60,startupinfo=startup)
    result=json.loads(report.read_text(encoding='utf-8'));assert result['compatible'] and result['file_count']==245
    save(ROOT/'metadata'/f'release_{VERSION}.json',{'version':VERSION,'archive':str(archive.relative_to(ROOT)),
        'size':archive.stat().st_size,'sha256':file_sha(archive),'files':hashes,
        'archive_crc_verified':True,'unpacked_executable_default_bundle_check':result,
        'publicly_uploaded':False})
    print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'sha256':file_sha(archive)},ensure_ascii=False))


if __name__=='__main__':main()
