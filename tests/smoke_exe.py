"""运行打包后的EXE，远离源码目录且移除Python环境变量，验证内置资源及依赖。"""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

import httpx


def run():
    exe = Path(__file__).resolve().parents[1] / "dist" / "SpringOscillatorLab-v1.2.exe"
    port = 8765
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))  # 确认验证端口空闲，避免误测其他服务。
    env = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "CONDA_PREFIX"):
        env.pop(key, None)
    env["PATH"] = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    with tempfile.TemporaryDirectory(prefix="spring-lab-exe-check-") as cwd:
        process = subprocess.Popen([str(exe), "--headless", "--no-browser", "--port", str(port), "--quit-after", "30"],
            cwd=cwd, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=15) as client:
                deadline = time.monotonic() + 25
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(f"EXE exited early: {process.returncode}")
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if time.monotonic() > deadline:
                        raise RuntimeError("EXE startup timeout")
                    time.sleep(.2)
                page = client.get("/")
                assert page.status_code == 200 and "弹簧振子" in page.text
                settings = client.get("/api/demo-settings").json()
                settings.pop("truth")
                image = client.get("/api/demo.png").content
                response = client.post("/api/analyze", files={"file": ("demo.png", image, "image/png")},
                    data={"settings": json.dumps(settings)})
                assert response.status_code == 200, response.text
                data = response.json()
                assert data["summary"]["cycle_count"] == 4
                assert abs(data["standard"]["period"] - 2) < .04
                assert data["preview"]["mask"].startswith("data:image/png;base64,")
                # 直接测试 EXE 内置 OCR 模型。这里不提交任何标定点或已知刻度参数。
                auto = client.post("/api/auto-analyze", files={"file": ("demo.png", image, "image/png")})
                assert auto.status_code == 200, auto.text
                assert auto.json()["summary"]["cycle_count"] == 4
                assert abs(auto.json()["standard"]["period"] - 2) < .04
                print("EXE automatic OCR calibration: PASS", flush=True)
                print(json.dumps({"exe_api": "PASS", "url": str(client.base_url),
                    "cycles": 4, "T1": data["standard"]["period"], "A1": data["standard"]["amplitude"],
                    "RMSE": data["metrics"]["all_observed"]["rmse"]}), flush=True)
            assert process.wait(timeout=35) == 0
            print("EXE graceful shutdown: PASS", flush=True)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        # 验证无控制台的桌面窗口分支正常创建并在计时结束后退出。
        gui = subprocess.Popen([str(exe), "--no-browser", "--quit-after", "3"], cwd=cwd, env=env,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            assert gui.wait(timeout=35) == 0
            print("EXE desktop control window: PASS", flush=True)
        finally:
            if gui.poll() is None:
                gui.terminate()
                gui.wait(timeout=10)


if __name__ == "__main__":
    run()
