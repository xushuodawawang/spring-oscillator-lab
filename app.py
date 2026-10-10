"""启动：python -m uvicorn app:app --host 127.0.0.1 --port 8000"""
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from analysis import AnalysisError, Settings, analyze, decode_image
from auto_calibration import auto_analyze

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="弹簧振子实验分析", version="1.2.0")


@app.get("/")
def home():
    return FileResponse(ROOT / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "app": "spring-oscillator-lab", "version": "1.2.0"}


@app.post("/api/auto-analyze")
def auto_analyze_upload(file: UploadFile = File(...), unit: str = Form("纵轴单位"), include_offset: bool = Form(False)):
    data = file.file.read(12 * 1024 * 1024 + 1)
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(413, "图片文件不能超过 12 MB。")
    if len(unit) > 20:
        raise HTTPException(422, "位移单位不能超过20个字符。")
    try:
        return auto_analyze(decode_image(data), unit.strip() or "纵轴单位", include_offset)
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/analyze")
def analyze_upload(file: UploadFile = File(...), settings: str = Form(...)):
    # 同步路由由 FastAPI 在线程池执行，CPU 图像处理不堵塞事件循环。
    data = file.file.read(12 * 1024 * 1024 + 1)
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(413, "图片文件不能超过 12 MB。")
    if len(settings) > 16000:
        raise HTTPException(400, "标定参数过长。")
    try:
        cfg = Settings.model_validate_json(settings)
        return analyze(decode_image(data), cfg)
    except ValidationError as exc:
        message = "；".join(str(e["msg"]) for e in exc.errors(include_url=False))
        raise HTTPException(422, "参数错误：" + message) from exc
    except AnalysisError as exc:
        raise HTTPException(422, str(exc)) from exc


def demo_image(damping=0.045):
    """可复核的合成实验图：A(t)=exp(-0.045t)，T=2s，初相位0.25rad。"""
    image = np.full((600, 1100, 3), 255, np.uint8)
    for px in range(80, 1081, 100):
        cv2.line(image, (px, 60), (px, 540), (225, 225, 225), 1)
        cv2.putText(image, str((px - 80) // 100), (px - 6, 565), cv2.FONT_HERSHEY_SIMPLEX, .55, (65, 65, 65), 1)
    for py in range(60, 541, 60):
        cv2.line(image, (80, py), (1080, py), (225, 225, 225), 1)
        cv2.putText(image, f"{(300-py)/180:.2f}", (6, py + 5), cv2.FONT_HERSHEY_SIMPLEX, .45, (65, 65, 65), 1)
    cv2.line(image, (80, 300), (1080, 300), (50, 50, 50), 2)
    cv2.line(image, (80, 60), (80, 540), (50, 50, 50), 2)
    t = np.linspace(0, 10, 4000)
    y = np.exp(-damping * t) * np.sin(np.pi * t + .25)
    pts = np.column_stack((80 + 100 * t, 300 - 180 * y)).round().astype(np.int32)
    cv2.polylines(image, [pts], False, (150, 45, 225), 3, cv2.LINE_AA)
    return image


@app.get("/api/demo.png")
def demo():
    _, data = cv2.imencode(".png", demo_image())
    return Response(data.tobytes(), media_type="image/png")


@app.get("/api/demo-settings")
def demo_settings():
    return {"origin": {"x": 80, "y": 300}, "x_point": {"x": 580, "y": 300},
        "y_point": {"x": 80, "y": 120}, "x_value": 5, "y_value": 1,
        "roi": [82, 65, 1078, 535], "truth": "A(t)=exp(-0.045t) cm；T=2 s；相位=0.25 rad。"}
