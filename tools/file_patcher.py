"""Standalone file-addressed GameCube delta patcher. Python standard library only."""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import shutil
import struct
import sys
import threading
import uuid
import zipfile
import zlib

VERSION='1.0f'
RELEASE_NAME='GWWJ_KPatch_v'+VERSION
BUILD_NAME='WarioWorld_KO_v1_0f'
DISC_MAX=1459978240
CHUNK=8*1024*1024


def require(condition,message):
    if not condition:raise ValueError(message)


def sha(data):return hashlib.sha256(data).hexdigest()


def file_sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def region(f,offset,length):
    f.seek(offset);b=f.read(length);require(len(b)==length,'파일이 중간에 잘렸습니다.');return b


def u32(b,p=0):return struct.unpack_from('>I',b,p)[0]


def scan(path):
    size=Path(path).stat().st_size
    require(size<=DISC_MAX,'표준 GameCube 디스크보다 큰 이미지는 지원하지 않습니다.')
    with Path(path).open('rb') as f:
        h=region(f,0,0x2440)
        require(h[:6]==b'GWWJ01' and h[6:8]==b'\0\0','지원 판본은 일본판 GWWJ01 revision 0입니다.')
        require(u32(h,0x1c)==0xc2339f3d,'압축되지 않은 GameCube ISO/GCM을 선택하세요. RVZ/GCZ는 먼저 ISO로 변환하세요.')
        do,fo,fs,fmax=struct.unpack_from('>4I',h,0x420)
        require(0<fs<=fmax<=4*1024*1024 and fo+fmax<=size,'FST 범위가 올바르지 않습니다.')
        app_header=region(f,0x2440,32)
        app_end=0x2460+u32(app_header,0x14)+u32(app_header,0x18)
        require(0x2460<=app_end<=size,'Apploader 범위 오류')
        dh=region(f,do,256);ends=[]
        for i in range(18):
            off,n=u32(dh,i*4),u32(dh,0x90+i*4)
            if n:
                require(off>=256 and do+off+n<=size,'DOL 섹션 범위 오류');ends.append(off+n)
        require(bool(ends),'DOL이 비어 있습니다.');ds=max(ends)
        fst=region(f,fo,fs);count=u32(fst,8)
        require(fst[0]==1 and u32(fst,4)==0 and 1<=count<=fs//12,'FST 루트 오류')
        names=fst[count*12:];stack=[(count,'',0)];files={}
        for i in range(1,count):
            while i>=stack[-1][0]:stack.pop()
            a,b,c=struct.unpack_from('>III',fst,i*12);kind=a>>24;n=a&0xffffff
            require(kind in (0,1) and n<len(names),'FST 항목 오류')
            end=names.find(b'\0',n);require(end>n,'FST 파일명 오류')
            name=names[n:end].decode('cp932')
            require(name not in ('.','..') and '/' not in name and '\\' not in name,'FST 경로 오류')
            path=stack[-1][1]+name
            if kind:
                require(b==stack[-1][2] and i<c<=stack[-1][0],'FST 디렉터리 오류');stack.append((c,path+'/',i))
            else:
                require(path not in files and b+c<=size,'중복 경로 또는 파일 범위 오류');files[path]={'offset':b,'size':c,'index':i}
        occupied=[(0,app_end),(do,do+ds),(fo,fo+fmax)]+[(r['offset'],r['offset']+r['size']) for r in files.values() if r['size']]
        occupied.sort()
        for a,b in zip(occupied,occupied[1:]):require(a[1]<=b[0],'겹치는 디스크 영역은 지원하지 않습니다.')
        return {'size':size,'dol':{'offset':do,'size':ds},'files':files,'occupied':occupied,'app_end':app_end,
                'fst':{'offset':fo,'size':fs,'max':fmax,'raw':fst},
                'apploader_sha256':sha(region(f,0x2440,app_end-0x2440))}


def relayout(disc,dol_len):
    """Keep header, apploader, DOL, FST, files in disc order.

    UWUVCI's NKit step fails to verify an image whose DOL sits in a gap after
    the files, so the grown DOL stays at its original offset, the FST follows
    it, and the few files in the way move to the first 0x8000-aligned gap.
    """
    do=disc['dol']['offset'];fst=disc['fst'];newfst=(do+dol_len+0xff)&~0xff;fend=newfst+fst['max']
    moved=sorted((r['index'],p) for p,r in disc['files'].items() if r['size'] and r['offset']<fend and r['offset']+r['size']>do)
    need=0
    for _,p in moved:need=((need+31)&~31)+disc['files'][p]['size']
    occupied=sorted([(0,disc['app_end']),(do,fend)]+[(r['offset'],r['offset']+r['size']) for p,r in disc['files'].items()
                    if r['size'] and p not in dict((p,0) for _,p in moved)])
    start=None;end=0
    for a,b in occupied+[(DISC_MAX,DISC_MAX)]:
        at=(end+0x7fff)&~0x7fff
        if at>=fend and at+need<=a:start=at;break
        end=max(end,b)
    require(start is not None,'파일을 옮길 빈 공간이 없습니다.')
    raw=bytearray(fst['raw']);positions={};at=start
    for i,p in moved:
        positions[p]=at;struct.pack_into('>I',raw,i*12+4,at);at=((at+disc['files'][p]['size'])+31)&~31
    return newfst,bytes(raw),positions


def apply_delta(old,packed,expected_size):
    # Only changed XOR bytes are shipped. Unchanged original bytes come from input.
    require(expected_size<=16*1024*1024,'패치 대상이 너무 큽니다.')
    dec=zlib.decompressobj();raw=dec.decompress(packed,64*1024*1024)
    require(dec.eof and not dec.unused_data and not dec.unconsumed_tail,'차분 압축 데이터 오류')
    require(raw[:4]==b'WWD1' and len(raw)>=16,'차분 형식 오류')
    oldsize,newsize,count=struct.unpack_from('>III',raw,4)
    require(oldsize==len(old) and newsize==expected_size,'차분 파일 크기 오류')
    out=bytearray(old[:newsize]);out.extend(b'\0'*(newsize-len(out)))
    p=16;last=0
    for _ in range(count):
        require(p+8<=len(raw),'차분 레코드 손상');at,n=struct.unpack_from('>II',raw,p);p+=8
        require(last<=at and 0<n<=newsize-at and p+n<=len(raw),'차분 범위 오류')
        out[at:at+n]=bytes(a^b for a,b in zip(out[at:at+n],raw[p:p+n]));p+=n;last=at+n
    require(p==len(raw),'차분 뒤에 불필요한 데이터가 있습니다.');return bytes(out)


def load_patch(bundle):
    with zipfile.ZipFile(bundle) as z:
        require(len(z.namelist())==len(set(z.namelist())),'중복 패치 항목')
        require(z.getinfo('manifest.json').file_size<1024*1024,'목록 크기 오류')
        m=json.loads(z.read('manifest.json'))
        require(m['format']=='wario-file-delta-v1' and m['version']==VERSION,'지원하지 않는 패처 버전입니다.')
        blobs={}
        for r in m['patches']:
            require(r['target'] not in blobs,'중복 패치 대상')
            require(z.getinfo(r['delta']).file_size<16*1024*1024,'차분 크기 오류')
            b=z.read(r['delta']);require(sha(b)==r['delta_sha256'],'패치 파일이 손상되었습니다.');blobs[r['target']]=b
    return m,blobs


def plan(source,bundle,log=print):
    m,blobs=load_patch(bundle);disc=scan(source)
    require(disc['apploader_sha256']==m['apploader_sha256'],'Apploader가 원본과 다릅니다.')
    expected=m['files'];require(set(disc['files'])==set(expected),'디스크 파일 목록이 지원 판본과 다릅니다.')
    targets={r['target']:r for r in m['patches']};updates={}
    with Path(source).open('rb') as f:
        for i,(name,r) in enumerate(disc['files'].items()):
            b=region(f,r['offset'],r['size']);e=expected[name]
            require(len(b)==e['size'] and sha(b)==e['sha256'],f'원본 파일 불일치: {name}\n다른 판본·수정본·이미 패치된 이미지는 적용할 수 없습니다.')
            if name in targets:
                t=targets[name];new=apply_delta(b,blobs[name],t['size'])
                require(len(new)==len(b) and sha(new)==t['sha256'],f'패치 결과 검증 실패: {name}');updates[name]=new
            if i%40==0:log(f'원본 내부 파일 확인: {i+1}/{len(expected)}')
        b=region(f,disc['dol']['offset'],disc['dol']['size'])
        require(len(b)==m['dol']['size'] and sha(b)==m['dol']['sha256'],'실행 파일(DOL)이 지원 원본과 다릅니다.')
        t=targets['@main.dol'];dol=apply_delta(b,blobs['@main.dol'],t['size']);require(sha(dol)==t['sha256'],'DOL 패치 검증 실패')
        at=disc['dol']['offset'];newfst,fst,positions=relayout(disc,len(dol))
        moved={n:updates.get(n) or region(f,disc['files'][n]['offset'],disc['files'][n]['size']) for n in positions}
    changes=[(0x420,struct.pack('>II',at,newfst)),(at,dol),(newfst,fst)]
    changes+=[(positions.get(n,disc['files'][n]['offset']),b) for n,b in updates.items() if n not in positions]
    changes+=[(positions[n],b) for n,b in moved.items()]
    changes.sort();require(all(a+len(b)<=c for (a,b),(c,_) in zip(changes,changes[1:])),'패치 영역 중복')
    return m,disc,changes,at


def run(source,output,bundle,log=print,check_only=False):
    source=Path(source).resolve();output=Path(output).resolve() if output else None
    require(source.is_file(),'원본 이미지를 찾을 수 없습니다.')
    if not check_only:
        require(output is not None and output!=source,'원본과 다른 저장 경로를 선택하세요.')
        require(not output.exists(),'저장할 파일이 이미 있습니다. 다른 이름을 선택하세요.')
        require(output.parent.is_dir(),'저장 폴더가 없습니다.')
    m,disc,changes,at=plan(source,bundle,log)
    if check_only:return {'compatible':True,'file_count':len(disc['files']),'dol_destination':at}
    # Normalize trimmed inputs to the standard disc size; added tail bytes are zero.
    outsize=DISC_MAX
    require(shutil.disk_usage(output.parent).free>=outsize+16*1024*1024,'저장 공간이 부족합니다.')
    source_hash=file_sha(source);tmp=output.with_name(output.name+'.partial-'+uuid.uuid4().hex)
    def overlay(block,pos):
        b=bytearray(block)
        for start,data in changes:
            lo=max(pos,start);hi=min(pos+len(b),start+len(data))
            if lo<hi:b[lo-pos:hi-pos]=data[lo-start:hi-start]
        return bytes(b)
    copyhash=hashlib.sha256();out_hash=hashlib.sha256()
    try:
        log('새 ISO 생성 중…')
        with source.open('rb') as inp,tmp.open('xb') as out:
            pos=0
            while pos<outsize:
                n=min(CHUNK,outsize-pos);b=inp.read(min(n,max(0,disc['size']-pos)));copyhash.update(b)
                out.write(overlay(b+b'\0'*(n-len(b)),pos));pos+=n
        require(copyhash.hexdigest()==source_hash,'작업 중 원본 파일이 변경되었습니다.')
        log('전체 이미지와 내부 파일 재검증 중…')
        with source.open('rb') as inp,tmp.open('rb') as built:
            pos=0;again=hashlib.sha256()
            while pos<outsize:
                n=min(CHUNK,outsize-pos);old=inp.read(min(n,max(0,disc['size']-pos)));again.update(old);new=built.read(n)
                require(new==overlay(old+b'\0'*(n-len(old)),pos),'예상 범위 밖 데이터 변경 또는 쓰기 오류');out_hash.update(new);pos+=n
            require(not built.read(1) and again.hexdigest()==source_hash,'이미지 길이 또는 원본 변경 오류')
        actual=scan(tmp);targets={r['target']:r for r in m['patches']}
        with tmp.open('rb') as f:
            for name,r in actual['files'].items():
                e=targets.get(name,m['files'][name]);require(sha(region(f,r['offset'],r['size']))==e['sha256'],f'재독출 오류: {name}')
            r=actual['dol'];require(sha(region(f,r['offset'],r['size']))==targets['@main.dol']['sha256'],'DOL 재독출 오류')
        require(not output.exists(),'작업 중 같은 이름의 파일이 생겼습니다.')
        # Windows rename refuses an existing destination; this product targets Windows.
        tmp.rename(output)
        result={'version':VERSION,'source':str(source),'output':str(output),'source_sha256':source_hash,'output_sha256':out_hash.hexdigest(),
                'size':outsize,'patched_files':len(targets),'internal_files_verified':len(actual['files']),'unexpected_changes':0,'runtime_tested':False}
        log('완료: '+str(output));return result
    finally:
        if tmp.exists():tmp.unlink() # Only our unique newly created temporary file.


def gui(bundle,self_test=False):
    import tkinter as tk
    from tkinter import filedialog,messagebox,ttk
    root=tk.Tk();root.title('와리오 월드 한글 패처 '+VERSION);root.geometry('650x370')
    if self_test:root.withdraw()
    src=tk.StringVar();dst=tk.StringVar();events=queue.Queue()
    ttk.Label(root,text='일본판 ISO/GCM → 한글 ISO',font=('',14,'bold')).pack(pady=(18,5))
    ttk.Label(root,text='원본을 보존하며 새 파일로 저장합니다. RVZ/GCZ는 먼저 ISO로 변환하세요.').pack()
    def choose():
        p=filedialog.askopenfilename(filetypes=[('GameCube ISO/GCM','*.iso *.gcm'),('모든 파일','*.*')])
        if p:src.set(p);q=Path(p);dst.set(str(q.with_name(q.stem+'_KO_'+VERSION+'.iso')))
    def destination():
        p=filedialog.asksaveasfilename(defaultextension='.iso',filetypes=[('GameCube ISO','*.iso')])
        if p:dst.set(p)
    for label,var,cmd in [('원본',src,choose),('저장',dst,destination)]:
        frame=ttk.Frame(root);frame.pack(fill='x',padx=20,pady=8);ttk.Label(frame,text=label,width=5).pack(side='left');ttk.Entry(frame,textvariable=var).pack(side='left',expand=True,fill='x');ttk.Button(frame,text='찾기',command=cmd).pack(side='right',padx=(6,0))
    status=tk.StringVar(value='원본 이미지를 선택하세요.');ttk.Label(root,textvariable=status,wraplength=605).pack(padx=20,pady=10)
    bar=ttk.Progressbar(root,mode='indeterminate');bar.pack(fill='x',padx=20)
    busy=[False]
    def start():
        if not src.get() or not dst.get():messagebox.showerror('입력 필요','원본과 저장 경로를 선택하세요.');return
        a,b=src.get(),dst.get();busy[0]=True;button.config(state='disabled');bar.start()
        def worker():
            try:result=run(a,b,bundle,lambda s:events.put(('log',s)));events.put(('done',result))
            except Exception as e:events.put(('error',str(e)))
        threading.Thread(target=worker,daemon=True).start()
    button=ttk.Button(root,text='한글 패치 적용',command=start);button.pack(pady=15)
    def poll():
        while not events.empty():
            kind,value=events.get()
            if kind=='log':status.set(value)
            else:
                busy[0]=False;bar.stop();button.config(state='normal')
                if kind=='error':status.set('적용하지 못했습니다.');messagebox.showerror('패치 오류',value)
                else:status.set('패치와 재검증이 완료되었습니다.');messagebox.showinfo('완료',value['output']+'\n\nDolphin으로 결과를 실행하세요.')
        root.after(100,poll)
    def close():
        if busy[0]:messagebox.showinfo('작업 중','검증이 끝난 뒤 닫아 주세요.')
        else:root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    if self_test:
        root.update_idletasks();result={'gui_widgets_initialized':True,'tk_version':root.tk.call('info','patchlevel')};root.destroy();return result
    root.after(100,poll);root.mainloop()


def main():
    home=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    ap=argparse.ArgumentParser(description='와리오 월드 일본판 디스크 내부 파일 차분 패처')
    ap.add_argument('--input');ap.add_argument('--output');ap.add_argument('--bundle',default=str(home/'patch-data.zip'))
    ap.add_argument('--check',action='store_true');ap.add_argument('--report');ap.add_argument('--self-test-gui',action='store_true');args=ap.parse_args()
    if not args.input and not args.self_test_gui:gui(args.bundle);return
    try:
        result=gui(args.bundle,True) if args.self_test_gui else run(args.input,args.output,args.bundle,lambda s:print(s) if sys.stdout else None,args.check)
        if args.report:
            with Path(args.report).open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
        if sys.stdout:print(json.dumps(result,ensure_ascii=False))
    except Exception as e:
        if sys.stderr:print(str(e),file=sys.stderr)
        sys.exit(1)


if __name__=='__main__':main()
