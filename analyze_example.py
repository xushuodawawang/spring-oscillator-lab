"""分析用户本次实验图，生成带三个标定标记的独立离线网页报告。"""
import base64
import csv
import io
import json
from pathlib import Path
import shutil
import sys

from analysis import Settings, analyze, decode_image


def main():
    root = Path(__file__).resolve().parent
    folder = root / "examples"
    folder.mkdir(exist_ok=True)
    original = Path(sys.argv[1])
    destination = folder / "experiment.jpg"
    if original.resolve() != destination.resolve():
        shutil.copyfile(original, destination)
    raw_image = destination.read_bytes()
    cfg = Settings(origin={"x": 35, "y": 133}, x_point={"x": 1180, "y": 133},
        y_point={"x": 35, "y": 43}, x_value=5, y_value=1,
        unit="纵轴单位", roi=[36, 15, 1180, 253])
    result = analyze(decode_image(raw_image), cfg)
    (folder / "experiment-analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "experiment-calibration.json").write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["周期", "起点_s", "终点_s", "振幅_纵轴单位", "周期_s", "振幅变化_pct", "周期变化_pct"])
    for cycle in result["cycles"]:
        writer.writerow([cycle["number"], cycle["start"], cycle["end"], cycle["amplitude"],
            cycle["period"], cycle["amplitude_change_pct"], cycle["period_change_pct"]])
    (folder / "experiment-cycles.csv").write_text(output.getvalue(), encoding="utf-8-sig")
    template = (root / "index.html").read_text(encoding="utf-8")
    template = template.replace('<script>', '<script>window.SPRING_REPORT=true;</script><script>', 1)
    payload = json.dumps({"image": base64.b64encode(raw_image).decode(),
        "settings": cfg.model_dump(), "result": result}, ensure_ascii=False).replace("</", "<\\/")
    bootstrap = """
<script>
const example = __PAYLOAD__;
(async () => {
    const binary=atob(example.image), bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));
    await loadImage(new File([bytes],'experiment.jpg',{type:'image/jpeg'}));
    const c=example.settings;
    points={origin:c.origin,x_point:c.x_point,y_point:c.y_point}; roi=c.roi;
    for(const [id,value] of Object.entries({t0:c.t0,y0:c.y0,xValue:c.x_value,yValue:c.y_value,unit:c.unit}))$(id).value=value;
    updateLabels(); setMode(null); result=example.result; renderResults(); drawImage();
    document.title='本次实验图 · 标定与分析报告';
    document.querySelector('header h1').textContent='本次实验图 · 标定与分析报告';
    document.querySelector('header p').textContent='已标定：① (0,0)；② (5秒,0)；③ (0,1)。这里是预先计算的离线报告，可切换曲线和导出数据。';
    $('modeHint').textContent='① 在纵轴与黑色水平轴的交点；② 在5.0秒竖网格与黑色水平轴的交点；③ 在1.0位移水平网格与纵轴的交点。';
    $('demoTruth').textContent='当前显示你提供的实验图。纵轴单位未标注，结果沿用纵轴刻度单位。';
    for(const id of ['upload','demo','analyze','autoAnalyze','autoOnUpload','clearRoi','perspective','t0','y0','xValue','yValue','unit','hLow','hHigh','sMin','vMin','spacing','prominence','maxGap','smoothWindow','minComponent','includeOffset'])$(id).disabled=true;
    document.querySelectorAll('[data-mode]').forEach(button=>button.disabled=true);
    $('analyze').textContent='本图分析已完成';
    status('本图已分析完成，可直接查看结果。分析新图片或重新标定，请双击 SpringOscillatorLab-v1.2.exe。');
    document.querySelector('footer').textContent='离线报告 · 无需本地服务 · 新图片请使用 EXE 上传、标定并分析';
})().catch(error=>status(error.message,true));
</script>
<style>button:disabled{cursor:default}input:disabled{color:#41586a!important}</style>
""".replace("__PAYLOAD__", payload)
    (folder / "experiment-report.html").write_text(template.replace("</body>", bootstrap + "</body>"), encoding="utf-8")
    print(json.dumps({"report": str(folder / "experiment-report.html"),
        "cycles": result["cycles"], "standard": result["standard"], "metrics": result["metrics"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
