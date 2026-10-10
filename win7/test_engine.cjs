// 独立生成已知物理函数的像素图，不借用被测算法产生预期结果。
const fs=require('fs'),vm=require('vm'),assert=require('assert');
vm.runInThisContext(fs.readFileSync(__dirname+'/offline-engine.js','utf8'));
global.document={createElement:()=>({getContext:()=>({createImageData:(w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData:()=>{}}),toDataURL:()=> 'data:image/png;base64,test'})};
global.rgbToHSV=(r,g,b)=>{let hi=Math.max(r,g,b),lo=Math.min(r,g,b),d=hi-lo,h=hi===r?((g-b)/d)%6:hi===g?(b-r)/d+2:(r-g)/d+4;return[d?((h*30+180)%180):0,hi?d/hi*255:0,hi]};
function sample(mode,damping,gap){let w=1000,h=500,p=new Uint8ClampedArray(w*h*4);p.fill(255);function project(t,y){let u=80+85*t,v=250-130*y;if(mode==='shear')return[u+.12*(v-250),v+.03*(u-80)];if(mode==='perspective'){let z=1+.0001*u;return[(u+.10*v)/z,(v+.04*u)/z]}return[u,v]}
for(let k=0;k<15000;k++){let t=k/15000*10;if(gap&&t>2&&t<4)continue;let y=Math.exp(-damping*t)*Math.sin(Math.PI*t+.25),[x,v]=project(t,y);for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){let xx=Math.round(x)+dx,yy=Math.round(v)+dy;if(xx>=0&&xx<w&&yy>=0&&yy<h){let i=(yy*w+xx)*4;p[i]=225;p[i+1]=45;p[i+2]=150}}}
let pt=(t,y)=>{let a=project(t,y);return{x:a[0],y:a[1]}},c={origin:pt(0,0),x_point:pt(5,0),y_point:pt(0,1),fourth_point:mode==='perspective'?pt(5,1):null,t0:0,y0:0,x_value:5,y_value:1,unit:'cm',roi:[25,45,980,440],h_low:140,h_high:179,s_min:55,v_min:50,min_component:5,max_gap:8,smooth_window:9,min_extrema_spacing:.25,prominence:.08,include_offset:false};return{p,w,h,c}}
let cases=0;function test(name,job){job();cases++;console.log('PASS '+name)}
test('ideal amplitude, period and phase',()=>{let {p,w,h,c}=sample('none',0,false),r=offlineAnalyze(p,w,h,c);assert(Math.abs(r.standard.period-2)<.025);assert(Math.abs(r.standard.amplitude-1)<.025);assert(r.metrics.all_observed.rmse<.02);assert.equal(r.cycles.length,4)});
test('damping retained against first-cycle sine',()=>{let {p,w,h,c}=sample('none',.045,false),r=offlineAnalyze(p,w,h,c);assert(r.summary.amplitude_nonincreasing);assert(r.summary.last_amplitude_decay_pct>20);assert(r.metrics.all_observed.rmse>r.metrics.first_cycle.rmse)});
test('rotation and shear rectification',()=>{let {p,w,h,c}=sample('shear',0,false),r=offlineAnalyze(p,w,h,c);assert(Math.abs(r.standard.period-2)<.03);assert(Math.abs(r.standard.amplitude-1)<.03)});
test('four-point perspective rectification',()=>{let {p,w,h,c}=sample('perspective',0,false),r=offlineAnalyze(p,w,h,c);assert(Math.abs(r.standard.period-2)<.03);assert(Math.abs(r.standard.amplitude-1)<.03)});
test('long gaps never become a cycle',()=>{let {p,w,h,c}=sample('none',0,true),r=offlineAnalyze(p,w,h,c);assert(r.cycles.every(q=>q.period<2.05));assert(r.warnings.some(s=>s.includes('长缺口')))});
test('cropped extrema are rejected',()=>{let {p,w,h,c}=sample('none',0,false);c.roi=[25,170,980,330];assert.throws(()=>offlineAnalyze(p,w,h,c),/完整周期/)});
test('collinear calibration rejected',()=>{let {p,w,h,c}=sample('none',0,false);c.y_point=c.x_point;assert.throws(()=>offlineAnalyze(p,w,h,c),/退化/)});
test('blank image rejects fabricated data',()=>{let {p,w,h,c}=sample('none',0,false);p.fill(255);assert.throws(()=>offlineAnalyze(p,w,h,c),/不足/)});
console.log(cases+' offline physics checks passed');
