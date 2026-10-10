// 已知测量值验证学生结论；不能把插值误当成实测，不能强制显示衰减。
const fs=require('fs'),vm=require('vm'),assert=require('assert');
vm.runInThisContext(fs.readFileSync(__dirname+'/../student-display.js','utf8'));
function fixture(amplitudes,periods){
    return {cycles:amplitudes.map((amplitude,i)=>({amplitude,period:periods[i]})),standard:{amplitude:amplitudes[0],period:periods[0]},
        data:{t:[0,1,2,3,4],raw:[1,null,.5,9,-1],standard:[1,0,.25,0,-.5],observed:[true,false,true,false,true],residual:[0,null,.25,null,-.5]}};
}
let checks=0;
function test(name,job){job();checks++;console.log('PASS '+name)}
test('mean absolute difference uses only measured valid points',()=>{
    const v=studentReadings(fixture([1,.9,.8],[2,2.01,1.99]));
    assert.equal(v.meanError,.25);assert.equal(v.errorPct,25);assert.equal(v.maxError,.5);
    assert(Math.abs(v.decrease-20)<1e-10);assert(Math.abs(v.maxPeriodDiff-.01)<1e-10);
    assert(v.trend.includes('逐次减小'));
});
test('single waveform cannot establish damping',()=>{
    const v=studentReadings(fixture([1],[2]));assert(v.trend.includes('无法判断'));assert.equal(v.maxPeriodDiff,0);
});
test('rising and fluctuating amplitudes remain truthful',()=>{
    const rising=studentReadings(fixture([1,1.1,1.2],[2,2,2]));assert(rising.decrease<0);assert(rising.trend.includes('逐次增大'));
    const mixed=studentReadings(fixture([1,.8,.9],[2,2,2]));assert(mixed.trend.includes('有波动'));
});
test('equal amplitudes do not claim decay',()=>{
    const v=studentReadings(fixture([1,1,1],[2,2,2]));assert.equal(v.decrease,0);assert(v.trend.includes('基本不变'));
});
test('excluded edge samples cannot bias the whole-image difference',()=>{
    const r=fixture([1,.8],[2,2]);r.data.observed[3]=true;r.data.residual[3]=null;
    assert.equal(studentReadings(r).meanError,.25);
});
const page=fs.readFileSync(__dirname+'/../index.html','utf8'),helper=fs.readFileSync(__dirname+'/../student-display.js','utf8');
assert(page.replace(/\r\n/g,'\n').includes(helper.replace(/\r\n/g,'\n').trim()),'单文件页面中的学生读数代码需要同步');
console.log(checks+' student reading checks passed');
