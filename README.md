# WeChat AI Bot

让 AI 替你自动回复微信消息，模仿你的语气和风格。

## 功能

- **自动回复**：私聊全自动回复，群聊 @你时回复
- **人格模仿**：上传聊天记录分析风格，或手动添加对话示例训练
- **Web 控制面板**：浏览器管理一切——启停、联系人、日志、配置、训练
- **多模型支持**：DeepSeek / 千问 / OpenAI 兼容 API 均可
- **微信版本自适应**：自动检测微信版本选择合适的后端

## 一键部署

### 前提

- Windows 10/11
- Python 3.10+
- PC 微信已安装并登录

### 安装

```bash
# 1. 进入项目目录
cd claude

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key
# 编辑 .env 文件，填入你的 LLM API Key
notepad .env

# 4. 启动
python app.py
```

浏览器自动打开 `http://localhost:7860`。

### .env 最简配置

```ini
LLM_API_KEY=sk-你的key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
CONTACT_LIST=张三,李四
```

## 架构

```
wechat-ai-bot/
├── app.py                  # 主入口 (Gradio Web UI + Bot Engine)
├── database.py             # SQLite 数据层
├── config.py               # 统一配置管理
├── llm_client.py           # LLM 客户端
├── requirements.txt        # Python 依赖
├── start.bat               # Windows 一键启动
│
├── personality/            # 人格引擎
│   ├── trainer.py          # 聊天记录分析 → 提取风格特征
│   ├── prompt_builder.py   # 动态构建 System Prompt
│   └── fewshot_manager.py  # Few-shot 示例管理
│
├── wechat/                 # 微信适配层
│   ├── adapter_base.py     # 抽象接口
│   ├── wx4py_adapter.py    # 微信 4.x 适配器
│   ├── uia_adapter.py      # 通用回退适配器
│   └── version_detector.py # 版本自动检测
│
├── web/                    # Gradio Web 控制面板
│   ├── ui_dashboard.py     # 仪表盘
│   ├── ui_logs.py          # 实时日志
│   ├── ui_contacts.py      # 联系人管理
│   ├── ui_history.py       # 聊天记录
│   ├── ui_config.py        # 系统配置
│   └── ui_training.py      # 人格训练
│
└── data/                   # 数据目录 (自动创建)
```

## 使用指南

### 1. 配置 LLM

打开 Web UI → **配置** Tab → 填入 API Key / Model / Base URL → 点「测试连接」→ 确认后保存。

### 2. 添加联系人

Web UI → **联系人** Tab → 添加要监控的联系人名称（微信里显示的备注名或昵称）。

### 3. 启动 Bot

Web UI → **仪表盘** Tab → 点「启动 Bot」。确保微信窗口可见。

### 4. 训练人格

#### 方式 A：手动 Few-Shot（最简单）

Web UI → **人格训练** → **Few-Shot 管理** → 填写「对方消息」和「你的回复」，添加 10-20 组即可。

#### 方式 B：上传聊天记录

1. 用 WeChatMsg 等工具导出聊天记录为 CSV
2. Web UI → **人格训练** → **上传聊天记录** → 选择文件 → 分析 → 保存为风格档案
3. 去 **配置** Tab → **人格档案** → 激活新档案

## 案例演示

### 案例 1：基础自动回复

**场景**：你有一个小号，想让 AI 帮你回复好友消息。

1. `.env` 中设置 `CONTACT_LIST=小明,小红`
2. 启动 Bot
3. 小明发「在吗」→ Bot 自动回复「在的在的～」

### 案例 2：模仿你的风格

**场景**：你想让回复听起来像你本人。

1. 去「人格训练」Tab，添加几组你平时的对话示例：
   - 对方: 「吃了吗」 → 你: 「没呢 你请我啊哈哈哈」
   - 对方: 「周末干嘛」 → 你: 「躺平 哪也不想去」
2. 再跟 bot 聊天，它就会用类似的语气回复

### 案例 3：群聊客服

**场景**：在某个群里当客服 bot。

1. `CONTACT_LIST=` 留空
2. `GROUP_LIST=客户群`
3. 群里有人 @bot → 自动回复

## 常见问题

**Q: 微信窗口能最小化吗？**
A: 不能。wx4py 通过 UI 自动化操作微信，窗口必须可见。

**Q: 支持哪些 LLM？**
A: 所有 OpenAI 兼容接口：DeepSeek、千问、智谱、OpenAI、Ollama 等。

**Q: 回复太慢？**
A: 调整 `.env` 中 `REPLY_MIN_DELAY` 和 `REPLY_MAX_DELAY`。

**Q: Bot 偶尔不回复？**
A: 配置了 `SKIP_REPLY_PROBABILITY=0.05`（5% 概率跳过），模拟真人偶尔不回消息。设为 0 可关闭。

## 许可证

MIT
