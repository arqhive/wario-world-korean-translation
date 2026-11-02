"""User-authorized masking/compositing of imagegen lettering; no ROM build.

Original and generated sources remain untouched. Masks are computed from source
lettering before compositing, not from a final-image difference.
"""
import hashlib
import json
import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy import sparse
from scipy.sparse.linalg import spsolve
from inspect_discs import ROOT, save

OUT=ROOT/'work/graphics/objective-board/native-v05'
ORIGINAL=ROOT/'work/extraction/texture_objects/d99165c72072000f8b52c2ec2907a37c78b07ed3b0e543a06a2fd91488dba229.png'
CUTOUT=ROOT/'work/graphics/objective-board/ko-cutout-imagegen-v02.png'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def original_mask(rgba):
    a=rgba[:,:,:3].astype(np.int16);r,g,b=a.transpose(2,0,1)
    y,x=np.indices(r.shape)
    title=(x>=27)&(x<=425)&(y>=12)&(y<=92)
    title &= ~((x<90)&(y<35))
    body_domain=np.zeros(r.shape,np.uint8)
    cv2.fillPoly(body_domain,[np.array([(32,140),(360,88),(380,170),(370,287),(155,304),(43,283),(27,230)],np.int32)],1)
    body=body_domain.astype(bool)
    dark=(r<192)&(g<158)&(b<118)
    orange=(r-b>110)&(g-b>45)
    seed=(title&(dark|orange))|(body&dark)
    labels,n=ndimage.label(seed)
    counts=np.bincount(labels.ravel());keep=counts>=3;keep[0]=False
    seed=keep[labels]
    # Fill enclosed pale glyph interiors; mask remains glyph-shaped, not boxes.
    seed=ndimage.binary_fill_holes(seed)
    seed=ndimage.binary_dilation(seed,iterations=4)
    # The title has a wider soft extrusion shadow than the outlined body text.
    title_support=seed&(y<94)
    seed |= ndimage.binary_dilation(title_support,iterations=6)
    labels,_=ndimage.label(seed)
    counts=np.bincount(labels.ravel());keep=counts>=120;keep[0]=False
    seed=keep[labels]
    return seed & (rgba[:,:,3]>0)


def reconstruct(rgb,paper,mask):
    # Dirichlet solve: correct generated-paper colors smoothly to untouched
    # original background at every mask boundary. No old text is sampled inside.
    h,w=mask.shape;ys,xs=np.nonzero(mask);n=len(xs)
    index=np.full((h,w),-1,np.int32);index[ys,xs]=np.arange(n)
    ri=[];ci=[];values=[];rhs=np.zeros((n,3),np.float64)
    boundary=rgb.astype(np.float64)-paper.astype(np.float64)
    degree=np.zeros(n)
    for dy,dx in [(0,1),(0,-1),(1,0),(-1,0)]:
        ny,nx=ys+dy,xs+dx
        valid=(ny>=0)&(ny<h)&(nx>=0)&(nx<w)
        current=np.flatnonzero(valid);ny=ny[valid];nx=nx[valid];degree[current]+=1
        neighbor=index[ny,nx];inside=neighbor>=0
        ri.extend(current[inside]);ci.extend(neighbor[inside]);values.extend([-1.]*int(inside.sum()))
        rhs[current[~inside]]+=boundary[ny[~inside],nx[~inside]]
    ri.extend(range(n));ci.extend(range(n));values.extend(degree)
    matrix=sparse.csr_matrix((values,(ri,ci)),shape=(n,n))
    correction=spsolve(matrix,rhs)
    result=rgb.copy();result[ys,xs]=np.clip(paper[ys,xs]+correction,0,255).round().astype('uint8')
    return result


def main():
    state=json.loads((ROOT/'project.json').read_text(encoding='utf8'))
    assert state['decisions'].get('graphics_python_postprocessing_authorized') is True
    assert digest(ORIGINAL)=='e3086d37a5f14784232493173586d157f69fa4b1b7913644a1af391b11a031ad'
    assert digest(CUTOUT)=='c197157b54f01b808dbb6a45773ef7f45fd9517b0a042307664991dac5a90bd7'
    OUT.mkdir(parents=True,exist_ok=True)
    original=np.array(Image.open(ORIGINAL).convert('RGBA'))
    mask=original_mask(original)
    # Use generated parchment gradients only inside source-derived masks.
    # Poisson boundary matching avoids importing rectangular paper patches.
    paper=np.array(Image.open(ROOT/'work/graphics/objective-board/clean-v01.png').convert('RGB').resize((448,312),Image.Resampling.LANCZOS))
    restored=reconstruct(original[:,:,:3],paper,mask)
    clean=original.copy();clean[mask,:3]=restored[mask]
    Image.fromarray(mask.astype('uint8')*255).save(OUT/'removal-mask.png')
    Image.fromarray(clean).save(OUT/'clean.png')
    # Retain generated glyph shapes; fit complete cutout to original canvas.
    cut=Image.open(CUTOUT).convert('RGBA')
    cut_pixels=np.array(cut)
    labels,_=ndimage.label(cut_pixels[:,:,3]>8)
    counts=np.bincount(labels.ravel());keep=counts>=50;keep[0]=False
    cut_pixels[~keep[labels],3]=0
    cut=Image.fromarray(cut_pixels)
    overlay=cut.resize((448,312),Image.Resampling.LANCZOS)
    layer=np.array(overlay)
    placement=layer[:,:,3]>0
    Image.fromarray(placement.astype('uint8')*255).save(OUT/'placement-mask.png')
    overlay.save(OUT/'lettering.png')
    result=np.array(Image.alpha_composite(Image.fromarray(clean),overlay))
    result[:,:,3]=original[:,:,3]
    union=mask|placement
    # Enforce source pixels outside the declared masks and original alpha.
    result[~union]=original[~union]
    Image.fromarray(result).save(OUT/'ko.png')
    Image.fromarray(union.astype('uint8')*255).save(OUT/'edit-mask.png')
    changes=np.any(result!=original,axis=2)
    outside=int(np.count_nonzero(changes&~union))
    assert outside==0 and np.array_equal(result[:,:,3],original[:,:,3])
    overlay_mask=original.copy();overlay_mask[mask,:3]=(overlay_mask[mask,:3]*.4+np.array([255,0,190])*.6).astype('uint8')
    Image.fromarray(overlay_mask).save(OUT/'mask-review.png')
    sheet=Image.new('RGBA',(448*3,340),(240,240,240,255));draw=ImageDraw.Draw(sheet)
    for i,(label,im) in enumerate([('Original',Image.fromarray(original)),('Restored background',Image.fromarray(clean)),('Korean draft',Image.fromarray(result))]):
        draw.text((i*448+8,7),label,fill=(0,0,0,255));sheet.alpha_composite(im,(i*448,28))
    sheet.convert('RGB').save(OUT/'comparison.png')
    Image.fromarray(result).resize((896,624),Image.Resampling.NEAREST).save(OUT/'ko-2x.png')
    report={'original_sha256':digest(ORIGINAL),'cutout_sha256':digest(CUTOUT),
            'output':str((OUT/'ko.png').relative_to(ROOT)).replace('\\','/'),
            'dimensions':[448,312],'alpha_equal_original':True,
            'removal_mask_pixels':int(mask.sum()),'placement_mask_pixels':int(placement.sum()),
            'edit_mask_pixels':int(union.sum()),'changed_pixels':int(changes.sum()),
            'outside_proposed_mask_changed_pixels':outside,
            'mask_approval':'Proposed source-derived glyph/shadow masks, awaiting visual review; not separately user-approved.',
            'original_region_outside_mask_exact':True,
            'mask_sha256':digest(OUT/'edit-mask.png'),
            'limitations':['Masked background is reconstructed, not recovered original hidden pixels.',
                           'PNG only; RGB5A3 encoding and game display not validated.']}
    save(ROOT/'metadata/objective_board_native_v05.json',report)
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
