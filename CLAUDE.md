# 微信 AI 自动回复机器人

## 项目概述

这是一个 Windows 桌面应用，通过 wx4py 库自动化控制 PC 微信 4.x，实现 AI 自动回复消息。带 Gradio Web 控制面板。

## 启动

```bash
cd C:\Users\28708\wechat-ai-bot && python app.py
# Web UI: http://localhost:7860
```

## 核心架构

```
微信 4.x (前台) → wx4py (双击侧边栏→独立窗口→读消息气泡)
    → BotEngine (消息队列 → LLM → 回复)
    → Gradio Web UI (7个Tab控制面板)
```

### 关键技术

- **微信交互**: wx4py (UIAutomation 封装库)
- **消息监听**: 双击侧边栏联系人 → 弹出独立窗口 → 读取 `mmui::ChatTextItemView` 消息气泡
- **消息队列**: Python `queue.Queue`，单 worker 线程串行处理，保证上下文不乱
- **LLM**: OpenAI 兼容 API (DeepSeek/千问/智谱等)，URL 自动补全 `/v1/chat/completions`
- **存储**: JSON 文件 (`data/*.json`)，线程安全

## 文件结构

```
wechat-ai-bot/
├── app.py                  # 主入口: Gradio UI + BotEngine
├── database.py             # JSON 文件存储层 (所有 CRUD)
├── config.py               # 配置管理 (.env + settings.json)
├── llm_client.py           # LLM 客户端 (OpenAI 兼容)
├── screen_capture.py       # PrintWindow 截图 (替代剪贴板)
├── ui_detector.py           # OpenCV UI 检测 (气泡/图片块/红点)
├── ocr_reader.py            # OCR 文字提取 (PaddleOCR→RapidOCR)
├── vision.py               # 识图管道: 截图→检测→裁剪→OCR/VL双路线
├── image_gen.py            # 图片生成框架 (抽象接口)
├── requirements.txt        # pip 依赖
├── start.bat               # 一键启动脚本
├── .env                    # 环境变量 (API Key 等)
├── CLAUDE.md               # 本文档
│
├── personality/            # 人格引擎
│   ├── prompt_builder.py   # 动态构建 System Prompt (支持纯AI/人格双模式)
│   ├── trainer.py          # 聊天记录分析 → 提取风格特征
│   └── fewshot_manager.py  # Few-shot 示例管理
│
├── wechat/                 # 微信适配层
│   ├── adapter_base.py     # 抽象接口 (WeChatAdapter)
│   ├── wx4py_adapter.py    # 微信 4.x 实现 (主力)
│   ├── uia_adapter.py      # 通用 UIA 回退
│   └── version_detector.py # 微信版本检测
│
├── web/                    # Gradio Web UI
│   ├── ui_main.py          # 主布局 (7个Tab)
│   ├── ui_dashboard.py     # 仪表盘: 状态/统计/启停
│   ├── ui_logs.py          # 日志: 日期筛选
│   ├── ui_contacts.py      # 联系人: 增删启用
│   ├── ui_history.py       # 聊天记录: 日期/联系人/关键词筛选
│   ├── ui_config.py        # 配置: 多LLM配置切换+AI模式+回复策略
│   ├── ui_training.py      # 人格训练: AI创建+聊天记录分析+few-shot
│   ├── ui_emojis.py        # 表情包: 自动扫描+标签(关键词/情绪/场景/注释)
│   └── ui_memories.py      # 记忆: 直接编辑文本+增删
│
├── data/                   # 数据目录 (JSON文件)
│   ├── contacts.json       # 联系人
│   ├── messages.json       # 聊天记录
│   ├── settings.json       # 配置键值
│   ├── profiles.json       # 人格档案 (含fewshots)
│   ├── configs.json        # LLM多配置
│   ├── emojis.json         # 表情包标签
│   ├── memories.json       # 对话记忆
│   └── logs.json           # 运行日志
│
└── emojis/                 # 表情包图片文件目录
```

## LLM 回复特殊标记

Bot 解析 LLM 回复中的特殊标记：

| 标记 | 功能 | 示例 |
|------|------|------|
| `[SKIP]` | 不回复 | |
| `[STICKER:关键词]` | 发送表情包 | `[STICKER:哈哈]` |
| `[IMAGE:描述]` | 生成图片(待接入) | `[IMAGE:a cat]` |
| `[MEMORY:事实]` | 自动记忆 | `[MEMORY:喜欢喝咖啡]` |

## 消息处理流程

```
聊天窗口消息气泡 → monitor._poll() → on_message 回调
  → 群聊未@: 只存上下文
  → 群聊@或私聊: 进 msg_queue
  → worker 线程: _handle_message()
    → 缓冲窗口 (1.5s内多条合并)
    → 图片检测 (UIA标记 → PrintWindow截图 → OpenCV检测气泡 → OCR/VL识别)
    → 加载记忆 (群聊: 群记忆+发信人记忆)
    → 构建 System Prompt (纯AI模式/人格模式)
    → LLM.chat() → 解析标记
    → 延迟 → send_message + send_file(表情包)
```

## 群聊逻辑

- 消息全部读取 (存上下文)
- 只有 `@机器人名` 才触发回复 (机器人名在配置页设置)
- 记忆按发送者存储 (不是存到群名)

## API 配置

- 支持多配置保存/切换 (类似 ccswitch)
- 运营商预设: DeepSeek/千问/智谱/OpenAI/Kimi/SiliconFlow/Ollama
- AI 模式: `persona` (人格模式) / `pure` (纯AI模式)
- 回复策略: 延迟/跳过率/冷却

## 常见问题

- **微信窗口必须可见**，不能最小化
- **群聊需要设置机器人名称**才能正确 @ 检测
- **表情包**放 `emojis/` 目录，在 Web UI 打标签
- **识图** 有三条路线: lightweight (OCR→文本LLM) / vision (截图→VL) / auto (自动选择)
- **数据文件**在 `data/*.json`，可直接编辑

## 依赖

```
gradio>=5.0
wx4py>=0.2.1
openai>=1.58
jieba>=0.42
pywin32>=305
Pillow>=10.0
opencv-python-headless>=4.8
numpy>=1.24
paddleocr>=2.7 (可选，Python 3.8-3.12)
rapidocr-onnxruntime>=1.3
```
