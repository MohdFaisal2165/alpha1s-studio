"""Draw an original schematic; no vendor artwork or action files are redistributed."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
root=Path(__file__).resolve().parents[1]
im=Image.new('RGB',(500,680),'#101827');d=ImageDraw.Draw(im)
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',20)
small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
d.text((24,18),'JOINT MAP · FRONT VIEW',font=font,fill='#e5edf8')
d.rounded_rectangle((195,70,305,170),radius=35,fill='#23344c')
d.rounded_rectangle((165,185,335,340),radius=30,fill='#23344c')
points={1:(180,205),2:(120,225),3:(90,325),4:(320,205),5:(380,225),6:(410,325),7:(195,365),8:(185,410),9:(175,480),10:(165,550),11:(160,595),12:(305,365),13:(315,410),14:(325,480),15:(335,550),16:(340,595)}
for chain in ((1,2,3),(4,5,6),(7,8,9,10,11),(12,13,14,15,16)):
 d.line([points[i] for i in chain],fill='#6b819d',width=22)
for i,(x,y) in points.items():
 d.ellipse((x-21,y-21,x+21,y+21),fill='#38dbc0')
 d.text((x,y),str(i),font=font,anchor='mm',fill='#082620')
d.text((25,638),'ROBOT RIGHT',font=small,fill='#c7d6e8');d.text((320,638),'ROBOT LEFT',font=small,fill='#c7d6e8')
(root/'assets').mkdir(exist_ok=True);im.save(root/'assets/joint-map.png')
