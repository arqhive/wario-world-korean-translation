"""Entire seven-line imagegen overlay on previously restored paper.

No old Korean lettering, partial-word cutouts or per-line removal are used.
PNG preparation only; does not build or patch any game image.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/graphics/objective-board/all-lettering-20261022'


def main():
    clean=Image.open(ROOT/'work/graphics/objective-board/native-v05/clean.png').convert('RGBA')
    source=Image.open(OUT/'all-lettering-imagegen.png').convert('RGBA')
    layer=Image.new('RGBA',(448,312))
    layer.alpha_composite(source.resize((432,292),Image.Resampling.LANCZOS),(8,10))
    # Remove barely-visible alpha-1 resampling speckles across the whole overlay.
    pixels=np.array(layer);pixels[pixels[:,:,3]<=1]=0;layer=Image.fromarray(pixels)
    result=np.array(Image.alpha_composite(clean,layer));paper=np.array(clean)
    result[:,:,3]=paper[:,:,3]
    placement=np.array(layer)[:,:,3]>0
    assert np.array_equal(result[~placement],paper[~placement])
    assert np.array_equal(result[:,:,3],paper[:,:,3])
    # Japanese-source removal mask plus the complete new lettering layer.
    original_removal=np.array(Image.open(ROOT/'work/graphics/objective-board/native-v05/removal-mask.png'))>0
    mask=original_removal|placement
    original=np.array(Image.open(ROOT/'work/extraction/texture_objects/d99165c72072000f8b52c2ec2907a37c78b07ed3b0e543a06a2fd91488dba229.png').convert('RGBA'))
    assert not np.any(result[~mask]!=original[~mask])
    # Keep the body clear of the runtime stamp column; title is above that column.
    assert not np.any(placement[100:,365:])
    Image.fromarray(result).save(OUT/'ko.png');layer.save(OUT/'lettering.png')
    Image.fromarray(mask.astype('uint8')*255).save(OUT/'edit-mask.png')
    Image.fromarray(result).resize((896,624),Image.Resampling.NEAREST).save(OUT/'ko-2x.png')
    old=Image.open(ROOT/'backups/graphics/objective-board/imperative-20261022/objective-board-before.png').convert('RGBA')
    sheet=Image.new('RGB',(1344,340),(238,238,238));draw=ImageDraw.Draw(sheet)
    for i,(label,im) in enumerate([('Before wording change',old),('Clean restored paper',clean),('All seven lines regenerated',Image.fromarray(result))]):
        sheet.paste(im,(i*448,28));draw.text((i*448+8,7),label,fill='black')
    sheet.save(OUT/'comparison.png')
    report={'date':'2026-10-22','scope':'ALL lettering: title and six body lines; no retained old Korean text fragments',
        'lines':['이 몸의 목표','여기 보스를 날려 버린다!!','빨간 다이아를 모아라','하트 조각을 손에 넣어라!!','황금상을 모아라','보물을 되찾아라!!','보물을 모아라'],
        'method':'Built-in imagegen complete transparent overlay + authorized Python whole-layer compositing',
        'prompt':'Recreate all seven lines exactly, reference-matched orange/yellow extruded title and rounded cream text with chocolate outlines, consistent main/subtitle sizes, complete punctuation and clear inter-line gaps, transparent background; reserve right 19 percent below title for stamps.',
        'size':[448,312],'whole_overlay_scale':[432,292],'whole_overlay_offset':[8,10],
        'background_outside_new_lettering_changed_pixels':0,'outside_original_removal_plus_new_lettering_changed_pixels':0,
        'alpha_preserved':True,'right_stamp_column_clear_below_y100':True,'inspection':'Native size and 2x; all seven strings visually inspected',
        'sha256':hashlib.sha256((OUT/'ko.png').read_bytes()).hexdigest(),'build_performed':False,'runtime_tested':False,
        'supersedes':['Rejected two-syllable edit','Rejected single-line edit; adjacent subtitle border damaged']}
    (ROOT/'metadata/objective_board_all_lettering_20261022.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
