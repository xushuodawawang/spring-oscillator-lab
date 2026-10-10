# 部署到 Streamlit

GitHub 仓库：https://github.com/xushuodawawang/spring-oscillator-lab

1. 打开 https://share.streamlit.io ，登录并点击 **Create app → Yup, I have an app**。
2. 填写下面三项，也可直接粘贴入口的 GitHub 链接。

| 项目 | 填写内容 |
| --- | --- |
| Repository | `xushuodawawang/spring-oscillator-lab` |
| Branch | `main` |
| Main file path | `streamlit_app/app.py` |

入口链接：https://github.com/xushuodawawang/spring-oscillator-lab/blob/main/streamlit_app/app.py

3. **Advanced settings** 里选 Python **3.12**，点击 **Deploy**。不需要配置 Secrets 或 API Key。

部署成功后，复制 Streamlit 生成的 `*.streamlit.app` 地址，发给学生即可。以上是部署配置，仓库本身不是已经上线的 Streamlit 网站。

## 本地运行

在项目根目录执行：

```bash
python -m pip install -r streamlit_app/requirements.txt
python -m streamlit run streamlit_app/app.py
```

Streamlit 入口只依赖 Streamlit。`streamlit_app/requirements.txt` 与入口同目录，Community Cloud 会使用这份依赖。根目录的 `requirements.txt` 是原有 Python/FastAPI 完整版的依赖，不是本部署入口。

## 功能与维护

保留学生简洁版：自动标定、红蓝对比、逐个完整波形的周期和振幅、相对上次和首次的衰减、平均位移差、结论；手动标定、透视校正和专业指标默认收起。上传的图像只在当前浏览器内按像素分析，不发送给 Python 后端。

坐标轴仍然必须建立。本地字体模板自动识别适用于清晰的数字截图；模糊图片、透视拍照或复杂字体可能需要展开高级设置手动校正。两端不完整波形不计入周期，程序不会强制振幅递减。

`streamlit_app/frontend/index.html` 是提交在仓库中的完整页面；云端不需要编译前端、安装 OCR 模型或启动额外端口。它由公共前端 `index.html`、`student-display.js` 和 `win7/offline-engine.js` 生成。

修改公共前端或计算引擎后，在装好根目录完整版依赖的开发环境执行：

```bash
python win7/build_offline.py
```

此命令同时更新 Win7 离线 HTML 与 Streamlit 页面。把源文件和新生成的 `streamlit_app/frontend/index.html` 一起提交，Streamlit 会随仓库更新。

官方说明：[部署步骤](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)、[入口与依赖文件位置](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization)。
