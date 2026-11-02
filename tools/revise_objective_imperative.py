"""Reproduce the 2026-10-22 user-requested 는다 -> 어라 graphic edit.

Uses built-in imagegen lettering and previously authorized Python masking.
Imagegen prompt: transparent two-syllable '어라', cream-yellow rounded Korean
lettering, thick chocolate outline and small extrusion, matching the source.
Only writes the revision workspace; activation/backups are a separate step.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/graphics/objective-board/imperative-20261022'
BEFORE=ROOT/'backups/graphics/objective-board/imperative-20261022/objective-board-before.png'


def main():
    old=Image.open(BEFORE).convert('RGBA');a=np.array(old)
    assert hashlib.sha256(BEFORE.read_bytes()).hexdigest()=='3e192fa4550efb2ee9dc7b6b4f564f7dd750db83bc6bb9da0f3175ae8c0c1387'
    layer=np.array(Image.open(ROOT/'work/graphics/objective-board/native-v06-left16/lettering.png').convert('RGBA'))
    clean=Image.open(ROOT/'work/graphics/objective-board/native-v05/clean.png').convert('RGBA')
    y,x=np.indices(a.shape[:2])
    ink=(a[:,:,0]>210)&(a[:,:,1]>174)&(a[:,:,2]>74)&(layer[:,:,3]>128)
    target=ink&(x>=278)&(x<=328)&(y>=158)&(y<202-.15*(x-278))
    near=ndimage.distance_transform_edt(~target)
    other=ndimage.distance_transform_edt(~(ink&~target))
    domain=(near<=other)&(near<10)&(x>=274)&(x<=334)&(y>=153)&(y<=211)
    remove=(layer[:,:,3]>0)&domain
    keep=layer.copy();keep[domain]=0
    restored=np.array(Image.alpha_composite(clean,Image.fromarray(keep)))
    restored[:,:,3]=a[:,:,3];restored[~remove]=a[~remove]
    gen=Image.open(OUT/'eara-imagegen.png').convert('RGBA');gen=gen.crop(gen.getbbox())
    # Rotate the pair together along the existing rising text baseline.
    insert=gen.resize((61,36),Image.Resampling.LANCZOS).rotate(9,Image.Resampling.BICUBIC,expand=True)
    fg=Image.new('RGBA',old.size);fg.alpha_composite(insert,(270,158));f=np.array(fg)
    other=ndimage.distance_transform_edt(~(ink&~remove));f[(other<1.5)&~remove]=0
    preserve=(x<=276)|(x>=329)|((x<286)&(y>=202))
    restored[preserve]=a[preserve];f[preserve]=0
    result=np.array(Image.alpha_composite(Image.fromarray(restored),Image.fromarray(f)))
    result[:,:,3]=a[:,:,3];result[preserve]=a[preserve]
    revision=(remove|(f[:,:,3]>0))&~preserve
    original_mask=np.array(Image.open(ROOT/'work/graphics/objective-board/native-v06-left16/edit-mask.png'))>0
    fullmask=original_mask|revision
    assert np.array_equal(result[~revision],a[~revision])
    assert np.array_equal(result[:,:,3],a[:,:,3])
    assert np.array_equal(result[:150],a[:150]) and np.array_equal(result[212:],a[212:])
    assert np.array_equal(result[:,329:],a[:,329:])
    composed=np.array(Image.alpha_composite(Image.fromarray(keep),Image.fromarray(f)))
    composed[preserve]=layer[preserve]
    for name,data in [('ko',result),('restored',restored),('lettering',composed),('insert',f)]:
        Image.fromarray(data).save(OUT/(name+'.png'))
    for name,mask in [('revision-mask',revision),('removal-mask',remove&~preserve),('edit-mask',fullmask)]:
        Image.fromarray(mask.astype('uint8')*255).save(OUT/(name+'.png'))
    Image.fromarray(result).resize((896,624),Image.Resampling.NEAREST).save(OUT/'ko-2x.png')
    sheet=Image.new('RGBA',(1344,340),(238,238,238,255));draw=ImageDraw.Draw(sheet)
    for i,(label,im) in enumerate([('Before',old),('Letters removed',Image.fromarray(restored)),('After',Image.fromarray(result))]):
        draw.text((448*i+8,6),label,fill='black');sheet.alpha_composite(im,(448*i,28))
    sheet.convert('RGB').save(OUT/'comparison.png')
    changed=np.any(result!=a,axis=2);yy,xx=np.where(changed)
    report={'date':'2026-10-22','before':'하트 조각을 손에 넣는다!!','after':'하트 조각을 손에 넣어라!!',
        'method':'Built-in imagegen two-syllable insert + user-authorized Python precise masking/compositing',
        'size':list(old.size),'alpha_preserved':True,'changed_pixels':int(changed.sum()),
        'changed_bbox':[int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1],
        'outside_revision_mask_changed_pixels':int(changed[~revision].sum()),
        'title_changed_pixels':0,'right_stamp_area_changed_pixels':0,
        'output':'work/graphics/objective-board/imperative-20261022/ko.png',
        'sha256':hashlib.sha256((OUT/'ko.png').read_bytes()).hexdigest(),
        'build_performed':False,'runtime_tested':False}
    (ROOT/'metadata/objective_board_imperative_20261022.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
