# Context-Aware Intelligent Desktop Agent System

## Project Overview

The context-aware intelligent desktop Agent system is an intelligent dialogue system that combines a desktop pet with web applications. It supports Ollama local inference and OpenAI-compatible APIs, providing complete conversation management, memory system, and multimodal interaction capabilities.
### Core Features

- 🖥️ **Dual-End Application**: PyQt6 desktop pet application and Flask web application
- 🧠 **Intelligent Memory System**: Multi-level memory management, long-term storage, vector retrieval
- 🤖 **Flexible Model Support**: Ollama local inference and OpenAI API-compatible interfaces
- 📸 **Multimodal Capabilities**: Text and image input with analysis
- 🛠️ **Tool Integration**: Search, file operations, image processing functions
- 👤 **User System**: Session isolation, personalized settings, authentication
- 💾 **Session Management**: Web chat, desktop pet chat, persistent long-term memory

---

## System Requirements

### Environment Configuration
- **Python**: 3.10.19
- **Operating System**: Windows (primary support)
- **GPU (Optional)**: CUDA 11.8+ (for local LLM acceleration, author uses 12.4)

### Python Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| torch | 2.4.1 | Deep learning framework |
| torchaudio | 2.4.1 | Audio processing |
| torchvision | 0.19.1 | Computer vision tools |
| transformers | 4.57.3 | Pre-trained models |
| numpy | 1.26.4 | Numerical computing |
| modelscope | 1.34.0 | Model repository support |
| Flask | 3.1.2 | Web framework |
| PyQt6 | 6.10.2 | Desktop GUI framework |
| faiss | 1.9.0 | Vector retrieval |
| pywin32 | 311 | Windows system integration |

### Additional Environment Requirements

The following packages are imported in the project code but not explicitly listed in requirements.txt. It's recommended to install them:

```
requests>=2.31.0          # HTTP request library
openai>=1.30.0            # OpenAI API client
pillow>=10.1.0            # Image processing
opencv-python>=4.8.0      # Image processing and analysis
python-dotenv>=1.0.0      # Environment variable management
pydantic>=2.5.0           # Data validation
flask-login>=0.6.3        # Flask user authentication
sqlalchemy>=2.0.0         # Database ORM
PyYAML>=6.0.0             # YAML configuration file parsing
```

---

## Installation & Launch

### 1. Environment Setup

```bash
# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install additional dependencies
pip install requests openai pillow opencv-python python-dotenv pydantic flask-login sqlalchemy PyYAML
```

### 2. Configuration

Create or edit `.env` file by renaming `.env.example` (remove the `.example` suffix).

### 3. Launch Application

#### Desktop Pet Mode

```bash
python DesktopCharacter.py
```

Features:
- Always-on-top floating window desktop pet
- Real-time text dialogue
- Expression pack feedback
- System clipboard monitoring
- Isolated from web sessions

#### Web Mode

```bash
python app.py
```

Access: `http://localhost:8505`

Features:
- Web chat interface
- Multi-session management
- User registration and authentication
- Dynamic model parameter switching
- Real-time streaming responses

---

## Project Structure

```
AIChat/
├── app.py                      # Web application entry point (Flask)
├── DesktopCharacter.py         # Desktop pet entry point (PyQt6)
│
├── Core Modules
├── ├── CharacterChat.py        # Desktop pet chat core (PetChatCore)
├── ├── AIService.py            # Chat processor (ChatProcessor)
├── ├── LLModel.py              # Language model wrapper (multimodal support)
├── ├── SessionContext.py       # Session & memory management
├── ├── ToolRegistry.py         # Tool registration & invocation
├── ├── AIConfig.py             # Global configuration (includes prompts)
├── ├── db.py                   # Database operations (optional usage)
├── ├── ListenEvent.py          # System event listening
├── ├── VisualAttention.py      # Visual processing module
│
├── Configuration Files
├── ├── prompt_config.json      # AI role prompt configuration (simple config, can use custom prompts or add in AIConfig)
├── ├── requirements.txt        # Python dependencies list
├── ├── .env                    # Environment variables (create manually, see .env.example)
│
├── Resource Directories
├── ├── CharacterImage/         # Desktop pet character images and profiles
├── ├── templates/              # Flask HTML templates
├── ├── static/                 # Static resources (CSS/JS)
├── ├── stickers/               # Expression pack resources
├── ├── Tool/                   # Tool collection
├── ├── context_templates/      # Behavior rule configurations
├── ├── KnowledgeBase/          # Knowledge base
│
├── Data Storage
├── ├── Memory/storage/         # Session memory storage
└── └── users.json              # User data (account data stored here if db.py is not used)
```

---

## Initial Setup

First, launch `app.py` to register an account, then you can use both the web and desktop applications.

For the desktop application, configure your username and password in `prompt_config.json` to use it. To use a custom character image, simply change the `IMAGE_PATH` in `DesktopCharacter.py` to your image path.

---

## Configuration & Customization

### AI Role Configuration

Edit `prompt_config.json`:

```json
{
  "user_name": "root",
  "password": "11111111",
  "selected_prompt_name": "Gentle Sister",
  "user_role": "Brother",
  "prompts": {
    "Gentle Sister": "You are a gentle and caring sister...",
    "Playful Assistant": "You are a playful and cute AI assistant..."
  }
}
```

---

## Core Features Explanation

### Session Management (SessionContext.py)

This module implements a hierarchical memory management system based on dialogue history, supporting session creation, persistence, compression archiving, and long-term memory merging, while ensuring session isolation across different scenarios (`chat_type`).

#### Core Classes

- **`MemoryBlock`**  
  Universal memory block with two levels:
  - **Level 1**: Contains compressed summary (JSON) and original messages for recent active compression.
  - **Level 2**: Contains only summary and references to long-term storage, used for archived global memory without original messages to save memory.

- **`SessionContext`**  
  Single session context manager responsible for:
  - Message addition and active buffer management.
  - Automatic compression triggering (token threshold, memory block count threshold).
  - Further merging of compressed Level-1 blocks into Level-2 global archives.
  - Providing context for AI usage (compressed summaries + active messages).
  - Persistence and soft/hard deletion of session metadata.

- **`LongTermMemoryManager`**  
  User long-term memory manager, merging multiple Level-1 blocks (or old Level-2 blocks) through LLM into a structured global profile (`long_term_memory` + `short_term_context`), persisting as JSON file, replacing heavy vector retrieval.

- **`MemoryManager`**  
  Global session manager managing all `SessionContext` instances, supporting:
  - Unique identification by `user_id`, `chat_type`, `session_id`.
  - Automatic reuse of empty sessions (no messages).
  - Session creation, retrieval, listing, renaming, and deletion.
  - Unified message addition and history retrieval interfaces.

#### Main Functions

1. **Hierarchical Memory Compression**  
   - Active buffer messages or tokens reach threshold, LLM generates Level-1 summary, original messages archived.
   - When Level-1 block count exceeds `SHORT_TERM_MEMORY_LIMIT`, multiple Level-1 blocks (and possible old Level-2 blocks) merge into new Level-2 global archive, retaining only summaries and references.

2. **Multi-Scenario Isolation**  
   - Each session carries `chat_type` parameter (e.g., `web_chat`, `pet_chat`), storage paths and memory keys include this parameter, ensuring different dialogue types don't interfere.

3. **Persistence & Lifecycle**  
   - Session data stored as JSON in `./Memory/storage/<user_id>/<chat_type>/<session_id>/` directory, containing metadata, active buffer, and compressed memory blocks.
   - Supports soft deletion (mark only) and hard deletion (physical file removal).

4. **Context Construction**  
   - `get_full_context_for_ai()` returns in order:
     - Level-2 global archive (structured JSON text).
     - Level-1 recent summaries.
     - Original messages in current active buffer.
   - Ensures AI receives coherent, refined context without losing key information.

5. **Flexible Message Addition**  
   - `add_message()` supports specifying message type (text, file, etc.) and whether to allow immediate compression triggering, useful for special scenarios (e.g., system messages) with delayed compression.

#### Design Points

- **Compression Strategy**: Prioritize cutting after `assistant` messages to avoid interrupting Q&A; if no suitable cut point, retain last 1-2 messages.
- **Two-Level Merging**: Merge multiple Level-1 blocks into single Level-2 global archive, significantly reducing long-term memory block count while retaining key state and continuity information.
- **Storage Structure**: User-level long-term memory stored independently in `long_term_memory/global_profile.json`, can be removed together when account is deleted.

### Multimodal Processing (LLModel.py)

The `LLModel` class has built-in unified multimodal input processing capabilities, supporting **image** and **video** files, with automatic compression, frame extraction, URL downloading, and temporary file cleanup mechanisms.

#### Supported File Types
- **Images**: `.jpg` / `.jpeg` / `.png` / `.gif` / `.bmp` / `.webp`
- **Videos**: `.mp4` / `.avi` / `.mov` / `.mkv` / `.webm` (requires OpenCV)

#### Core Features
| Feature | Description |
|---------|-------------|
| **Local File/URL Input** | Auto-detects `http://`/`https://` links and downloads to temp directory, supports retry and streaming download |
| **Automatic Image Compression** | Can enable `auto_compress_image`, limit max image size to `max_image_size` (default 1024), optimize format (JPEG quality 85), reduce transmission overhead |
| **Automatic Video Frame Extraction** | Can enable `auto_extract_video_frames`, uniformly extract up to `max_video_frames` (default 3) frames as image sequence for model, auto skip opening/ending (first 5% and last 5%) |
| **Temporary File Management** | Downloaded files auto-stored in `temp/download/` under project directory, supports auto cleanup (configurable `cleanup_downloaded_files`), periodically cleans files older than 24 hours |
| **Call-Level Override** | In `model_chat` can override instance's global settings via `auto_compress_image` / `auto_extract_video_frames` parameters |

#### Usage Example
```python
# Initialize
model = LLModel(
    chat_model="qwen2.5-vl",
    use_ollama=True,
    auto_compress_image=True,      # Global enable compression
    max_image_size=1024,
    auto_extract_video_frames=True, # Global enable video frame extraction
    max_video_frames=3
)

# Single image (local or URL)
result = model.model_chat(
    user_prompt="Describe this image",
    files=["https://example.com/pic.jpg"]
)

# Mixed multiple files (image + video)
result = model.model_chat(
    user_prompt="Analyze these contents",
    files=["local_img.png", "local_video.mp4", "https://example.com/video.webm"]
)

# Convenience methods
desc = model.describe_image("photo.jpg")
summary = model.analyze_video("clip.mp4", task="Summarize main plot of video")
```

#### Dependency Requirements
- Image compression requires `Pillow`
- Video frame extraction requires `opencv-python`
- URL download uses `requests`, dependency already built-in in `LLModel`

### Tool Integration (ToolRegistry.py)

This module implements an intelligent tool registration and retrieval system, providing dynamic tool management and semantic retrieval capabilities for agents.

**Core Components**  
- **EmbeddingEngine**: Vector engine based on multilingual MiniLM-L12, converts tool descriptions into embedding vectors.
- **SmartToolRegistry**: Base registry supporting tool registration, automatic Pydantic model generation, vector caching, tool execution and parameter validation, providing soft/hard deletion and zombie cleanup.
- **IntentProcessor** / **AdvancedToolRegistry**: Enhanced registry integrating LLM intent decomposition (using function calling), decomposing user natural language input into multiple retrieval keywords, then matching most relevant tools via vector similarity, achieving precise tool selection in multi-intent scenarios.

**Main Functions**  
- Automatically generate tool schema (Pydantic models) from function signatures and docstrings.
- Tool description vectorization and caching, semantic retrieval based on cosine similarity (supports Top-K filtering).
- Tool lifecycle management: soft deletion (disable but retain), recovery, hard deletion (completely remove), and cache zombie cleanup.
- Smart tool retrieval: LLM decomposes user input into search keywords first, then vector retrieval returns matching tool set.

This module enables agents to automatically select appropriate tools based on complex user intent, ensuring type safety and parameter correctness in tool invocation.

### Event Listening Integration (ListenEvent.py)

`ListenEvent.py` implements a **desktop activity monitoring and context-aware engine** that captures user interaction behavior in real-time, analyzes current window scenarios, and generates structured behavior logs, providing high-quality input for upper-level AI interactions.

#### Core Functions

- **Multimodal Input Capture**  
  Based on `pynput` and `win32gui` simultaneously monitor mouse clicks, keyboard keys, window switches, filter own process, ensuring pure monitoring.

- **Intelligent Context Analysis (`AppContextAnalyzer`)**  
  - Through static process name registry, dynamic window title regex matching, URL parsing, categorize current application into `Coding`, `Browser`, `Social`, `Game`, `Music` semantic tags.
  - Support browser scenario penetration (e.g., further identify `AI`, `Video`, `Music` sub-scenarios from `Browser` tag).
  - Provide configurable template export (`static_registry.json`, `dynamic_rules.yaml`, `url_rules.yaml`) for manual maintenance.

- **Association Learning & Persistence (`ContextAssociator`)**  
  - Automatically remember user click behavior on unknown processes, infer their tags and persist to `learned_registry.json`, making analyzer gradually adapt to individual usage habits.

- **Window Stack Management (`WindowStateManager`)**  
  - Maintain window push/pop relationships, accurately distinguish "new window open", "return to old window", "window close/minimize", avoiding log confusion from window switching.

- **Event Aggregation & Debouncing**  
  - **Keyboard Input Aggregation**: Merge continuous character input into single "input text" event, reducing redundant logs.
  - **Double-Click Detection**: Use time threshold and target matching to identify two consecutive left clicks as double-click, correcting intent.
  - **Key Debouncing**: Avoid same key repeated recording from repeated triggering (e.g., long press).

- **Scenario Statistics**  
  - **Game Timing**: Automatically identify game windows, accumulate daily/total playtime, segment statistics by "day (refresh at 4am)".
  - **Music Play Statistics**: Detect real audio output through `pycaw`, record song play count and duration, generate hot charts.

- **Visual Attention Linkage (`VisualAttentionManager`)**  
  - Based on current scenario policies (e.g., `text_only` / `visual_only` / `hybrid`) decide whether to trigger screenshot.
  - Support screenshot of active window or full screen, adjustable resolution and compression quality, adapting to different scenario visual needs.

- **Structured Output**  
  - Generate two forms of data:
    - **Console colored logs**: Convenient for human debugging.
    - **AI-friendly memory**: Convert events to natural language descriptions (e.g., "user clicked search box in Chrome"), return with screenshot paths, for upper-level modules (e.g., large models) to consume.

### Visual Attention Integration (VisualAttention.py)

The `VisualAttentionManager` class implements entropy-pool-based visual attention management to dynamically trigger screen screenshots based on user behavior. It monitors events (focus switch, keyboard input, interface interaction) and accumulates "entropy values" for different scenarios (tags). When entropy exceeds preset threshold, it triggers screenshot command, supporting time decay, auto-increment (tick), and config hot-reload.

#### Main Features
- **Entropy Pool Mechanism**: Maintain independent cumulative score pool for each scenario (e.g., `Coding`, `Social`).
- **Event-Driven**: Handle `FOCUS_SWITCH`, `KEYBOARD`, `INTERACTION` events, update entropy pool based on action scores in YAML config.
- **Time Evolution**: Execute natural entropy decay (decay) at time intervals, auto-increment tick score for current foreground scenario.
- **Threshold Triggering**: Return screenshot instruction when entropy reaches scenario threshold, clear corresponding pool.
- **Config Hot-Reload**: `reload_config()` method reloads YAML config at runtime, takes effect immediately.
- **Thread-Safe**: Use `threading.RLock` to protect config read/write, support multi-threaded environment.

#### Key Methods
| Method | Description |
|--------|-------------|
| `__init__(config_path)` | Initialize manager, load config, create entropy pool dict and lock. |
| `reload_config()` | Reload policies from YAML file, update `text_policies` and `config`. |
| `_apply_time_evolution(current_time)` | Internal method: Apply decay and tick increment, update entropy pool based on time difference. |
| `process_event(event)` | Core interface: Receive event dict, return `None` or dict containing screenshot parameters. |

#### Configuration Format (YAML)
```yaml
policies:
  Coding:
    enabled: true
    decay_rate: 1.5          # Decay per second
    threshold: 100.0
    capture_scope: window
    snapshot_quality: high
    capture_mode: hybrid
    actions:
      tick: 2.0              # Auto-increment per second (only current scenario)
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

#### Event Structure Example
- **FOCUS_SWITCH**: `{"type": "FOCUS_SWITCH", "context_tag": "Coding", "switch_type": "SWITCH_NEW"}`
- **KEYBOARD**: `{"type": "KEYBOARD", "context_tag": "Coding", "target": "enter"}`
- **INTERACTION**: `{"type": "INTERACTION", "context_tag": "Coding", "target": "send button"}`

#### Trigger Return
When entropy ≥ threshold, return:
```python
{
    "should_capture": True,
    "reason": "threshold_met_Coding",
    "tag": "Coding",
    "capture_scope": "window",   # Screenshot scope (window/fullscreen, etc.)
    "quality": "high",           # Image quality
    "include_logs": 10,          # Include log count
    "capture_mode": "hybrid"     # Screenshot mode
}
```

---

## License

This project is licensed under the MIT License.

---

