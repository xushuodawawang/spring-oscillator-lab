"""EXE入口：后台运行本地服务，提供可关闭的桌面控制窗口。"""
import argparse
import logging
import os
from pathlib import Path
import socket
import sys
import threading
import time
import traceback
import webbrowser
import urllib.request
import json


def main():
    parser = argparse.ArgumentParser(description="Spring Oscillator Lab")
    parser.add_argument("--headless", action="store_true", help="自动化验证时不显示控制窗口")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--quit-after", type=float, default=0)
    args = parser.parse_args()
    folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SpringOscillatorLab"
    folder.mkdir(parents=True, exist_ok=True)
    logfile = folder / "spring-lab.log"
    logging.basicConfig(filename=logfile, level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        # 在 onefile 模式中 app.py 的 __file__ 指向解包目录，index.html 随包包含。
        import uvicorn
        from app import app
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        preferred = args.port or 8766
        try:
            sock.bind(("127.0.0.1", preferred))
        except OSError:
            if args.port:
                raise
            # 重复双击时复用同一应用的服务，使用户已有浏览器标签继续有效。
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(f"http://127.0.0.1:{preferred}/health", timeout=2) as response:
                    existing = json.load(response)
                if existing.get("app") == "spring-oscillator-lab" and existing.get("version") == app.version:
                    if not args.no_browser:
                        webbrowser.open(f"http://127.0.0.1:{preferred}/")
                    sock.close()
                    return 0
            except Exception:
                pass
            sock.bind(("127.0.0.1", 0))  # 端口被其他程序占用时安全选择空闲端口。
        sock.listen(128)
        port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}/"
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
            log_config=None, loop="asyncio", http="h11", ws="none", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 30
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("本地服务启动失败，请查看日志。")
            time.sleep(.05)
        logging.info("READY %s", url)
        if not args.no_browser:
            webbrowser.open(url)
        if args.quit_after > 0:
            def timed_stop():
                server.should_exit = True
            timer = threading.Timer(args.quit_after, timed_stop)
            timer.daemon = True
            timer.start()
        if args.headless:
            thread.join()
        else:
            import tkinter as tk
            from tkinter import ttk
            root = tk.Tk()
            root.title("弹簧振子实验分析")
            root.geometry("470x230")
            root.resizable(False, False)
            body = ttk.Frame(root, padding=22)
            body.pack(fill="both", expand=True)
            ttk.Label(body, text="弹簧振子 · 物理实验工作台", font=("Microsoft YaHei", 14, "bold")).pack(anchor="w")
            ttk.Label(body, text="本地服务已启动。请在浏览器中上传图片并分析。", wraplength=425).pack(anchor="w", pady=(12, 4))
            ttk.Label(body, text=url).pack(anchor="w")
            ttk.Label(body, text="浏览器关闭后服务仍运行；关闭此窗口即可退出。", wraplength=425).pack(anchor="w", pady=8)
            buttons = ttk.Frame(body)
            buttons.pack(anchor="w", pady=8)
            ttk.Button(buttons, text="打开分析页面", command=lambda: webbrowser.open(url)).pack(side="left", padx=(0, 12))
            def close():
                server.should_exit = True
                root.destroy()
            ttk.Button(buttons, text="退出程序", command=close).pack(side="left")
            root.protocol("WM_DELETE_WINDOW", close)
            def watch():
                if not thread.is_alive():
                    root.destroy()
                else:
                    root.after(500, watch)
            root.after(500, watch)
            root.mainloop()
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        logging.info("STOPPED")
        return 0
    except Exception:
        logging.error(traceback.format_exc())
        if not args.headless:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"程序启动失败。\n日志：{logfile}", "弹簧振子实验分析", 16)
        return 1


if __name__ == "__main__":
    sys.exit(main())
