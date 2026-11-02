"""Move existing imagegen body lettering left using user-authorized Python compositing."""
import json
import hashlib
import numpy as np
from PIL import Image, ImageDraw
from inspect_discs import ROOT, save
from prepare_objective_board import ORIGINAL


def main():
    base=ROOT/'work/graphics/objective-board/native-v05'
    out=ROOT/'work/graphics/objective-board/native-v06-left16';out.mkdir(parents=True,exist_ok=True)
    old=np.array(Image.open(base/'ko.png').convert('RGBA'))
    clean=Image.open(base/'clean.png').convert('RGBA')
    layer=np.array(Image.open(base/'lettering.png').convert('RGBA'))
    original=np.array(Image.open(ORIGINAL).convert('RGBA'))
    # Separation follows the gap between the title extrusion and rising body.
    # At the rightmost exclamation mark their antialiasing touches; retain the
    # title-side pixels in place. No background rectangles are copied.
    seam=np.interp(np.arange(448),[0,250,298,308,325,336,355,360,379,390,447],
                   [90,90,86,88,89,86,84,83,83,88,90]).round().astype(int)
    y=np.arange(312)[:,None];body_domain=y>=seam[None,:]
    body=layer.copy();body[~body_domain]=0
    title=layer.copy();title[body_domain]=0
    assert not np.any(body[:,:16,3]),'Translation would crop lettering'
    moved=np.zeros_like(body);moved[:,:-16]=body[:,16:]
    assert np.count_nonzero(moved[:,:,3])==np.count_nonzero(body[:,:,3])
    assert np.array_equal(moved[:,:-16],body[:,16:])
    newlayer=np.array(Image.alpha_composite(Image.fromarray(title),Image.fromarray(moved)))
    result=np.array(Image.alpha_composite(clean,Image.fromarray(newlayer)))
    result[:,:,3]=original[:,:,3]
    change_mask=(body[:,:,3]>0)|(moved[:,:,3]>0)
    # Keep the old title, paper, and other pixels exactly, including its halo.
    result[~change_mask]=old[~change_mask]
    protected_title=title[:,:,3]>0
    title_overlap=protected_title&(moved[:,:,3]>0)
    result[protected_title]=old[protected_title]
    oldmask=np.array(Image.open(base/'edit-mask.png'))>0
    fullmask=oldmask|(moved[:,:,3]>0)
    assert np.array_equal(result[~change_mask],old[~change_mask])
    assert np.array_equal(result[protected_title],old[protected_title])
    assert np.array_equal(result[~fullmask],original[~fullmask])
    assert np.array_equal(result[:,:,3],old[:,:,3])
    for name,data in [('ko',result),('lettering',newlayer),('body-before',body),('body-after',moved)]:Image.fromarray(data).save(out/(name+'.png'))
    for name,mask in [('revision-mask',change_mask),('edit-mask',fullmask),('title-protected-mask',protected_title)]:Image.fromarray(mask.astype('uint8')*255).save(out/(name+'.png'))
    Image.fromarray(result).resize((896,624),Image.Resampling.NEAREST).save(out/'ko-2x.png')
    sheet=Image.new('RGBA',(448*3,340),(238,238,238,255));d=ImageDraw.Draw(sheet)
    for i,(label,im) in enumerate([('Before',Image.fromarray(old)),('Restored paper',clean),('Body shifted left 16px',Image.fromarray(result))]):
        d.text((i*448+8,6),label,fill='black');sheet.alpha_composite(im,(i*448,28))
    sheet.convert('RGB').save(out/'comparison.png')
    yy,xx=np.where(moved[:,:,3]>0)
    report={'shift_px':[-16,0],'size':[448,312],'body_bbox_after':[int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1],
        'body_layer_pixels_preserved':True,'title_changed_pixels':0,'title_overlap_pixels_preserved_in_place':int(title_overlap.sum()),
        'outside_revision_mask_changed_pixels':0,'outside_original_edit_mask_union_changed_pixels':0,'alpha_equal':True,
        'output':str((out/'ko.png').relative_to(ROOT)),'sha256':hashlib.sha256((out/'ko.png').read_bytes()).hexdigest(),
        'mask':str((out/'edit-mask.png').relative_to(ROOT)),
        'limitation':'Stamp clearance estimated from user screenshot; stamps are separate game overlays, not present in this texture. Title/body touching antialias seam kept on title side. No game build or runtime test.'}
    save(ROOT/'metadata/objective_board_left16.json',report);print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
