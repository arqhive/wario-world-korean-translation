"""Resize approved imagegen lettering and composite into independent originals.
User authorized Python masking/background compositing/size correction. PNG only.
"""
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'work/graphics/title'
OUT=WORK/'variants-v02'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def lettering(height):
    im=Image.open(WORK/'subtitle-imagegen-v01.png').convert('RGBA')
    a=np.array(im); labels,_=ndimage.label(a[:,:,3]>20)
    counts=np.bincount(labels.ravel());keep=counts>=100;keep[0]=False
    a[~ndimage.binary_dilation(keep[labels],iterations=1)]=0
    im=Image.fromarray(a);im=im.crop(im.getbbox())
    return im.resize((round(im.width*height/im.height),height),Image.Resampling.LANCZOS)


def make(key,original,mask,clean,layer,protected,basis):
    folder=OUT/key;folder.mkdir(parents=True,exist_ok=True)
    src=Image.open(original).convert('RGBA');a=np.array(src)
    cleaned=a.copy();cleaned[mask]=clean[mask]
    im=Image.alpha_composite(Image.fromarray(cleaned),layer);out=np.array(im)
    placement=np.array(layer)[:,:,3]>0;union=mask|placement
    assert not np.any(out[~union]!=a[~union])
    assert not np.any(out[protected]!=a[protected])
    for name,img in [('original',src),('clean',Image.fromarray(cleaned)),('ko',im),('lettering',layer)]:img.save(folder/(name+'.png'))
    for name,m in [('removal-mask',mask),('placement-mask',placement),('edit-mask',union),('protected-mask',protected)]:Image.fromarray(m.astype(np.uint8)*255).save(folder/(name+'.png'))
    for name,color in [('white-preview','white'),('dark-preview',(60,70,85))]:
        bg=Image.new('RGBA',src.size,color);bg.alpha_composite(im);bg.convert('RGB').save(folder/(name+'.png'))
    sheet=Image.new('RGB',(src.width*3,src.height+22),(60,70,85));draw=ImageDraw.Draw(sheet)
    for n,(label,img) in enumerate([('ORIGINAL',src),('RESTORED',Image.fromarray(cleaned)),('KOREAN',im)]):
        draw.text((src.width*n+2,4),label,fill='white');sheet.paste(img,(src.width*n,22),img)
    sheet.save(folder/'comparison.png')
    sheet.resize((sheet.width*4,sheet.height*4),Image.Resampling.NEAREST).save(folder/'comparison-4x.png')
    return {'id':key,'original':original.relative_to(ROOT).as_posix(),'original_sha256':sha(original),
            'output':(folder/'ko.png').relative_to(ROOT).as_posix(),'output_sha256':sha(folder/'ko.png'),
            'size':list(im.size),'mode':im.mode,'mask_basis':basis,'removal_mask_pixels':int(mask.sum()),
            'placement_mask_pixels':int(placement.sum()),'outside_proposed_mask_changed_pixels':0,
            'protected_region_changed_pixels':0,'alpha_equal_original':bool(np.array_equal(out[:,:,3],a[:,:,3])),
            'limitations':['PNG draft; RGB5A3 encoding and game display not validated.','Hidden background reconstructed; proposed mask awaits review.']}


def main():
    d=json.loads((ROOT/'project.json').read_text(encoding='utf-8'))
    assert d['decisions']['graphics_python_postprocessing_authorized']
    assert sha(ROOT/'graphics/approved/title-large.png')=='639c80b5c7a39a03fecb19271f147b6fcb528a133215898e4ff76cce1061dab4'
    small=ROOT/'work/extraction/texture_objects/c77ef88e9fa05c7e3079fbafeea6441b8092aabd57d99a17dbc999a57e350945.png'
    assert sha(small)=='b8cc43582b23d08f52b1853e902a4fa5d936ae867151801acdde8177a5a44eba'
    src=Image.open(small);a=np.array(src);y,x=np.indices(a.shape[:2])
    mask=np.array(Image.open(WORK/'native-v04/removal-mask.png').resize(src.size,Image.Resampling.BOX))>0
    protected=(y<63)|(x<56)|(x>159)|((x>=158)&(y<=65))
    mask|=(y>=73)&(y<=80)&(x>=56)&(x<=159)&(a[:,:,3]>0)
    mask&=~protected
    clean=np.array(Image.open(WORK/'native-v04/clean.png').resize(src.size,Image.Resampling.LANCZOS))
    # User revision: castle gate center ~98.5px, matching the large logo.
    layer=Image.new('RGBA',src.size);layer.alpha_composite(lettering(16),(60,63))
    results=[make('title-small',small,mask,clean,layer,protected,'Approved large source glyph mask mapped to native small source, with separate English/W badge protection and source alpha below castle sill.')]
    results[0].update(lettering_position=[60,63],castle_center_x=98.5,lettering_box_center_x=98.5)
    banner=ROOT/'work/extraction/jp/banner.png'
    assert sha(banner)=='4648e54d6676f0491cc762259e25ae3b7cff6d0f316923086e1f391ba33a5eae'
    src=Image.open(banner);a=np.array(src);y,x=np.indices(a.shape[:2])
    protected=(y<22)|(y>30)|(x<26)|(x>76)
    # Estimate local row background solely to identify glyph/outline contrast.
    estimate=np.zeros_like(a[:,:,:3],dtype=float)
    for row in range(32):
        left=a[row,25,:3].astype(float);right=a[row,78,:3].astype(float)
        for col in range(96):estimate[row,col]=left+(right-left)*np.clip((col-25)/53,0,1)
    contrast=np.max(np.abs(a[:,:,:3].astype(float)-estimate),axis=2)
    seed=(contrast>24)&(~protected)&(y>=23)&(y<=29)
    mask=ndimage.binary_dilation(seed,iterations=1)&(~protected)
    clean=a.copy();clean[:,:,:3]=cv2.inpaint(a[:,:,:3],mask.astype(np.uint8)*255,3,cv2.INPAINT_TELEA)
    # User screenshot: isolated original Japanese gold pixel just right of 드.
    # Correct this pixel only, using the immediately adjacent restored background.
    mask[22,72]=True
    clean[22,72,:3]=np.rint((clean[22,71,:3].astype(float)+clean[22,73,:3])/2).astype(np.uint8)
    layer=Image.new('RGBA',src.size);layer.alpha_composite(lettering(8),(32,22))
    results.append(make('banner',banner,mask,clean,layer,protected,'Source glyph contrast against interpolated adjacent background, dilated one native pixel to include outline. English/W badge and border excluded.'))
    previous=np.array(Image.open(WORK/'variants-v01/banner/ko.png'))
    revised=np.array(Image.open(OUT/'banner/ko.png'))
    changed=np.argwhere(np.any(previous!=revised,axis=2))
    assert changed.tolist()==[[22,72]],changed.tolist()
    results[1].update(correction_xy=[72,22],changed_pixels_since_v01=1)
    evidence={'approved_style':'graphics/approved/title-large.png','lettering_source_sha256':sha(WORK/'subtitle-imagegen-v01.png'),'assets':results}
    (ROOT/'metadata/title_variants_v02.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sheet=Image.new('RGB',(840,650),(60,70,85));draw=ImageDraw.Draw(sheet)
    for key,label,y in [('title-small','SMALL TITLE',10),('banner','BANNER',150)]:
        draw.text((12,y),label+' / ORIGINAL - RESTORED - KOREAN / NATIVE SIZE',fill='white')
        sheet.paste(Image.open(OUT/key/'comparison.png'),(12,y+20))
    draw.text((12,240),'KOREAN PREVIEWS / 3x NEAREST-NEIGHBOR',fill='white')
    for key,pos in [('title-small',(12,270)),('banner',(12,540))]:
        preview=Image.open(OUT/key/'dark-preview.png')
        sheet.paste(preview.resize((preview.width*3,preview.height*3),Image.Resampling.NEAREST),pos)
    sheet.save(OUT/'review.png')
    print(json.dumps(evidence,ensure_ascii=False))


if __name__=='__main__':main()
