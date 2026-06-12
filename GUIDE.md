# 微信 AI Bot — 使用指南

## 快速开始

```bash
# 第一次: 一键初始化
双击 setup.bat → 编辑 .env 填入 API Key → 双击 start.bat

# 之后直接
双击 start.bat
```

Web UI: `http://localhost:7860`

---

## 🏖 不影响电脑正常使用 — 三种隔离方案

Bot 运行时需要控制微信窗口（点击、输入），会占用鼠标键盘。以下方案让你**同时处理工作**：

### 方案一: 双 Windows 用户 (⭐ 推荐，所有版本)

```
设置 → 账户 → 其他用户 → 添加账户 → 创建本地用户(如 bot)
→ Win+L 切换到 bot 用户 → 安装微信 + 登录 + 启动 Bot
→ Win+L 切回主用户继续工作，Bot 在后台用户静默运行
```

- ✅ 所有 Windows 版本都支持
- ✅ 微信一次登录永久保持，无需额外配置
- ✅ Bot 在后台用户中运行，完全不干扰主用户
- ✅ 不需要 Pro 版，不需要虚拟化

### 方案二: 虚拟机

```
安装 VirtualBox / VMware → 创建 Windows 虚拟机
→ 虚拟机里: 安装微信 + 运行 Bot
→ 宿主机正常工作
```

- ✅ 最彻底隔离
- ⚠️ 需要额外 Windows 许可证
- ⚠️ 占用资源较多 (建议 8GB+ 内存)

---

## 隐私保护

### 绝不会上传到 GitHub

`.gitignore` 已配置排除:
| 类型 | 排除内容 |
|------|----------|
| 密钥 | `.env`（含 API Key） |
| 聊天数据 | `data/chats/*.txt`、`data/messages.json`、`data/memories.json` |
| 日志 | `*.log`、`data/logs.json` |
| 联系人 | `data/contacts.json` |
| 配置 | `data/configs.json`、`data/settings.json`（含你的 Key） |
| 表情包 | `emojis/` 下所有图片 |
| 虚拟环境 | `venv/` |

### 首次推送前确认

```bash
git status  # 确认只有代码文件，没有 .env 或 data/ 下的个人文件
```

---

## 项目结构

```
wechat-ai-bot/
├── app.py                  # 主入口
├── config.py               # 配置管理
├── llm_client.py           # LLM 客户端
├── chat_store.py           # 聊天记录文本存储 (data/chats/*.txt)
├── vision.py               # 识图管道 (PrintWindow→OpenCV→OCR/VL)
├── screen_capture.py       # PrintWindow 窗口截图
├── ui_detector.py          # OpenCV UI 检测
├── ocr_reader.py           # OCR (PaddleOCR→RapidOCR)
├── image_gen.py            # 图片生成
├── database.py             # JSON 数据层
│
├── setup.bat               # 一键初始化 (venv + .env + 依赖)
├── start.bat               # 启动脚本
├── sandbox.wsb             # Windows Sandbox 配置
├── requirements.txt        # pip 依赖
├── .env.example            # 配置模板 (可提交)
├── .env                    # 真实配置 (gitignore 保护)
│
├── personality/
│   ├── prompt_builder.py   # Prompt 构建器
│   └── persona_cloner.py   # 角色克隆引擎
│
├── wechat/
│   ├── adapter_base.py     # 抽象接口
│   ├── wx4py_adapter.py    # 微信 4.x 适配器
│   ├── uia_adapter.py      # 通用 UIA 回退
│   └── version_detector.py # 版本检测
│
├── web/                    # Gradio Web UI
│   ├── ui_main.py          # 主布局
│   ├── ui_dashboard.py     # 仪表盘
│   ├── ui_config.py        # 配置 (LLM + 人格克隆 + 识图)
│   ├── ui_contacts.py      # 联系人管理
│   ├── ui_history.py       # 聊天记录
│   ├── ui_emojis.py        # 表情包
│   ├── ui_memories.py      # AI 记忆
│   └── ui_logs.py          # 日志
│
├── data/chats/             # 聊天文本文件 (gitignore)
├── emojis/                 # 表情包图片 (gitignore)
└── venv/                   # 虚拟环境 (gitignore)
```

---

## 依赖

```
gradio>=5.0
wx4py>=0.2.1
openai>=1.58
jieba>=0.42
pywin32>=305
Pillow>=10.0
pyautogui>=0.9
opencv-python-headless>=4.8
numpy>=1.24
rapidocr-onnxruntime>=1.3
```

---

## 常见问题

- **微信窗口必须可见**，不能最小化
- **群聊需要设置机器人名称** 才能正确检测 @
- **表情包** 放 `emojis/` 目录，Web UI 打标签
- **识图** 有三条路线: lightweight (OCR→文本LLM) / vision (截图→VL) / auto
- **角色克隆** 上传聊天记录文件，AI 自动分析风格
