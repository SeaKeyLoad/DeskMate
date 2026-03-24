# AIChat - 桌宠与Web双端智能对话系统

## 项目简介

AIChat 是一个集桌面宠物与Web应用于一身的智能对话系统。支持Ollama本地推理和OpenAI兼容API，提供完整的会话管理、记忆系统和多模态交互能力。

### 核心特性

- 🖥️ **双端应用**：PyQt6桌宠应用和Flask Web应用
- 🧠 **智能记忆系统**：多层级内存管理、长期存储、向量检索
- 🤖 **灵活模型支持**：支持Ollama本地推理和OpenAI API兼容接口
- 📸 **多模态能力**：文本、图像输入和分析
- 🛠️ **工具集成**：搜索、文件操作、图像处理等功能
- 👤 **用户系统**：会话隔离、个性化设置、用户认证
- 💾 **会话管理**：Web聊天、桌宠聊天、长期记忆持久化

---

## 系统要求

### 环境配置
- **Python**：3.10.19
- **操作系统**：Windows（主要支持）
- **GPU **：CUDA 11.8+ (用于本地LLM加速) 本人使用的12.4

### Python依赖

| 包名 | 版本 | 用途 |
|------|------|------|
| torch | 2.4.1 | 深度学习框架 |
| torchaudio | 2.4.1 | 音频处理 |
| torchvision | 0.19.1 | 计算机视觉工具 |
| transformers | 4.57.3 | 预训练模型 |
| numpy | 1.26.4 | 数值计算 |
| modelscope | 1.34.0 | 模型库支持 |
| Flask | 3.1.2 | Web框架 |
| PyQt6 | 6.10.2 | 桌宠GUI框架 |
| faiss | 1.9.0 | 向量检索 |
| pywin32 | 311 | Windows系统集成 |

### 额外环境需求

以下包虽未在requirements.txt中明确列出，但项目代码中已导入，建议安装：

```
requests>=2.31.0          # HTTP请求库
openai>=1.30.0            # OpenAI API客户端
pillow>=10.1.0            # 图像处理
opencv-python>=4.8.0      # 图像处理和分析
python-dotenv>=1.0.0      # 环境变量管理
pydantic>=2.5.0           # 数据验证
flask-login>=0.6.3        # Flask用户认证
sqlalchemy>=2.0.0         # 数据库ORM
PyYAML>=6.0.0             # YAML配置文件解析
```

---

## 安装与启动

### 1. 环境安装

```bash
# 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装额外依赖
pip install requests openai pillow opencv-python python-dotenv pydantic flask-login sqlalchemy PyYAML
```

### 2. 配置文件设置

编辑或创建 `.env` 文件，使用.env.example将后缀.example去掉。


### 3. 启动应用

#### 桌宠模式

```bash
python DesktopCharacter.py
```

特性：
- 置顶浮窗桌面宠物
- 实时文本对话
- 表情包反馈
- 系统剪贴板监听
- 与Web会话隔离

#### Web模式

```bash
python app.py
```

访问：`http://localhost:8505`

特性：
- Web聊天界面
- 多会话管理
- 用户注册与认证
- 模型参数动态切换
- 实时流式响应

---

## 项目结构

```
AIChat/
├── app.py                      # Web应用入口 (Flask)
├── DesktopCharacter.py         # 桌宠应用入口 (PyQt6)
│
├── 核心模块
├── ├── CharacterChat.py        # 桌宠聊天核心 (PetChatCore)
├── ├── AIService.py            # 聊天处理器 (ChatProcessor)
├── ├── LLModel.py              # 语言模型封装 (多模态支持)
├── ├── SessionContext.py       # 会话与内存管理
├── ├── ToolRegistry.py         # 工具注册与调用
├── ├── AIConfig.py             # 全局配置管理(包含prompt)
├── ├── db.py                   # 数据库操作(并不强制使用)
├── ├── ListenEvent.py          # 系统事件监听
├── ├── VisualAttention.py      # 视觉处理模块
│
├── 配置文件
├── ├── prompt_config.json      # AI角色提示词配置(简单配置，里面可以用一个自定义提示词，也可在AIConfig中新加)
├── ├── requirements.txt        # Python依赖列表
├── ├── .env                    # 环境变量配置（需自行创建）可参考.env.example
│
├── 资源目录
├── ├── CharacterImage/         # 桌宠角色图像和设定
├── ├── templates/              # Flask HTML模板
├── ├── static/                 # 静态资源 (CSS/JS)
├── ├── stickers/               # 表情包资源
├── ├── Tool/                   # 工具集合
├── ├── context_templates/      # 行为规则配置
├── ├── KnowledgeBase/          # 知识库
│
├── 数据存储
├── ├── Memory/storage/         # 会话记忆存储
└── └── users.json              # 用户数据(不使用db.py则账户数据就在这里)
```
---
## 正式启动
首先启动app.py注册一个账号，然后就可以在web和桌面端使用了。
桌面端还需要再prompt_config.json中配置账号密码即可使用，如果要使用自定义形象，只需要在DesktopCharacter.py里将IMAGE_PATH换成你图片路径

## 配置与自定义
### AI角色配置
编辑 `prompt_config.json`：

```json
{
  "user_name": "root",
  "password": "11111111",
  "selected_prompt_name": "温柔妹妹",
  "user_role": "哥哥",
  "prompts": {
    "温柔妹妹": "你是一个温柔贴心的妹妹...",
    "调皮助手": "你是一个调皮可爱的AI助手..."
  }
}
```


---

## 核心功能说明
### 会话管理 (SessionContext.py)

该模块实现了基于对话历史的分层记忆管理系统，支持会话的创建、持久化、压缩归档及长期记忆合并，并确保不同场景（`chat_type`）下会话的隔离性。

---

#### 核心类

- **`MemoryBlock`**  
  通用记忆块，分为两级：
  - **Level 1**：包含压缩后的摘要（JSON）及原始消息，用于近期活跃压缩。  
  - **Level 2**：仅保留摘要及指向长期存储的引用，用于归档后的全局记忆，不保留原始消息以节省内存。

- **`SessionContext`**  
  单个会话的上下文管理器，负责：
  - 消息的添加、活跃缓冲区管理。  
  - 自动触发压缩（Token 阈值、记忆块数量阈值）。  
  - 将压缩后的 Level‑1 块进一步合并为 Level‑2 全局档案。  
  - 提供供 AI 使用的上下文（压缩摘要 + 活跃消息）。  
  - 会话元数据（名称、类型、时间戳）的持久化与软/硬删除。

- **`LongTermMemoryManager`**  
  用户长期记忆管理器，将多个 Level‑1 块（或旧 Level‑2 块）通过 LLM 合并成一份结构化全局档案（`long_term_memory` + `short_term_context`），并持久化为 JSON 文件，替代繁重的向量检索。

- **`MemoryManager`**  
  全局会话管理器，管理所有 `SessionContext` 实例，支持：
  - 按 `user_id`、`chat_type`、`session_id` 唯一标识会话。  
  - 自动复用空会话（无消息）。  
  - 会话的创建、获取、列表查询、名称更新及删除。  
  - 对外提供统一的消息添加和历史获取接口。

---

#### 主要功能

1. **分层记忆压缩**  
   - 活跃缓冲区（`active_buffer`）消息数或 Token 达到阈值时，调用 LLM 生成 Level‑1 摘要，并将原始消息归档。  
   - 当 Level‑1 块数量超过 `SHORT_TERM_MEMORY_LIMIT` 时，将多个 Level‑1 块（及可能存在的旧 Level‑2 块）合并为一份新的 Level‑2 全局档案，仅保留摘要与引用。

2. **多场景隔离**  
   - 每个会话携带 `chat_type` 参数（如 `web_chat`、`pet_chat`），存储路径和内存 Key 均包含该参数，确保不同类型对话互不干扰。

3. **持久化与生命周期**  
   - 会话数据以 JSON 形式存储于 `./Memory/storage/<user_id>/<chat_type>/<session_id>/` 目录下，包含元数据、活跃缓冲区和压缩记忆块。  
   - 支持软删除（仅标记）和硬删除（物理删除文件）。

4. **上下文构建**  
   - `get_full_context_for_ai()` 按顺序返回：  
     - Level‑2 全局档案（结构化 JSON 文本）。  
     - Level‑1 近期摘要。  
     - 当前活跃缓冲区中的原始消息。  
   - 保证 AI 获得连贯、精简且不失关键的上下文。

5. **灵活的消息添加**  
   - `add_message()` 支持指定消息类型（文本、文件等）及是否允许立即触发压缩，可用于特殊场景（如系统消息）的延迟压缩。

---

#### 设计要点

- **压缩策略**：优先在 `assistant` 消息后切割，避免切断一问一答；若无合适切割点，则保留最后 1‑2 条消息。  
- **二级合并**：将多个 Level‑1 块合并为单一的 Level‑2 全局档案，大幅减少长期记忆块数量，同时保留关键状态与连续性信息。  
- **存储结构**：用户级长期记忆独立存放于 `long_term_memory/global_profile.json`，可随账号注销一并清除。

### 多模态处理 (LLModel.py)

`LLModel` 类内置了统一的多模态输入处理能力，支持**图片**和**视频**文件，并提供了自动压缩、抽帧、URL 下载及临时文件清理等配套机制。

#### 支持的文件类型
- **图片**：`.jpg` / `.jpeg` / `.png` / `.gif` / `.bmp` / `.webp`
- **视频**：`.mp4` / `.avi` / `.mov` / `.mkv` / `.webm`（需安装 OpenCV）

#### 核心功能
| 功能 | 说明 |
|------|------|
| **本地文件/URL 输入** | 自动识别 `http://`/`https://` 链接并下载到临时目录，支持重试和流式下载 |
| **图片自动压缩** | 可开启 `auto_compress_image`，将图片最大边长限制为 `max_image_size`（默认 1024），并优化格式（JPEG 质量 85），降低传输开销 |
| **视频自动抽帧** | 可开启 `auto_extract_video_frames`，均匀抽取最多 `max_video_frames`（默认 3）帧作为图像序列传入模型，自动跳过片头/片尾（前 5% 和后 5%） |
| **临时文件管理** | 下载的文件自动存放于项目目录下的 `temp/download/`，支持自动清理（可配置 `cleanup_downloaded_files`），并定期清理 24 小时前的过期文件 |
| **调用级覆盖** | 在 `model_chat` 中可通过参数 `auto_compress_image` / `auto_extract_video_frames` 临时覆盖实例的全局设置 |

#### 使用示例
```python
# 初始化
model = LLModel(
    chat_model="qwen2.5-vl",
    use_ollama=True,
    auto_compress_image=True,      # 全局开启压缩
    max_image_size=1024,
    auto_extract_video_frames=True, # 全局开启视频抽帧
    max_video_frames=3
)

# 单张图片（本地或URL）
result = model.model_chat(
    user_prompt="描述这张图片",
    files=["https://example.com/pic.jpg"]
)

# 多文件混合（图片+视频）
result = model.model_chat(
    user_prompt="分析这些内容",
    files=["local_img.png", "local_video.mp4", "https://example.com/video.webm"]
)

# 便捷方法
desc = model.describe_image("photo.jpg")
summary = model.analyze_video("clip.mp4", task="总结视频主要情节")
```

#### 依赖要求
- 图片压缩需要 `Pillow`
- 视频抽帧需要 `opencv-python`
- URL 下载使用 `requests`，依赖已内置在 `LLModel` 中

### 工具集成 (ToolRegistry.py)

该模块实现了一个智能化的工具注册与检索系统，为Agent提供动态工具管理和语义检索能力。

**核心组件**  
- **EmbeddingEngine**：基于多语言MiniLM-L12的向量化引擎，将工具描述转换为嵌入向量。  
- **SmartToolRegistry**：基础注册器，支持工具注册、Pydantic模型自动生成、向量缓存、工具执行与参数校验，并提供软/硬删除及僵尸清理功能。  
- **IntentProcessor** / **AdvancedToolRegistry**：增强版注册器，集成LLM意图拆解（使用function calling），将用户自然语言输入分解为多个检索关键词，再通过向量相似度匹配最相关工具，实现多意图场景下的精准工具选择。

**主要功能**  
- 自动从函数签名和文档字符串生成工具Schema（Pydantic模型）。  
- 工具描述向量化与缓存，基于余弦相似度进行语义检索（支持Top‑K筛选）。  
- 工具生命周期管理：软删除（禁用但保留）、恢复、硬删除（完全移除）和缓存僵尸清理。  
- 智能工具获取：先由LLM拆解用户输入为搜索关键词，再向量检索返回匹配的工具集。  

该模块使得Agent能够根据用户复杂意图自动选择合适工具，并确保工具调用的类型安全与参数正确性。

### 监听集成 (ListenEvent.py)

`ListenEvent.py` 实现了一个**桌面活动监听与上下文感知引擎**，用于实时捕获用户交互行为、分析当前窗口场景，并生成结构化的行为日志，为上层 AI 交互提供高质量输入。

#### 核心功能

- **多模态输入捕获**  
  基于 `pynput` 与 `win32gui` 同时监听鼠标点击、键盘按键、窗口切换，过滤自身进程，确保监控纯净。

- **智能上下文分析 (`AppContextAnalyzer`)**  
  - 通过静态进程名注册表、动态窗口标题正则匹配、URL 解析，将当前应用归类为 `Coding`、`Browser`、`Social`、`Game`、`Music` 等语义标签。  
  - 支持浏览器场景穿透（如从 `Browser` 标签进一步识别出 `AI`、`Video`、`Music` 等子场景）。  
  - 提供可配置的模板导出（`static_registry.json`、`dynamic_rules.yaml`、`url_rules.yaml`），便于人工维护。

- **关联学习与持久化 (`ContextAssociator`)**  
  - 自动记忆用户对未知进程的点击行为，推断其所属标签并持久化到 `learned_registry.json`，使分析器逐步适应个体使用习惯。

- **窗口栈管理 (`WindowStateManager`)**  
  - 维护窗口的压栈/出栈关系，准确区分“新开窗口”、“返回旧窗口”、“窗口关闭/最小化”，避免因窗口切换导致日志混乱。

- **事件聚合与防抖**  
  - **键盘输入聚合**：将连续输入的字符合并为一条“输入文本”事件，减少冗余日志。  
  - **双击检测**：利用时间阈值与目标匹配，将连续两次左键单击识别为双击，并修正意图。  
  - **按键防抖**：避免同一按键因重复触发而反复记录（如长按）。

- **场景化统计**  
  - **游戏计时**：自动识别游戏窗口，累计每日/总游玩时长，按“天（凌晨4点刷新）”切分统计。  
  - **音乐播放统计**：通过 `pycaw` 检测进程真实音频输出，记录歌曲播放次数与时长，生成热榜。

- **视觉注意力联动 (`VisualAttentionManager`)**  
  - 根据当前场景策略（如 `text_only` / `visual_only` / `hybrid`）决定是否触发截图。  
  - 支持对活动窗口或全屏进行截图，并可调节分辨率与压缩质量，适配不同场景的视觉需求。

- **结构化输出**  
  - 生成两种形式的数据：  
    - **控制台彩色日志**：方便人工调试。  
    - **AI 友好记忆**：将事件转换为自然语言描述（如“用户 在 Chrome 中 点击了 搜索框”），连同截图路径一并返回，供上层模块（如大模型）消费。

### 视觉注意集成 (VisualAttention.py)

`VisualAttentionManager` 类实现了基于熵池的视觉注意力管理，用于根据用户行为动态触发屏幕截图。它通过监听事件（焦点切换、键盘输入、界面交互）累积不同场景（tag）的“熵值”，当熵值超过预设阈值时触发截图指令，同时支持时间衰减、自动加分（tick）和配置热重载。

#### 主要特性
- **熵池机制**：为每个场景（如 `Coding`、`Social`）维护独立的累积分数池。
- **事件驱动**：处理 `FOCUS_SWITCH`、`KEYBOARD`、`INTERACTION` 事件，根据 YAML 配置中的动作分值更新熵池。
- **时间演化**：按时间间隔执行熵值自然衰减（decay），并为当前前台场景自动增加 tick 分值。
- **阈值触发**：熵值达到场景阈值后返回截图指令，并清空对应池子。
- **配置热重载**：`reload_config()` 方法可在运行时重新加载 YAML 配置文件，立即生效。
- **线程安全**：使用 `threading.RLock` 保护配置读写，支持多线程环境。

#### 关键方法
| 方法 | 说明 |
|------|------|
| `__init__(config_path)` | 初始化管理器，加载配置，创建熵池字典和锁。 |
| `reload_config()` | 从 YAML 文件重新加载策略，更新 `text_policies` 和 `config`。 |
| `_apply_time_evolution(current_time)` | 内部方法：应用衰减和 tick 加分，基于时间差更新熵池。 |
| `process_event(event)` | 核心接口：接收事件字典，返回 `None` 或包含截图参数的字典。 |

#### 配置格式（YAML）
```yaml
policies:
  Coding:
    enabled: true
    decay_rate: 1.5          # 每秒衰减量
    threshold: 100.0
    capture_scope: window
    snapshot_quality: high
    capture_mode: hybrid
    actions:
      tick: 2.0              # 每秒自动加分（仅当前场景）
      switch_in: 10.0
      keypress: 0.5
      enter: 5.0
      paste: 8.0
      special_key: 1.0
      click: 3.0
      click_send: 6.0
  Other:
    enabled: true
    threshold: 200.0
    actions: {}
```

#### 事件结构示例
- **FOCUS_SWITCH**：`{"type": "FOCUS_SWITCH", "context_tag": "Coding", "switch_type": "SWITCH_NEW"}`
- **KEYBOARD**：`{"type": "KEYBOARD", "context_tag": "Coding", "target": "enter"}`
- **INTERACTION**：`{"type": "INTERACTION", "context_tag": "Coding", "target": "发送按钮"}`

#### 触发返回
当熵值 ≥ 阈值时，返回：
```python
{
    "should_capture": True,
    "reason": "threshold_met_Coding",
    "tag": "Coding",
    "capture_scope": "window",   # 截图范围（窗口/全屏等）
    "quality": "high",           # 图像质量
    "include_logs": 10,          # 附带日志条数
    "capture_mode": "hybrid"     # 截图模式
}
```

## 许可证

本项目遵循 MIT 许可证。
---
