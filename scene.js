// A printed winter village, drawn locally to keep the postcard available offline.
const ctx = document.getElementById('scene').getContext('2d');
let seed = 193;
function random() {
  seed = (seed * 16807) % 2147483647;
  return seed / 2147483647;
}
function shape(color, points) {
  ctx.fillStyle = color;
  ctx.beginPath();
  points.forEach(([x,y], i) => i ? ctx.lineTo(x,y) : ctx.moveTo(x,y));
  ctx.closePath();
  ctx.fill();
}
function hill(color, level, wave) {
  const points = [];
  for(let x=0;x<=680;x+=5) points.push([x, level+Math.sin(x/115+wave)*27]);
  shape(color,[...points,[680,360],[0,360]]);
}
function spruce(x,y,h,color) {
  ctx.fillStyle=color;
  ctx.fillRect(x-h*.022,y-h*.5,h*.045,h*.5);
  for(let i=0;i<4;i++) {
    const w=h*(.095+i*.055), top=y-h+i*h*.16;
    shape(color,[[x,top],[x+w,top+h*.36],[x,top+h*.31],[x-w,top+h*.37]]);
  }
}
function cabin(x,y,w,color) {
  ctx.fillStyle=color;
  ctx.fillRect(x,y-w*.48,w,w*.48);
  shape('#e7d9b6',[[x-5,y-w*.48],[x+w*.34,y-w*.88],[x+w*.75,y-w*.49]]);
  shape('#ac5850',[[x+w*.34,y-w*.88],[x+w*.72,y-w*.88],[x+w+5,y-w*.48],[x+w*.69,y-w*.48]]);
  ctx.fillStyle='#f5ca76';
  for(const p of [.16,.62,.78]) ctx.fillRect(x+w*p,y-w*.35,w*.09,w*.17);
}
for(let i=0;i<78;i++){
  const x=random()*680,y=random()*170,r=random()*1.8+.6;
  ctx.fillStyle='#decc98';ctx.fillRect(x,y,r,r);
}
hill('#366458',145,1);
for(let i=0;i<62;i++){const x=random()*680;spruce(x,153+Math.sin(x/115+1)*27,16+random()*37,'#366458');}
hill('#99ac92',190,3);
hill('#e8ddbd',236,0);
cabin(265,221,69,'#934d40');cabin(366,211,46,'#477165');cabin(449,212,58,'#9e5947');
for(const [x,y,h] of [[31,248,145],[107,227,91],[195,225,69],[540,221,77],[621,239,144],[669,235,104]])spruce(x,y,h,'#234e41');
hill('#799387',297,1);
hill('#224e43',331,3);
for(const [x,y,h] of [[8,352,168],[67,356,116],[150,354,65],[572,365,90],[651,363,176]])spruce(x,y,h,'#173d34');
for(let i=0;i<7800;i++){ctx.fillStyle=random()>.5?'#ffffff0b':'#352d2012';ctx.fillRect(random()*680,random()*360,1.5,1.2);}
