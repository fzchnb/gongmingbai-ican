# 工明白

工明白是一款面向装修、安装和搬运等零工劳动者的 AI 务工助手。用户可以按项目记录工作和工钱，核对与老板的微信沟通，并整理可导出的务工档案。

## 核心功能

- **语音记工**：将口述转为文字，辅助填写工作日期、工时、工价和借支；用户核对后保存。
- **对话纠正**：通过文字或语音修改草稿和已保存记录。
- **截图核账**：提取用户上传的微信截图信息，结合项目账本辅助核对。
- **本人确认到账**：识别到付款线索后，用户核实并确认，系统再更新账本。
- **务工档案**：按项目整理记工、沟通和收款记录，支持导出 PDF 或原文件备份。

AI 负责语音转写、信息提取和表达辅助；金额计算、数据校验和账本更新由程序处理，关键账目由用户确认。应用不会自动读取微信或银行账户。

## 技术结构

- `Frontend/`：uni-app、Vue 3 前端，支持 H5 与 Android。
- `Backend/`：Python / FastAPI 服务、业务流程、测试和数据库结构。
- `Backend/supabase/schema.sql`：Supabase 数据库初始化结构。
- `render.yaml`：Render 后端部署配置模板。

语音、视觉和文本能力使用阿里云百炼模型，使用者需要自行配置服务；后端支持本地 SQLite 及 Supabase。字体许可说明见各字体目录。

## 本地运行

需要 Python 3.12、Node.js 20+ 和 npm。以下命令以 Windows PowerShell 为例，在项目根目录执行：

```powershell
python -m venv Backend/.venv
Backend/.venv/Scripts/python.exe -m pip install -r Backend/requirements.txt
Copy-Item Backend/.env.example Backend/.env
cd Frontend
npm ci
```

在 `Backend/.env` 中配置自己的 `DASHSCOPE_API_KEY` 才能使用 AI 功能。云端部署还需配置自己的 Supabase 地址和密钥，初始化 `Backend/supabase/schema.sql`，并根据环境设置私有存储。请勿将真实密钥提交到仓库。

分别在两个终端运行：

```powershell
cd Backend
.venv/Scripts/python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

```powershell
cd Frontend
npm run dev:h5
```

浏览器打开 `http://127.0.0.1:5173`，并将应用中的后端地址设为 `http://127.0.0.1:8000`。手机访问时需改为手机可访问的后端地址；手机上的 `127.0.0.1` 指手机本身。Android 构建可使用 HBuilderX 打开前端项目。

## 测试

前端在 `Frontend/` 运行 `npm test`。后端在 `Backend/` 运行 `python tests/run_isolated.py`；测试不等同于模型在所有场景下的识别准确率。

本项目作为可演示的 AI 产品原型提供；导出的档案用于整理和核对资料，不构成第三方真实性认证或司法认定。
