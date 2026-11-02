"""Native title draft. Source-derived masks + user-authorized Python compositing.
No texture injection or ROM generation. Original English pixels are protected.
"""
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work/graphics/title'
OUT = WORK / 'native-v05'
ORIGINAL = ROOT / 'work/extraction/texture_objects/4b2bd652391878cd4f72284e8da22764446ebb6652bb914c9729a60f5f6451a7.png'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    assert json.loads((ROOT/'project.json').read_text(encoding='utf-8'))['decisions']['graphics_python_postprocessing_authorized']
    assert sha(ORIGINAL) == 'a34d1f6713c609e4aa7ceab5e4cd0e87d7c5ec1b1fd55cbe9488d25513cd1fd8'
    OUT.mkdir(parents=True, exist_ok=True)
    src = Image.open(ORIGINAL).convert('RGBA')
    a = np.array(src)
    # Hand-traced source subtitle domains exclude English extrusion and W badge.
    polygons = [
        [(164,186),(206,186),(206,209),(198,222),(185,230),(175,230),(168,218),(164,207)],
        [(209,186),(245,186),(248,206),(243,219),(230,229),(218,229),(212,214),(208,206)],
        [(247,189),(268,189),(269,182),(281,182),(282,189),(290,189),(291,202),(285,202),(285,226),(280,230),(264,230),(259,220),(249,226),(242,213)],
        [(291,187),(332,187),(333,208),(328,220),(316,229),(305,230),(296,216),(290,208)],
        [(334,199),(374,199),(374,215),(334,215)],
        [(375,187),(405,184),(405,207),(410,200),(421,206),(417,218),(401,228),(392,228),(388,224),(378,230),(370,219)],
        [(421,182),(438,182),(438,196),(440,198),(437,189),(444,185),(448,183),(453,181),(461,192),(454,198),(461,201),(459,208),(453,219),(438,210),(438,229),(419,229)],
    ]
    domain = np.zeros(a.shape[:2], np.uint8)
    for poly in polygons:
        cv2.fillPoly(domain, [np.array(poly, np.int32)], 1)
    yy,xx=np.indices(a.shape[:2])
    domain=ndimage.binary_dilation(domain,iterations=3)
    # Protect the main English logo/badge, including its lower extrusion edge.
    domain &= (yy>=183)&(xx>=164)&(xx<=463)
    # The English L's white contour meets the Japanese dakuten at this corner.
    english_protection=(yy<183)|(xx<164)|(xx>463)|((xx>=458)&(yy<=187))
    domain &= ~english_protection
    r,g,b = a[:,:,:3].astype(np.int16).transpose(2,0,1)
    seed = ((r-b>35)&(r-g>7) | ((r>185)&(g>180)&(b>155))) & (domain>0) & (a[:,:,3]>0)
    mask = ndimage.binary_dilation(seed, iterations=3) & (domain>0)
    mask = ndimage.binary_fill_holes(mask)
    # Below the castle sill only the old subtitle occupies this span.
    mask |= (yy>=213)&(yy<=233)&(xx>=164)&(xx<=463)&(a[:,:,3]>0)
    mask &= ~english_protection
    # Generated clean plate is used ONLY under the source lettering mask.
    plate = Image.open(WORK/'clean-imagegen-v01.png').convert('RGBA').resize(src.size, Image.Resampling.LANCZOS)
    clean = a.copy()
    clean[mask] = np.array(plate)[mask]
    cut = Image.open(WORK/'subtitle-imagegen-v01.png').convert('RGBA')
    c = np.array(cut)
    labels,_ = ndimage.label(c[:,:,3]>20)
    counts=np.bincount(labels.ravel()); keep=counts>=100; keep[0]=False
    support=ndimage.binary_dilation(keep[labels],iterations=1)
    c[~support]=0
    cut=Image.fromarray(c)
    cut=cut.crop(cut.getbbox())
    # Preserve glyph proportions; five Korean syllables require less width.
    height=47
    width=round(cut.width*height/cut.height)
    cut=cut.resize((width,height),Image.Resampling.LANCZOS)
    lettering=Image.new('RGBA',src.size)
    # User revision: center subtitle on the castle gate (x~286), not JP text span.
    lettering.alpha_composite(cut,(173,183))
    placement=np.array(lettering)[:,:,3]>0
    result=Image.alpha_composite(Image.fromarray(clean),lettering)
    out=np.array(result); union=mask|placement
    assert np.array_equal(out[~union],a[~union])
    assert np.array_equal(out[english_protection],a[english_protection])
    Image.fromarray(clean).save(OUT/'clean.png'); result.save(OUT/'ko.png'); lettering.save(OUT/'lettering.png')
    for name,m in [('removal-mask',mask),('placement-mask',placement),('edit-mask',union)]:
        Image.fromarray(m.astype(np.uint8)*255).save(OUT/(name+'.png'))
    review=a.copy();review[mask,:3]=(review[mask,:3].astype(float)*.35+np.array([255,30,150])*.65).astype(np.uint8)
    Image.fromarray(review).save(OUT/'mask-review.png')
    sheet=Image.new('RGB',(580*3,274),(60,70,85));draw=ImageDraw.Draw(sheet)
    for n,(label,im) in enumerate([('ORIGINAL',src),('RESTORED',Image.fromarray(clean)),('KOREAN DRAFT',result)]):
        draw.text((n*580+10,8),label,fill='white');sheet.paste(im,(n*580,30),im)
    sheet.save(OUT/'comparison.png')
    result.resize((1160,488),Image.Resampling.NEAREST).save(OUT/'ko-2x.png')
    for name,color in [('white-preview','white'),('dark-preview',(60,70,85))]:
        preview=Image.new('RGBA',src.size,color)
        preview.alpha_composite(result)
        preview.convert('RGB').save(OUT/(name+'.png'))
    evidence={
        'original_sha256':sha(ORIGINAL),'clean_source_sha256':sha(WORK/'clean-imagegen-v01.png'),
        'lettering_source_sha256':sha(WORK/'subtitle-imagegen-v01.png'),
        'output_sha256':sha(OUT/'ko.png'),'size':list(result.size),'mode':result.mode,
        'lettering_native_size':[width,height], 'lettering_position':[173,183],
        'castle_center_x':286, 'lettering_box_center_x':173+width/2,
        'removal_mask_pixels':int(mask.sum()),
        'placement_mask_pixels':int(placement.sum()),'edit_mask_pixels':int(union.sum()),
        'outside_proposed_edit_mask_changed_pixels':int(np.any(out[~union]!=a[~union],axis=-1).sum()),
        'protected_region_changed_pixels':int(np.any(out[english_protection]!=a[english_protection],axis=-1).sum()),
        'protection_basis':'All pixels above y183, left of x164, right of x463, and English L contour at x458..463 through y187; includes main English, upper castle/flag, TM and W badge.',
        'mask_basis':'Original Japanese color/outline seeds within source-traced glyph domains, defined before compositing.',
        'limitations':['Background under removed Japanese reconstructed by imagegen; not recovered original pixels.',
                        'Proposed masks await visual approval. PNG only; no encoding, injection or runtime test.'],
    }
    (ROOT/'metadata/title_logo_native_v05.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=False))


if __name__=='__main__':
    main()
