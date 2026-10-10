"""Streamlit Community Cloud 入口；图像处理在浏览器内完成。"""
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent

st.set_page_config(page_title="弹簧振子 · 看图分析", page_icon="〰️", layout="wide")

# 组件中只加载项目自带的代码；上传的图片仅按图像像素读取。
lab = st.components.v2.component(
    "spring_oscillator_lab",
    html='<div id="lab-host"></div>',
    css="#lab-host{width:100%}iframe{display:block;width:100%;border:0;background:#f2f6f8}",
    js=(ROOT / "bridge.js").read_text(encoding="utf-8"),
)

st.markdown(
    """<style>
    .stMainBlockContainer{padding:1rem 0.5rem;max-width:1200px}
    </style>""",
    unsafe_allow_html=True,
)
lab(
    data={"page": (ROOT / "frontend/index.html").read_text(encoding="utf-8")},
    key="spring-lab",
)
