"""Recompose the complete replacement line; never use the rejected two-letter edit.

User explicitly requested a full-line replacement on the restored background.
The source-derived removal mask and generated full-line artwork are saved in the
revision workspace and backup. This script writes PNGs only, never builds an ISO.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image,ImageDraw
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/graphics/objective-board/imperative-full-line-20261022'


def main():
    before=ROOT/'backups/graphics/objective-board/imperative-20261022/objective-board-before.png'
    assert hashlib.sha256(before.read_bytes()).hexdigest()=='3e192fa4550efb2ee9dc7b6b4f564f7dd750db83bc6bb9da0f3175ae8c0c1387'
    a=np.array(Image.open(before).convert('RGBA'))
    original_layer=np.array(Image.open(ROOT/'work/graphics/objective-board/native-v06-left16/lettering.png').convert('RGBA'))
    clean=Image.open(ROOT/'work/graphics/objective-board/native-v05/clean.png').convert('RGBA')
    remove=np.array(Image.open(OUT/'removal-mask-final.png'))>0
    kept=original_layer.copy();kept[remove]=0
    restored=np.array(Image.alpha_composite(clean,Image.fromarray(kept)))
    restored[~remove]=a[~remove];restored[:,:,3]=a[:,:,3]
    g=Image.open(OUT/'line-imagegen.png').convert('RGBA')
    yy,xx=np.where(np.array(g)[:,:,3]>16)
    g=g.crop((xx.min()-2,yy.min()-2,xx.max()+3,yy.max()+3))
    # A single scale and rotation apply to the whole phrase AND both punctuation marks.
    line=g.resize((337,42),Image.Resampling.LANCZOS).rotate(9,Image.Resampling.BICUBIC,expand=True)
    placed=Image.new('RGBA',(448,312));placed.alpha_composite(line,(19,142))
    assert int(np.array(placed)[:,:,3].sum())==int(np.array(line)[:,:,3].sum()),'Do not crop any line pixels'
    b=np.array(Image.alpha_composite(Image.fromarray(restored),placed));b[:,:,3]=a[:,:,3]
    revision=remove|(np.array(placed)[:,:,3]>0)
    fullmask=(np.array(Image.open(ROOT/'work/graphics/objective-board/native-v06-left16/edit-mask.png'))>0)|revision
    changed=np.any(a!=b,axis=2)
    assert not np.any(changed[~revision]) and np.array_equal(a[:,:,3],b[:,:,3])
    # Check the existing lettering of every other line, independently of the edit mask.
    y,x=np.indices(a.shape[:2]);s=y+.15*x
    ink=(original_layer[:,:,0]>220)&(original_layer[:,:,1]>175)&(original_layer[:,:,2]>85)&(original_layer[:,:,3]>128)
    labels,n=ndimage.label(ink);protect=np.zeros_like(ink)
    for k in range(1,n+1):
        m=labels==k
        if m.sum()>4 and not 208<s[m].mean()<240:protect|=m
    assert not np.any(changed&protect),'Other line foreground altered'
    assert not np.any(changed[:95]) and not np.any(changed[:,365:])
    Image.fromarray(b).save(OUT/'ko.png');Image.fromarray(restored).save(OUT/'restored-final.png')
    placed.save(OUT/'line-layer.png')
    Image.alpha_composite(Image.fromarray(kept),placed).save(OUT/'lettering.png')
    Image.fromarray(revision.astype('uint8')*255).save(OUT/'revision-mask.png')
    Image.fromarray(fullmask.astype('uint8')*255).save(OUT/'edit-mask.png')
    Image.fromarray(b).resize((896,624),Image.Resampling.NEAREST).save(OUT/'ko-2x.png')
    sheet=Image.new('RGB',(1344,340),(238,238,238));draw=ImageDraw.Draw(sheet)
    for i,(label,im) in enumerate([('Before',Image.fromarray(a)),('Restored background',Image.fromarray(restored)),('Whole line replaced',Image.fromarray(b))]):
        sheet.paste(im,(i*448,28));draw.text((i*448+8,7),label,fill='black')
    sheet.save(OUT/'comparison.png')
    report={'date':'2026-10-22','text':'하트 조각을 손에 넣어라!!','replacement_scope':'entire line including both exclamation marks',
        'method':'Built-in imagegen full-line artwork, authorized Python compositing onto restored paper',
        'prompt':'One horizontal transparent line: 하트 조각을 손에 넣어라!!; match reference cream-yellow rounded lettering, thick chocolate outline and small extrusion; consistent glyph size and intact full-size punctuation; no paper or other text.',
        'source_size':[448,312],'scaled_line_size':[337,42],'rotation_degrees':9,'placement':[19,142],
        'line_alpha_pixels_cropped':0,'outside_revision_mask_changed_pixels':0,'other_line_foreground_changed_pixels':0,
        'title_changed_pixels':0,'right_stamp_area_changed_pixels':0,'alpha_preserved':True,'changed_pixels':int(changed.sum()),
        'sha256':hashlib.sha256((OUT/'ko.png').read_bytes()).hexdigest(),'build_performed':False,'runtime_tested':False,
        'supersedes':'Rejected partial-glyph edit metadata/objective_board_imperative_20261022.json'}
    (ROOT/'metadata/objective_board_full_line_20261022.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
