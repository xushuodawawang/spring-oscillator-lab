"""生成单个 Win7 浏览器离线文件，所有代码、示例和字体模板均本地运行。"""
import base64
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

import cv2
from app import demo_image

page = (root / "index.html").read_text(encoding="utf-8")
engine = (root / "win7/offline-engine.js").read_text(encoding="utf-8")
_, demo = cv2.imencode(".png", demo_image())
demo_url = "data:image/png;base64," + base64.b64encode(demo).decode()
shim = r'''
async function apiFetch(path,options={}) {
    const response=(data,ok=true)=>({ok,status:ok?200:422,json:async()=>data,headers:{get:()=> 'application/json'}});
    if(path==='/health')return response({status:'ok',app:'spring-offline-win7',version:'1.2'});
    if(path==='/api/demo-settings')return response({origin:{x:80,y:300},x_point:{x:580,y:300},y_point:{x:80,y:120},roi:[82,65,1078,535],truth:'A(t)=exp(-0.045t) cm；T=2 s；相位=0.25 rad。'});
    if(path==='/api/demo.png'){
        let b64=OFFLINE_DEMO.split(',')[1],bytes=atob(b64),a=new Uint8Array(bytes.length);for(let i=0;i<a.length;i++)a[i]=bytes.charCodeAt(i);
        return{ok:true,blob:async()=>new Blob([a],{type:'image/png'})};
    }
    // 用一帧让“正在分析”提示先显示；实际图像只从本页 Canvas 读取。
    await new Promise(resolve=>setTimeout(resolve,30));
    if(options.signal&&options.signal.aborted){let e=Error('取消');e.name='AbortError';throw e}
    try{let p=sampleCtx.getImageData(0,0,sampler.width,sampler.height).data;
        let data=path==='/api/auto-analyze'?offlineAuto(p,sampler.width,sampler.height,options.body.get('unit')||'纵轴单位',options.body.get('include_offset')==='true'):offlineAnalyze(p,sampler.width,sampler.height,JSON.parse(options.body.get('settings')));
        return response(data);
    }catch(e){return response({detail:e.message},false)}
}
async function checkConnection(){
    $('connectionStatus').textContent='Win7 离线版 v1.2 · 学生简洁版';
    $('connectionHelp').textContent='图片与计算只在本地浏览器中处理。请使用 Chrome 109 或 Edge 109；IE 不支持。';
    return true;
}
'''.replace("OFFLINE_DEMO", repr(demo_url))
start = page.index("async function apiFetch(")
end = page.index("$('checkConnection').onclick", start)
page = page[:start] + shim + page[end:]
# 服务提示也改为本地浏览器说明。
page = re.sub(r"const serviceHelp=.*?;\n", "const serviceHelp='请用 Chrome 109 / Edge 109 打开本离线文件；IE 不支持。';\n", page)
compat = '''<script>
// 补齐旧 Chromium 的本地 API；IE 无法执行现代 JavaScript，单独给出提示。
try { new Function('return (async function(){})'); }
catch(e) { alert('请使用 Chrome 或 Edge 打开本文件，IE 浏览器不支持。Win7可使用Chrome109或Edge109。'); }
if(!Array.prototype.at)Array.prototype.at=function(i){i=Number(i);return this[i<0?this.length+i:i]};
if(!Array.prototype.flatMap)Array.prototype.flatMap=function(fn){return [].concat.apply([],this.map(fn))};
if(!Element.prototype.replaceChildren)Element.prototype.replaceChildren=function(){while(this.firstChild)this.removeChild(this.firstChild);for(var i=0;i<arguments.length;i++)this.appendChild(arguments[i])};
if(!window.AbortController)window.AbortController=function(){this.signal={aborted:false};this.abort=function(){this.signal.aborted=true}};
</script>
'''
page = page.replace('<script>\n', compat + '<script>\n' + engine + '\n', 1)
page = page.replace('弹簧振子 · 物理实验工作台</title>', '弹簧振子 · Win7 离线兼容版</title>')
page = page.replace('本地运行 · 原生 Canvas 绘图 · 无外部 CDN · 数据保留在当前浏览器会话与本地 Python 服务中', 'Win7 离线兼容版 · 本地浏览器计算 · 无 Python · 无网络请求')
page = page.replace('请从 EXE 控制窗口的“打开分析页面”进入；分析时保持控制窗口开启。', '打开本文件即可运行；不需要启动服务器。')
# 教学示例自带已知标定和理论真值，直接复用这些标定；实际上传图仍自动识别。
page = page.replace("if($('autoOnUpload').checked)await runAutomatic()});\nasync function runAutomatic()",
                    "if($('autoOnUpload').checked)await $('analyze').onclick()});\nasync function runAutomatic()")
out = root / 'dist/win7/SpringOscillatorLab-Win7.html'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(page, encoding='utf-8')
print(out)

# Streamlit 部署直接读取已生成的页面，不在云端安装 OpenCV、OCR 或启动 FastAPI。
cloud = root / 'streamlit_app/frontend/index.html'
cloud.parent.mkdir(parents=True, exist_ok=True)
cloud_page = page.replace('弹簧振子 · Win7 离线兼容版</title>', '弹簧振子 · 在线教学版</title>')
cloud_page = cloud_page.replace('Win7 离线版 v1.2 · 学生简洁版', '浏览器分析已就绪 · 学生简洁版')
cloud_page = cloud_page.replace('Win7 离线兼容版 · 本地浏览器计算 · 无 Python · 无网络请求', '教学在线版 · 图片与计算在浏览器内处理')
cloud_page = cloud_page.replace('图片与计算只在本地浏览器中处理。请使用 Chrome 109 或 Edge 109；IE 不支持。', '图片与计算在当前浏览器中处理，推荐使用 Chrome 或 Edge。')
cloud.write_text(cloud_page, encoding='utf-8')
print(cloud)
