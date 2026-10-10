/* 学生读数来自实测数据。标准波保持首周期参数，不把实验振幅强制改成递减。 */
function changeWords(percent){
    if(Math.abs(percent)<0.005)return '变化不足 0.01%';
    return (percent>0?'减小 ':'增大 ')+fmt(Math.abs(percent),2)+'%';
}
function periodWords(delta){
    if(Math.abs(delta)<0.00005)return '差不足 0.0001 秒';
    return (delta>0?'长 ':'短 ')+fmt(Math.abs(delta),4)+' 秒';
}
function studentReadings(r){
    const cs=r.cycles,first=cs[0],last=cs[cs.length-1],a1=r.standard.amplitude;
    const decrease=100*(1-last.amplitude/first.amplitude);
    const periods=cs.map(c=>c.period),minPeriod=Math.min(...periods),maxPeriod=Math.max(...periods);
    const maxPeriodDiff=Math.max(...periods.map(t=>Math.abs(t-r.standard.period)));
    // 只比较实际提取的像素点；插值和缺失点不能充当测量依据。
    let total=0,count=0,maxError=0;
    r.data.t.forEach((t,i)=>{
        const actual=r.data.raw[i],reference=r.data.standard[i];
        if(!r.data.observed[i]||r.data.residual[i]===null||actual===null||reference===null||!Number.isFinite(actual)||!Number.isFinite(reference))return;
        const error=Math.abs(actual-reference);total+=error;count++;maxError=Math.max(maxError,error);
    });
    const meanError=count?total/count:null,errorPct=meanError===null?null:100*meanError/a1;
    const down=cs.length>1&&cs.slice(1).every((c,i)=>c.amplitude<cs[i].amplitude);
    const up=cs.length>1&&cs.slice(1).every((c,i)=>c.amplitude>cs[i].amplitude);
    const same=cs.slice(1).every(c=>Math.abs(c.amplitude-first.amplitude)<1e-10);
    const trend=cs.length<2?'仅一个完整波形，暂时无法判断衰减。':
        down?'振幅逐次减小，呈现衰减。':up?'振幅逐次增大。':same?'振幅基本不变。':'振幅有波动，并非逐次减小。';
    return {decrease,minPeriod,maxPeriod,maxPeriodDiff,meanError,errorPct,maxError,trend};
}
function renderStudentResults(){
    const r=result,cs=r.cycles,first=cs[0],last=cs[cs.length-1],v=studentReadings(r);
    $('waveCount').textContent=cs.length+' 个';
    $('standardPeriod').textContent=fmt(r.standard.period,3)+' 秒';
    $('totalDecay').textContent=cs.length<2?'待更多波形':changeWords(v.decrease);
    $('meanDifference').textContent=fmt(v.meanError)+' '+r.unit;
    $('differenceNote').textContent='相当于第一次振幅的 '+fmt(v.errorPct,2)+'%；越小越接近。';
    $('standardNote').textContent=`标准波：每次 ${fmt(r.standard.period,3)} 秒，振幅 ${fmt(r.standard.amplitude)} ${r.unit}，始终不衰减。`;
    $('cycleRows').replaceChildren();
    cs.forEach((c,i)=>{
        const tr=document.createElement('tr');
        const previous=i?changeWords(100*(1-c.amplitude/cs[i-1].amplitude)):'作为起点';
        const texts=['第 '+c.number+' 次',fmt(c.period,4),periodWords(c.period-r.standard.period),fmt(c.amplitude),previous,i?changeWords(100*(1-c.amplitude/first.amplitude)):'作为标准'];
        texts.forEach(text=>{const td=document.createElement('td');td.textContent=text;tr.append(td)});
        $('cycleRows').append(tr);
    });
    $('amplitudeHeading').textContent='振幅 / '+r.unit;
    $('waveScope').textContent=`识别到 ${cs.length} 个完整波形，逐个列在下表；两端不完整的波形不计入周期。`;
    const periodText=cs.length===1?`这次振动用时 ${fmt(first.period,3)} 秒。`:
        `每次振动用时 ${fmt(v.minPeriod,3)}～${fmt(v.maxPeriod,3)} 秒；与标准周期最多相差 ${fmt(v.maxPeriodDiff,4)} 秒（${fmt(100*v.maxPeriodDiff/r.standard.period,2)}%）。`;
    const decayText=cs.length===1?'还需要更多完整波形才能比较振幅变化。':
        `从第 1 次到第 ${cs.length} 次，振幅由 ${fmt(first.amplitude)} 变为 ${fmt(last.amplitude)} ${r.unit}，${changeWords(v.decrease)}。${v.trend}`;
    $('conclusionPeriod').textContent=periodText;
    $('conclusionDecay').textContent=decayText;
    $('conclusionCompare').textContent=`整张图中可测部分与蓝色标准波的平均位移差为 ${fmt(v.meanError)} ${r.unit}（第一次振幅的 ${fmt(v.errorPct,2)}%）。标准波振幅不变，实验的振幅变化见上表。`;
    const quality=r.warnings.filter(w=>/缺口|多个|裁剪边缘|不足|失败/.test(w));
    $('qualityNotice').hidden=!quality.length;
    $('qualityNotice').textContent=quality.length?'有 '+quality.length+' 项识别提示，教师可展开“高级详情”核对。':'';
}
function renderAmplitudeTrend(){
    if(!result)return;
    const cs=result.cycles,a1=result.standard.amplitude,v=studentReadings(result);
    $('amplitudeValues').textContent=cs.length<=8?cs.map(c=>`第${c.number}次 ${fmt(c.amplitude)} ${result.unit}`).join(' → '):`第1次 ${fmt(cs[0].amplitude)} → 第${cs.length}次 ${fmt(cs[cs.length-1].amplitude)} ${result.unit}（每次读数见表格）`;
    $('amplitudeReading').textContent=cs.length<2?'仅一个完整波形，暂时无法判断衰减。':`从第1次到第${cs.length}次${changeWords(v.decrease)}。`;
    const cv=$('amplitudeChart'),box=cv.getBoundingClientRect(),w=box.width,h=box.height,dpr=window.devicePixelRatio||1;
    if(w<=0||h<=0)return;
    cv.width=Math.round(w*dpr);cv.height=Math.round(h*dpr);
    const g=cv.getContext('2d');g.scale(dpr,dpr);g.fillStyle='white';g.fillRect(0,0,w,h);
    const ratios=cs.map(c=>100*c.amplitude/a1),lo=Math.max(0,Math.floor(Math.min(...ratios,100)-2)),hi=Math.ceil(Math.max(...ratios,100)+2),
        pad={l:62,r:26,t:28,b:38},pw=w-pad.l-pad.r,ph=h-pad.t-pad.b,
        xp=i=>pad.l+pw*(cs.length===1?.5:i/(cs.length-1)),yp=value=>pad.t+(hi-value)/(hi-lo)*ph;
    g.font='12px system-ui';g.lineWidth=1;
    for(let k=0;k<=4;k++){const value=lo+(hi-lo)*k/4,y=yp(value);g.strokeStyle='#e1e9ed';g.beginPath();g.moveTo(pad.l,y);g.lineTo(w-pad.r,y);g.stroke();g.fillStyle='#607383';g.textAlign='right';g.fillText(value.toFixed(1)+'%',pad.l-8,y+4)}
    g.strokeStyle='#005bea';g.lineWidth=2;g.setLineDash([8,5]);g.beginPath();g.moveTo(pad.l,yp(100));g.lineTo(w-pad.r,yp(100));g.stroke();g.setLineDash([]);
    g.strokeStyle='#df3764';g.lineWidth=2.2;g.beginPath();ratios.forEach((value,i)=>{if(i===0)g.moveTo(xp(i),yp(value));else g.lineTo(xp(i),yp(value))});g.stroke();
    const interval=Math.max(1,Math.ceil(cs.length/8));
    ratios.forEach((value,i)=>{const x=xp(i),y=yp(value);g.fillStyle='#df3764';g.beginPath();g.arc(x,y,3,0,Math.PI*2);g.fill();
        if(i%interval&&i!==cs.length-1)return;
        g.textAlign=i===0&&cs.length>1?'left':i===cs.length-1&&cs.length>1?'right':'center';g.fillStyle='#192b3a';g.fillText(fmt(value,2)+'%',x,y-10);
        g.textAlign='center';g.fillStyle='#607383';g.fillText('第'+cs[i].number+'次',x,h-12)});
    g.textAlign='left';g.fillStyle='#607383';g.fillText('第一次为100%（纵轴放大）',pad.l,16);
}
