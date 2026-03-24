import time
import queue
import traceback
from collections import deque  # 引入双端队列用于实现有限缓存
from pynput import keyboard
import re
import yaml
import psutil
import win32gui
import win32process
import uiautomation as auto
from pynput import mouse
import ctypes
import json
import os
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import win32com.client
from urllib.parse import unquote
from VisualAttention import VisualAttentionManager
import matplotlib.pyplot as plt
from PIL import Image, ImageGrab
import datetime
try:
    from pycaw.pycaw import AudioUtilities
    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False
    print("⚠️ 未安装 pycaw，音乐播放状态检测可能不准确。建议运行: pip install pycaw")

# --- 配置 ---
auto.SetGlobalSearchTimeout(1.0)


# ==========================================
# 新增模块：上下文语义分析器
# ==========================================
class AppContextAnalyzer:
    DEFAULT_STATIC_REGISTRY = {
        # === 浏览器 ===
        "chrome.exe": {"tag": "Browser", "desc": "Chrome 浏览器"},
        "msedge.exe": {"tag": "Browser", "desc": "Edge 浏览器"},
        "firefox.exe": {"tag": "Browser", "desc": "Firefox 浏览器"},
        "opera.exe": {"tag": "Browser", "desc": "Opera 浏览器"},
        "brave.exe": {"tag": "Browser", "desc": "Brave 浏览器"},
        "safari.exe": {"tag": "Browser", "desc": "Safari 浏览器"},

        # === 开发工具 ===
        "code.exe": {"tag": "Coding", "desc": "VS Code 代码编辑"},
        "pycharm64.exe": {"tag": "Coding", "desc": "PyCharm Python IDE"},
        "idea64.exe": {"tag": "Coding", "desc": "IntelliJ IDEA Java IDE"},
        "webstorm64.exe": {"tag": "Coding", "desc": "WebStorm 前端开发"},
        "clion64.exe": {"tag": "Coding", "desc": "CLion C/C++ IDE"},
        "datagrip64.exe": {"tag": "Coding", "desc": "DataGrip 数据库工具"},
        "phpstorm64.exe": {"tag": "Coding", "desc": "PhpStorm PHP IDE"},
        "rubymine64.exe": {"tag": "Coding", "desc": "RubyMine Ruby IDE"},
        "goland64.exe": {"tag": "Coding", "desc": "GoLand Go IDE"},
        "rider64.exe": {"tag": "Coding", "desc": "Rider .NET IDE"},
        "androidstudio.exe": {"tag": "Coding", "desc": "Android Studio"},
        "eclipse.exe": {"tag": "Coding", "desc": "Eclipse IDE"},
        "notepad++.exe": {"tag": "Coding", "desc": "Notepad++ 文本编辑"},
        "sublime_text.exe": {"tag": "Coding", "desc": "Sublime Text 编辑器"},
        "atom.exe": {"tag": "Coding", "desc": "Atom 编辑器"},
        "vim.exe": {"tag": "Coding", "desc": "Vim 终端编辑器"},
        "nvim.exe": {"tag": "Coding", "desc": "Neovim 编辑器"},

        # === 办公软件 ===
        "excel.exe": {"tag": "Office", "desc": "Excel 电子表格"},
        "winword.exe": {"tag": "Office", "desc": "Word 文档编辑"},
        "powerpnt.exe": {"tag": "Office", "desc": "PowerPoint 演示文稿"},
        "outlook.exe": {"tag": "Office", "desc": "Outlook 邮件客户端"},
        "onenote.exe": {"tag": "Office", "desc": "OneNote 笔记"},
        "mspub.exe": {"tag": "Office", "desc": "Publisher 出版工具"},
        "visio.exe": {"tag": "Office", "desc": "Visio 流程图"},
        "wps.exe": {"tag": "Office", "desc": "WPS Office 套件"},
        "et.exe": {"tag": "Office", "desc": "WPS 表格"},
        "wpspdf.exe": {"tag": "Office", "desc": "WPS PDF 阅读"},

        # === 社交通讯 ===
        "wechat.exe": {"tag": "Social", "desc": "微信"},
        "qq.exe": {"tag": "Social", "desc": "QQ 即时通讯"},
        "tim.exe": {"tag": "Social", "desc": "TIM 办公版QQ"},
        "telegram.exe": {"tag": "Social", "desc": "Telegram"},
        "slack.exe": {"tag": "Social", "desc": "Slack 团队协作"},
        "discord.exe": {"tag": "Social", "desc": "Discord 社区聊天"},
        "skype.exe": {"tag": "Social", "desc": "Skype 视频通话"},
        "dingtalk.exe": {"tag": "Work", "desc": "钉钉办公"},
        "feishu.exe": {"tag": "Work", "desc": "飞书协作"},
        "lark.exe": {"tag": "Work", "desc": "飞书国际版"},

        # === 设计创作 ===
        "photoshop.exe": {"tag": "Design", "desc": "Photoshop 图像处理"},
        "illustrator.exe": {"tag": "Design", "desc": "Illustrator 矢量设计"},
        "indesign.exe": {"tag": "Design", "desc": "InDesign 排版"},
        "afterfx.exe": {"tag": "Design", "desc": "After Effects 视频特效"},
        "premiere.exe": {"tag": "Design", "desc": "Premiere 视频剪辑"},
        "figma.exe": {"tag": "Design", "desc": "Figma UI设计"},
        "xd.exe": {"tag": "Design", "desc": "Adobe XD 交互设计"},
        "blender.exe": {"tag": "Design", "desc": "Blender 3D 建模"},
        "cinema4d.exe": {"tag": "Design", "desc": "Cinema 4D 3D 动画"},
        "xmind.exe": {"tag": "Design", "desc": "XMind 思维导图"},
        "mindmanager.exe": {"tag": "Design", "desc": "MindManager 思维导图"},

        # === 媒体娱乐 ===
        "vlc.exe": {"tag": "Media", "desc": "VLC 媒体播放器"},
        "potplayer.exe": {"tag": "Media", "desc": "PotPlayer 播放器"},
        "spotify.exe": {"tag": "Media", "desc": "Spotify 音乐"},
        "netease.exe": {"tag": "Media", "desc": "网易云音乐"},
        "qqmusic.exe": {"tag": "Media", "desc": "QQ音乐"},
        "kugou.exe": {"tag": "Media", "desc": "酷狗音乐"},
        "bilibili.exe": {"tag": "Media", "desc": "哔哩哔哩"},
        "tencentvideo.exe": {"tag": "Media", "desc": "腾讯视频"},
        "iqiyi.exe": {"tag": "Media", "desc": "爱奇艺"},

        # === 系统工具 ===
        "cmd.exe": {"tag": "System", "desc": "命令提示符"},
        "powershell.exe": {"tag": "System", "desc": "PowerShell"},
        "explorer.exe": {"tag": "System", "desc": "文件资源管理器"},
        "taskmgr.exe": {"tag": "System", "desc": "任务管理器"},
        "regedit.exe": {"tag": "System", "desc": "注册表编辑器"},
        "mspaint.exe": {"tag": "System", "desc": "画图工具"},
        "snippingtool.exe": {"tag": "System", "desc": "截图工具"},
        "jietu.exe": {"tag": "System", "desc": "Snipaste 截图"},
        "teamviewer.exe": {"tag": "Remote", "desc": "TeamViewer 远程控制"},
        "anydesk.exe": {"tag": "Remote", "desc": "AnyDesk 远程桌面"},
        "todesk.exe": {"tag": "Remote", "desc": "ToDesk 远程控制"},

        # === 文档阅读 ===
        "acrord32.exe": {"tag": "Document", "desc": "Adobe Reader PDF"},
        "foxitreader.exe": {"tag": "Document", "desc": "Foxit PDF 阅读器"},
        "sumatra.exe": {"tag": "Document", "desc": "Sumatra PDF 轻量阅读"},
        "wpspdf.exe": {"tag": "Document", "desc": "WPS PDF 阅读"},

        # === 虚拟化/开发环境 ===
        "vmware.exe": {"tag": "DevEnv", "desc": "VMware 虚拟机"},
        "virtualbox.exe": {"tag": "DevEnv", "desc": "VirtualBox 虚拟机"},
        "docker.exe": {"tag": "DevEnv", "desc": "Docker 桌面版"},
        "wsl.exe": {"tag": "DevEnv", "desc": "WSL 终端"},
    }
    DEFAULT_DYNAMIC_RULES = [
        # === AI 场景 (优先级高，覆盖各类大模型) ===
        {
            "pattern": r"(?i)chatgpt|openai|deepseek|claude|gemini|copilot|qwen|tongyi|qianwen|通义|文心|kimi|doubao|豆包|metaso|perplexity|coze|poe|mistral|llama",
            "tag": "AI", "desc": "AI 对话助手"},
        # === 视频流媒体 (Video) ===
        {
            "pattern": r"(?i)youtube|bilibili|twitch|netflix|iqiyi|youku|tencent video|爱奇艺|优酷|腾讯视频|芒果tv|hulu|disney\+",
            "tag": "Video", "desc": "观看在线视频"},
        # === 社交/社区 (Social) ===
        {
            "pattern": r"(?i)wechat|wx|qq|weibo|twitter|x\.com|facebook|instagram|reddit|zhihu|douban|linkedin|slack|discord|whatsapp|telegram|微博|知乎|贴吧",
            "tag": "Social", "desc": "浏览社交媒体"},
        # === 在线开发 (Coding/DevEnv) ===
        {
            "pattern": r"(?i)github|gitlab|bitbucket|stackoverflow|colab|jupyter|codespaces|replit|huggingface|pypi|npm|maven|k8s|kubernetes|aws|azure|aliyun|console|terminal",
            "tag": "Coding", "desc": "查阅技术/云服务"},
        # === 音乐/音频 (Music) ===
        {"pattern": r"(?i)spotify|music|soundcloud|netease|qqmusic|kugou|kuwo|网易云|喜马拉雅|fm",
         "tag": "Music", "desc": "在线音频"},
        # === 在线办公/文档 (Office/Work) ===
        {
            "pattern": r"(?i)docs\.google|sheets|slides|notion|feishu|lark|dingtalk|wolai|语雀|confluence|jira|trello|office365|outlook|mail|邮箱",
            "tag": "Office", "desc": "在线文档/办公"},
        # === 设计 (Design) ===
        {"pattern": r"(?i)figma|canva|dribbble|behance|pixiv|artstation|sketch|mastergo|即时设计",
         "tag": "Design", "desc": "在线设计/素材"},
        # === 翻译/工具 (Tool -> System/Other) ===
        {"pattern": r"(?i)translate|deepl|fanyi|maps|ditu|百度翻译|谷歌翻译|地图",
         "tag": "System", "desc": "在线工具"},
        # === 默认学习 (Learning) ===
        {"pattern": r"(?i)tutorial|guide|course|mooc|coursera|udemy|edx|learn|study|教程|文档|wiki|百科",
         "tag": "Learning", "desc": "在线学习"},
    ]
    DEFAULT_URL_RULES = [
        {"pattern": r"(?i)github\.com", "tag": "Coding", "desc": "代码托管"},
        {"pattern": r"(?i)stackoverflow\.com", "tag": "Coding", "desc": "技术问答"},
        {"pattern": r"(?i)colab\.research\.google\.com", "tag": "Coding", "desc": "Colab Notebook"},
        {"pattern": r"(?i)chatgpt\.com|openai\.com", "tag": "AI", "desc": "ChatGPT"},
        {"pattern": r"(?i)claude\.ai", "tag": "AI", "desc": "Claude AI"},
        {"pattern": r"(?i)bilibili\.com|youtube\.com|twitch\.tv", "tag": "Video", "desc": "在线视频"},
        {"pattern": r"(?i)figma\.com|canva\.com", "tag": "Design", "desc": "在线设计"},
        {"pattern": r"(?i)feishu\.cn|larksuite\.com|dingtalk\.com", "tag": "Work", "desc": "协同办公"},
        {"pattern": r"(?i)docs\.google\.com|notion\.so|wolai\.com", "tag": "Office", "desc": "在线文档"},
        {"pattern": r"(?i)wechat\.com|wx\.qq\.com", "tag": "Social", "desc": "微信网页版"},
        {"pattern": r"(?i)mail\.google\.com|outlook\.live\.com", "tag": "Office", "desc": "网页邮箱"},
        {"pattern": r"(?i)maps\.google\.com|map\.baidu\.com", "tag": "System", "desc": "在线地图"},
    ]

    def __init__(
            self,
            static_registry_path: Optional[str] = r"./context_templates/static_registry.json",
            dynamic_rules_path: Optional[str] = r"./context_templates/dynamic_rules.yaml",
            url_rules_path: Optional[str] = r"./context_templates/url_rules.yaml",
            music_records_path="./context_templates/music_records.json",
            behavior_rules_path="./context_templates/behavior_rules.json",
            game_records_path="./context_templates/game_records.json",
            use_default_fallback: bool = True
    ):
        """
        初始化分析器

        :param static_registry_path: 静态注册表JSON/YAML文件路径
        :param dynamic_rules_path: 动态规则JSON/YAML文件路径
        :param use_default_fallback: 当文件加载失败时是否使用内置默认配置
        """
        self.static_registry = self._load_static_registry(static_registry_path, use_default_fallback)
        self.dynamic_rules = self._load_dynamic_rules(dynamic_rules_path, use_default_fallback)
        self.url_rules = self._load_url_rules(url_rules_path, use_default_fallback)
        self.music_records_path = music_records_path
        self.music_records = self._load_music_records()  # 启动时加载历史歌单
        self.behavior_rules_path = behavior_rules_path
        self.behavior_rules = self._load_behavior_rules()
        self.game_records_path = game_records_path
        self.game_records = self._load_game_records()

        # 预编译正则表达式提升性能
        self._compiled_rules = [
            (re.compile(rule["pattern"], re.UNICODE), rule["tag"], rule["desc"])
            for rule in self.dynamic_rules
        ]

        # 预编译 URL 正则
        self._compiled_url_rules = [
            (re.compile(rule["pattern"], re.UNICODE), rule["tag"], rule["desc"])
            for rule in self.url_rules
        ]

        self.export_templates()

    def analyze_url(self, url: str) -> Optional[Dict[str, str]]:
        """如果不为空，返回覆盖用的 Tag 信息"""
        if not url: return None

        # [修改点 5] 使用预编译的配置化规则进行匹配
        for pattern, tag, desc in self._compiled_url_rules:
            if pattern.search(url):
                return {"tag": tag, "desc": f"{desc} (Web)"}
        return None

    def _load_static_registry(self, path: Optional[str], use_default: bool) -> Dict[str, Dict]:
        """从文件加载静态注册表"""
        if path and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    if path.endswith('.yaml') or path.endswith('.yml'):
                        return yaml.safe_load(f)
                    else:
                        return json.load(f)
            except Exception as e:
                print(f"⚠️ 静态注册表加载失败 ({path}): {e}")

        return self.DEFAULT_STATIC_REGISTRY.copy() if use_default else {}

    def _load_dynamic_rules(self, path: Optional[str], use_default: bool) -> List[Dict]:
        """从文件加载动态规则"""
        if path and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    if path.endswith('.yaml') or path.endswith('.yml'):
                        rules = yaml.safe_load(f)
                    else:
                        rules = json.load(f)
                    # 验证规则结构
                    return [
                        r for r in rules
                        if isinstance(r, dict) and all(k in r for k in ['pattern', 'tag', 'desc'])
                    ]
            except Exception as e:
                print(f"⚠️ 动态规则加载失败 ({path}): {e}")

        return self.DEFAULT_DYNAMIC_RULES.copy() if use_default else []

    def _load_url_rules(self, path: Optional[str], use_default: bool) -> List[Dict]:
        """从文件加载 URL 规则"""
        if path and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    if path.endswith('.yaml') or path.endswith('.yml'):
                        rules = yaml.safe_load(f)
                    else:
                        rules = json.load(f)
                    # 验证规则结构
                    return [
                        r for r in rules
                        if isinstance(r, dict) and all(k in r for k in ['pattern', 'tag', 'desc'])
                    ]
            except Exception as e:
                print(f"⚠️ URL 规则加载失败 ({path}): {e}")

        return self.DEFAULT_URL_RULES.copy() if use_default else []

    def _load_music_records(self) -> Dict:
        """加载历史音乐记录"""
        if os.path.exists(self.music_records_path):
            try:
                with open(self.music_records_path, 'r', encoding='utf-8') as f:
                    print("🎧 已加载持久化历史歌单。")
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ 读取历史歌单失败: {e}")
        return {}

    def _save_music_records(self):
        """保存音乐记录到磁盘"""
        os.makedirs(os.path.dirname(self.music_records_path), exist_ok=True)
        try:
            with open(self.music_records_path, 'w', encoding='utf-8') as f:
                json.dump(self.music_records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            pass

    def _load_behavior_rules(self) -> List[Dict]:
        """加载用户自定义的UI行为识别规则"""
        if os.path.exists(self.behavior_rules_path):
            try:
                with open(self.behavior_rules_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass

        # 如果没有文件，生成一个默认的模板文件供你参考
        default_rules = [
            {
                "match": {"Process": "pycharm64.exe", "ControlTypeName": "TabItemControl"},
                "intent_tag": "切换代码文件"
            },
            {
                "match": {"Process": "chrome.exe", "AutomationId": "urlbar-input"},
                "intent_tag": "点击浏览器地址栏"
            }
        ]
        os.makedirs(os.path.dirname(self.behavior_rules_path), exist_ok=True)
        with open(self.behavior_rules_path, 'w', encoding='utf-8') as f:
            json.dump(default_rules, f, ensure_ascii=False, indent=2)
        return default_rules

    def _load_game_records(self) -> Dict:
        """加载历史游戏记录"""
        if os.path.exists(self.game_records_path):
            try:
                with open(self.game_records_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"total": {}, "daily": {}}

    def _save_game_records(self):
        """保存游戏记录到磁盘"""
        os.makedirs(os.path.dirname(self.game_records_path), exist_ok=True)
        try:
            with open(self.game_records_path, 'w', encoding='utf-8') as f:
                json.dump(self.game_records, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def analyze(self, process_name: str, window_title: str = "") -> Dict[str, str]:
        """
        分析应用上下文

        :param process_name: 进程名（如 "chrome.exe"）
        :param window_title: 窗口标题（可选）
        :return: 语义对象 {"tag": "...", "desc": "..."}
        """
        proc_lower = process_name.lower().strip() if process_name else ""

        # 1. 优先匹配静态注册表
        if proc_lower in self.static_registry:
            info = self.static_registry[proc_lower].copy()
            self._apply_dynamic_rules(window_title, info)
            return info

        # 2. 静态表未命中，进行动态推断
        info = {"tag": "Other", "desc": "未知应用"}
        self._apply_dynamic_rules(window_title, info)
        return info

    def _apply_dynamic_rules(self, title: str, info_dict: Dict[str, str]) -> None:
        """应用动态规则增强上下文识别 (支持浏览器场景透视)"""
        if not title or not title.strip():
            return

        title_clean = title.strip()
        current_tag = info_dict.get("tag", "Other")

        # 预先定义允许从浏览器“逃逸”出来的Tag白名单
        # 如果匹配到这些 Tag，我们将把主场景从 Browser 改为具体的 Tag
        BROWSER_OVERRIDE_TAGS = {
            "AI", "Video", "Music", "Coding", "Social",
            "Office", "Design", "Game", "Live", "DevEnv"
        }

        for pattern, match_tag, match_desc in self._compiled_rules:
            if pattern.search(title_clean):

                # === 逻辑 1: 浏览器场景透视 (核心修改) ===
                if current_tag == "Browser":
                    if match_tag in BROWSER_OVERRIDE_TAGS:
                        # 强行篡改主 Tag
                        info_dict["tag"] = match_tag
                        # 更新描述，保留来源信息
                        # 例如: "AI 对话助手 (Edge)"
                        browser_name = info_dict.get("desc", "浏览器").split(' ')[0]  # 提取 "Edge" 或 "Chrome"
                        info_dict["desc"] = f"{match_desc} ({browser_name})"
                    else:
                        # 如果是不在白名单里的规则（比如只是普通网页），仅追加描述
                        if match_desc not in info_dict["desc"]:
                            info_dict["desc"] += f" | {match_desc}"

                # === 逻辑 2: 未知应用归类 ===
                elif current_tag == "Other":
                    info_dict["tag"] = match_tag
                    info_dict["desc"] = match_desc

                # === 逻辑 3: 跨域修正 (例如在 VSCode 里看 Markdown 预览) ===
                elif match_tag != current_tag and match_tag not in ["Other", "System"]:
                    # 避免 tag 震荡，这里主要做描述补充
                    if match_desc not in info_dict["desc"]:
                        info_dict["desc"] += f" | {match_desc}"

                # 匹配命中即停止，防止规则冲突
                break

    def export_templates(self, output_dir: str = "./context_templates") -> None:
        """
        导出配置模板到文件（便于人工维护）
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        import yaml

        # 1. 导出静态注册表 (JSON)
        static_path = os.path.join(output_dir, "static_registry.json")
        with open(static_path, 'w', encoding='utf-8') as f:
            json.dump(self.static_registry, f, ensure_ascii=False, indent=2)

        # 2. 导出动态规则 (YAML)
        dynamic_path = os.path.join(output_dir, "dynamic_rules.yaml")
        with open(dynamic_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.dynamic_rules, f, allow_unicode=True, sort_keys=False)

        # 3. 导出 URL 规则 (YAML)
        url_path = os.path.join(output_dir, "url_rules.yaml")
        with open(url_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.url_rules, f, allow_unicode=True, sort_keys=False)

        print(f"✓ 配置模板已导出至: {output_dir}")
        print(f"  - 静态注册表: {static_path}")
        print(f"  - 动态规则: {dynamic_path}")
        print(f"  - URL 规则: {url_path}")


# ==========================================
# 关联学习与持久化引擎
# ==========================================
class ContextAssociator:
    def __init__(self, analyzer: AppContextAnalyzer,
                 persistence_path: str = "./context_templates/learned_registry.json"):
        self.analyzer = analyzer
        self.persistence_path = persistence_path
        self.last_strong_interaction = None  # 短期记忆：上一次强交互
        self.interaction_timeout = 2.0  # 关联有效时间窗口（秒）

        # 关键词触发映射表 (可以扩展)
        self.trigger_keywords = {
            "网易云": {"tag": "Media", "desc": "网易云音乐"},
            "QQ音乐": {"tag": "Media", "desc": "QQ音乐"},
            "歌词": {"tag": "Media", "desc": "桌面歌词"},
            "WeChat": {"tag": "Social", "desc": "微信"},
            "钉钉": {"tag": "Work", "desc": "钉钉"},
            "Feishu": {"tag": "Work", "desc": "飞书"},
        }

        # 加载已学习的规则
        self.learned_rules = self._load_learned_rules()
        # 将学习到的规则合并进分析器的注册表
        self.analyzer.static_registry.update(self.learned_rules)

    def _load_learned_rules(self) -> Dict:
        if os.path.exists(self.persistence_path):
            try:
                with open(self.persistence_path, 'r', encoding='utf-8') as f:
                    print(f"🧠 已加载学习记忆: {self.persistence_path}")
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ 读取记忆失败: {e}")
        return {}

    def _persist_rule(self, process_name: str, tag_info: Dict):
        """持久化新规则到磁盘"""
        if not process_name: return

        process_key = process_name.lower()
        # 如果已经存在且一样，就不重复保存
        if process_key in self.learned_rules:
            return

        print(f"💾 [学习新知识] 发现进程 '{process_name}' 属于 [{tag_info['tag']}]，正在固化记忆...")

        self.learned_rules[process_key] = tag_info
        # 同时更新内存中的分析器
        self.analyzer.static_registry[process_key] = tag_info

        # 写入文件
        try:
            with open(self.persistence_path, 'w', encoding='utf-8') as f:
                json.dump(self.learned_rules, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 持久化失败: {e}")

    def register_interaction(self, event: Dict):
        """
        登记一次交互事件 (用于触发判定)
        """
        if event['type'] != 'INTERACTION':
            return

        target_name = event.get('target', '')
        timestamp = time.time()

        # 检查点击的目标名字里是否有我们认识的关键词
        for keyword, context in self.trigger_keywords.items():
            if keyword in target_name:
                self.last_strong_interaction = {
                    "time": timestamp,
                    "keyword": keyword,
                    "context": context
                }
                # print(f"⚡ 触发关联预备: 检测到 '{keyword}' 点击，等待窗口激活...")
                return

    def infer_context(self, event: Dict) -> Dict:
        """
        尝试推断上下文 (处理 Focus 事件)
        """
        # 如果分析器已经识别出来了，就不需要推断了
        if event.get('context_tag') != "Other":
            return event

        # 如果是未知应用，且我们在时间窗口内有强交互
        if self.last_strong_interaction:
            time_delta = time.time() - self.last_strong_interaction['time']

            if time_delta <= self.interaction_timeout:
                # === 触发关联逻辑 ===
                predicted_context = self.last_strong_interaction['context']
                raw_process = event.get('raw_process')

                # 1. 修正当前事件的 Tag
                event['context_tag'] = predicted_context['tag']
                event['context_desc'] = f"{predicted_context['desc']} (自动关联)"

                # 2. 持久化学习：如果这个进程名是未知的，记录下来
                if raw_process and raw_process.lower() not in self.analyzer.static_registry:
                    # 我们保存纯净的描述，去掉"(自动关联)"字样
                    self._persist_rule(raw_process, predicted_context)

                # 消费掉这个触发器（防止连续误判）
                self.last_strong_interaction = None

        return event


# ==========================================
# 窗口栈管理器 (Window Stack Manager)
# ==========================================
class WindowStateManager:
    """
    负责维护窗口的层级关系（栈），解决日志“混乱”的问题。
    """

    def __init__(self):
        # 栈结构：List[Dict] -> [{'hwnd': 123, 'title': 'A', 'process': 'exe', 'time': t}]
        self.stack = []
        self.current_window = None

    def update_focus(self, hwnd, title, process_name, last_intent=None) -> Dict:
        """
        当焦点变化时调用。
        返回事件类型：'SWITCH_NEW' (新窗口), 'SWITCH_BACK' (返回旧窗口), 'TITLE_UPDATE' (标题更新)
        last_intent: 用户最近的操作意图 (例如 {'action': 'Close', 'process': 'xxx', 'time': t})
        """
        timestamp = time.time()
        new_window_data = {
            "hwnd": hwnd,
            "title": title,
            "process": process_name,
            "time": timestamp
        }

        # 1. 初始化
        if not self.current_window:
            self.current_window = new_window_data
            self.stack.append(new_window_data)
            return {"type": "INIT", "depth": 1}

        # 2. 同一窗口检查
        if self.current_window["hwnd"] == hwnd:
            if self.current_window["title"] != title:
                self.current_window["title"] = title
                return {"type": "TITLE_UPDATE", "depth": len(self.stack)}
            return None

            # 3. Explorer 合并
        if process_name.lower() == 'explorer.exe' and self.current_window['process'].lower() == 'explorer.exe':
            self.current_window.update(new_window_data)
            if self.current_window['title'] != title:
                return {"type": "TITLE_UPDATE", "depth": len(self.stack)}
            return None

            # 4. 回溯逻辑 (SWITCH_BACK)
        for index in range(len(self.stack) - 2, -1, -1):
            if self.stack[index]["hwnd"] == hwnd:
                popped_windows = self.stack[index + 1:]
                self.stack = self.stack[:index + 1]
                self.current_window = self.stack[-1]
                self.current_window["title"] = title

                # === [核心修复] 智能状态判断 ===
                processed_popped = []
                for w in popped_windows:
                    status = self._judge_window_status(w, last_intent)

                    processed_popped.append({
                        "process": w['process'],
                        "title": w['title'],
                        "status": status
                    })

                return {
                    "type": "SWITCH_BACK",
                    "depth": len(self.stack),
                    "popped_wins": processed_popped
                }

        # 5. 新窗口压栈
        self.stack.append(new_window_data)
        self.current_window = new_window_data
        return {"type": "SWITCH_NEW", "depth": len(self.stack)}

    def _judge_window_status(self, window_data, last_intent):
        """
        综合判断窗口状态：API检测 + 意图推断
        """
        hwnd = window_data['hwnd']
        proc_name = window_data['process']

        # 1. 优先检查用户意图 (如果在 1.5秒内点击了关闭/最小化)
        if last_intent and (time.time() - last_intent['time'] < 1.5):
            # 意图必须匹配当前的进程或窗口
            if last_intent['process'] == proc_name:
                if last_intent['action'] == "Close":
                    return "关闭(操作)"
                elif last_intent['action'] == "Minimize":
                    return "最小化(操作)"

        # 2. API 检测：窗口句柄是否还在？
        if not win32gui.IsWindow(hwnd):
            return "关闭"

        # 3. API 检测：是否最小化 (IsIconic)
        # IsIconic 返回非0表示最小化
        if win32gui.IsIconic(hwnd):
            return "最小化"

        # 4. API 检测：是否可见 (兜底)
        if not win32gui.IsWindowVisible(hwnd):
            return "后台(隐藏)"

        return "后台"

    def get_stack_str(self):
        # 生成类似 "Explorer > Notepad > Settings" 的面包屑字符串
        names = []
        max_len = 5  # 只显示最近5层，避免太长
        for w in self.stack[-max_len:]:
            proc = w['process'].replace('.exe', '')
            names.append(proc)
        path = " > ".join(names)
        if len(self.stack) > max_len:
            path = "... > " + path
        return f"[{path}]"


# ==========================================
# 主监控逻辑 (集成版)
# ==========================================
class DesktopMonitor:
    def __init__(self, role="用户"):
        # 记录当前程序自身的 PID，用于拦截自我监控
        self.current_pid = os.getpid()

        # 截图前后的回调函数钩子
        self.before_capture_callback = None
        self.after_capture_callback = None
        self.busy_check_callback = None  # 接收从 UI 传过来的忙碌状态回调

        self.event_queue = queue.Queue()
        self.role = role
        self.is_running = True

        # 1. 初始化分析器
        self.analyzer = AppContextAnalyzer()
        # === 日志有限缓存 (FIFO) ===
        # maxlen=50 表示只保留最近50条操作记录
        # 当超过50条时，最旧的记录会自动被挤出 (First-In-First-Out)
        self.log_history = deque(maxlen=50)

        # === 键盘输入聚合缓冲 ===
        self.typing_buffer = []  # 存放 ['c', 'l', 'a', 's', 's']
        self.last_typing_time = 0  # 上次打字时间
        self.TYPING_FLUSH_TIMEOUT = 1.5  # 停止打字多久后自动合并日志 (秒)

        # 2. 初始化关联学习引擎 (传入分析器以便共享数据)
        self.associator = ContextAssociator(self.analyzer)
        self.window_manager = WindowStateManager()  # 引入栈管理器
        # 记录最近的窗口控制意图
        self.last_window_intent = None  # {action: 'Close', process: 'xxx', time: t}

        # 初始化视觉注意力管理器
        self.visual_attention = VisualAttentionManager()
        self.last_chat = ""

        # === 双击检测相关变量 ===
        self.pending_click = None  # 暂存的第一次点击事件
        self.DOUBLE_CLICK_LIMIT = 0.35  # 双击判定时间阈值 (秒)

        # === 按键状态字典 (用于防抖动) ===
        # 格式: { "key_name": last_log_timestamp }
        self.key_states = {}  # 用于防抖动计时
        self.current_keys = set()  # 用于记录当前按住的所有键 (状态池)
        self.REPEAT_INTERVAL = 1.0

        # 定义修饰键集合，用于快速判断
        self.MODIFIER_KEYS = {
            keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
            keyboard.Key.alt_l, keyboard.Key.alt_r,
            keyboard.Key.shift, keyboard.Key.shift_r,
            keyboard.Key.cmd, keyboard.Key.cmd_r
        }

        # === 按键标准化映射表 ===
        self.KEY_NORMALIZATION = {
            'ctrl_l': 'Ctrl',
            'ctrl_r': 'Ctrl',
            'alt_l': 'Alt',
            'alt_gr': 'Alt',
            'shift': 'Shift',
            'shift_r': 'Shift',
            'cmd': 'Win',
            'cmd_r': 'Win',
            'enter': 'Enter',
            'tab': 'Tab',
            'space': 'Space',
            'backspace': 'Backspace',
            'esc': 'Esc'
        }

        # 初始化 COM Shell 对象 (用于获取 Explorer 路径)
        try:
            self.shell = win32com.client.Dispatch("Shell.Application")
        except:
            self.shell = None
            print("⚠️ 警告: 无法初始化 Shell 组件，路径获取可能受限")

        # 音乐与游戏记录相关的状态变量
        # 音乐字典结构: {"歌曲名": {"count": 1, "duration": 15.0}}
        self.music_records_path = self.analyzer.music_records_path
        self.music_records = self.analyzer.music_records

        # 自动迁移旧版音乐数据到新结构
        if "total" not in self.music_records and "daily" not in self.music_records:
            old_data = self.music_records
            self.music_records = {"total": old_data, "daily": {}}
            self._save_music_records()

        self.last_seen_song = None  # 用于判断是否切歌（防止暂停恢复时增加播放次数）
        self.last_music_scan_time = time.time()
        self.pid_cache = {}

        self.game_records_path = self.analyzer.game_records_path
        self.game_records = self.analyzer.game_records

        # 游戏独立计时字典 { "process.exe | 游戏描述": 累计秒数 }
        self.game_playtimes = {}
        # 当前游戏会话 { "key": "process.exe | 游戏描述", "start_time": 1234567.89 }
        self.current_game_session = None
        # 记录上一次判断“天”的日期，用于凌晨 4:00 清空
        self.last_reset_date = self._get_current_reset_date()

        # 用户行为映射
        self.behavior_rules = self.analyzer.behavior_rules
        self.rules_index = {}  # { "cloudmusic.exe": [rule1, rule2], "default": [...] }

        for rule in self.behavior_rules:
            proc = rule.get("match", {}).get("Process", "default").lower().strip()
            if proc not in self.rules_index:
                self.rules_index[proc] = []
            self.rules_index[proc].append(rule)
        # 添加默认规则池
        if "default" not in self.rules_index:
            self.rules_index["default"] = []

        # === 1. 启动鼠标监听 ===
        self.mouse_listener = mouse.Listener(on_click=self.on_click)
        self.mouse_listener.start()

        # === 2. 启动键盘监听  ===
        # === 同时监听 Press 和 Release ===
        self.keyboard_listener = keyboard.Listener(
            on_press=self.on_key_press,
            on_release=self.on_key_release
        )
        self.keyboard_listener.start()

    def _get_process_name_by_pid(self, pid):
        try:
            return psutil.Process(pid).name()
        except:
            return None

    def _save_game_records(self):
        """保存游戏记录到磁盘"""
        os.makedirs(os.path.dirname(self.game_records_path), exist_ok=True)
        try:
            with open(self.game_records_path, 'w', encoding='utf-8') as f:
                json.dump(self.game_records, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _save_music_records(self):
        """保存音乐记录到磁盘"""
        os.makedirs(os.path.dirname(self.music_records_path), exist_ok=True)
        try:
            with open(self.music_records_path, 'w', encoding='utf-8') as f:
                json.dump(self.music_records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            pass

    # 优化后的坐标匹配逻辑片段
    def _check_coordinate_match(self, curr_x, curr_y, win_w, win_h, rule_locate):
        strategy = rule_locate.get("strategy", "bottom_center").lower()
        mode = rule_locate.get("mode", "anchor").lower()
        base = rule_locate.get("baseline", {})

        if not base: return False

        ref_w, ref_h = base.get("W", 1), base.get("H", 1)
        ref_x, ref_y = base.get("X", 0), base.get("Y", 0)

        # 1. 自适应模式优化：增加对角线校验
        if mode == "adaptive":
            curr_pct_x = curr_x / win_w
            curr_pct_y = curr_y / win_h
            ref_pct_x = ref_x / ref_w
            ref_pct_y = ref_y / ref_h

            tolerance = rule_locate.get("tolerance_pct", 0.05)

            # 优化：允许 X 或 Y 单独容差，或者使用曼哈顿距离
            diff_x = abs(curr_pct_x - ref_pct_x)
            diff_y = abs(curr_pct_y - ref_pct_y)

            # 增加对角线距离校验，防止长条形误判
            dist_pct = (diff_x ** 2 + diff_y ** 2) ** 0.5

            if diff_x <= tolerance and diff_y <= tolerance and dist_pct <= (tolerance * 1.5):
                return True
            return False

        # 2. 锚定模式优化：动态计算目标区域 (ROI)
        else:
            tolerance = rule_locate.get("tolerance", 20)
            # 根据策略计算理论中心点
            target_x, target_y = ref_x, ref_y
            if "top_right" in strategy:
                target_x = win_w - (ref_w - ref_x)
                target_y = ref_y  # 假设 Y 是绝对距离顶部
            elif "bottom_center" in strategy:
                target_x = win_w / 2
                target_y = win_h - (ref_h - ref_y)

            # 优化：不仅判断距离，还判断是否在有效点击范围内
            dist_sq = (curr_x - target_x) ** 2 + (curr_y - target_y) ** 2
            return dist_sq <= (tolerance ** 2)

    def _is_pid_playing_audio(self, pid):
        """
        [核心判断] 检查指定 PID 的进程当前是否有真实的音频输出
        """
        if not HAS_PYCAW:
            return True  # 如果没装库，只能假设它只要活着就在播放 (退化逻辑)

        try:
            # 引入底层接口，用于获取音量表信息
            from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                process = session.Process
                if process and process.pid == pid:
                    # [修复点 1] 正确的接口转换方式
                    meter = session._ctl.QueryInterface(IAudioMeterInformation)

                    # GetPeakValue 返回 0.0 到 1.0 的音量峰值
                    if meter and meter.GetPeakValue() > 0.0001:
                        return True
            return False
        except Exception:
            print(traceback.format_exc())
            return False

    def _scan_background_music(self):
        """扫描后台音乐进程，基于真实音频输出累加时长"""
        current_time = time.time()
        elapsed = current_time - self.last_music_scan_time
        if elapsed < 1.5:  # 将 5.0 改为 1.5 秒，大幅提高检测灵敏度
            return
        self.last_music_scan_time = current_time

        found_playing_song = None
        found_playing_proc = ""  # 用来接住进程名

        def enum_windows_proc(hwnd, lParam):
            nonlocal found_playing_song, found_playing_proc
            if found_playing_song: return

            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if not title: return

                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid not in self.pid_cache:
                    try:
                        self.pid_cache[pid] = psutil.Process(pid).name()
                    except:
                        self.pid_cache[pid] = ""

                proc_name = self.pid_cache[pid]
                if proc_name:
                    context = self.analyzer.analyze(proc_name, title)
                    if context['tag'] == 'Music':
                        song_name = title
                        noise_words = ["网易云音乐", "QQ音乐", "Spotify", "酷狗音乐", " - "]
                        for word in noise_words:
                            song_name = song_name.replace(word, "").strip()

                        if song_name and len(song_name) > 1 and song_name not in ["Music", "音乐", "桌面歌词",
                                                                                  "Desktop Lyrics"]:
                            if self._is_pid_playing_audio(pid):
                                found_playing_song = song_name
                                found_playing_proc = proc_name

        win32gui.EnumWindows(enum_windows_proc, None)

        # === 处理统计逻辑 (支持总计和每日分离) ===
        if found_playing_song:
            needs_save = False
            current_date_str = self._get_current_reset_date().isoformat()

            # 初始化防御
            if "total" not in self.music_records: self.music_records["total"] = {}
            if "daily" not in self.music_records: self.music_records["daily"] = {}
            if current_date_str not in self.music_records["daily"]: self.music_records["daily"][current_date_str] = {}

            total_recs = self.music_records["total"]
            daily_recs = self.music_records["daily"][current_date_str]

            # 首次记录这首歌
            if found_playing_song not in total_recs:
                total_recs[found_playing_song] = {"count": 0, "duration": 0.0}
            if found_playing_song not in daily_recs:
                daily_recs[found_playing_song] = {"count": 0, "duration": 0.0}

            # 判断切歌 (增加次数)
            if found_playing_song != self.last_seen_song:
                total_recs[found_playing_song]["count"] += 1
                daily_recs[found_playing_song]["count"] += 1
                self.last_seen_song = found_playing_song
                print(f"\033[95m🎵 [音乐] 切回歌曲: {found_playing_song} (今日: {daily_recs[found_playing_song]['count']}次, 总计: {total_recs[found_playing_song]['count']}次)\033[0m")
                needs_save = True
                # 发送给 AI 队列
                self.event_queue.put({
                    "type": "SYSTEM_STATE",
                    "action_type": "MUSIC_CHANGE",
                    "intent": "系统检测到切歌",
                    "raw_process": found_playing_proc,
                    "window_title": found_playing_song,
                    "context_tag": "Music",
                    "context_desc": "后台音乐播放",
                    "target": found_playing_song,
                    "timestamp": time.time()
                })


            # 累加时长
            total_recs[found_playing_song]["duration"] += elapsed
            daily_recs[found_playing_song]["duration"] += elapsed

            # 满一分钟或切歌时保存
            if needs_save or int(total_recs[found_playing_song]["duration"]) % 60 < 5:
                self._save_music_records()

    # 尝试获取资源管理器的当前路径
    def _get_explorer_path(self, target_hwnd):
        if not self.shell: return None
        try:
            # 遍历所有打开的 Explorer 窗口
            windows = self.shell.Windows()
            for window in windows:
                # 必须转换为 int 进行比较，因为 COM 返回的 HWND 可能是 long
                if int(window.HWND) == int(target_hwnd):
                    # 获取 LocationURL (例如: file:///D:/Projects/code_test)
                    raw_url = window.LocationURL
                    if not raw_url: return None

                    # 移除 'file:///' 并解码 (处理空格和中文)
                    path = unquote(raw_url).replace("file:///", "").replace("/", "\\")
                    return path
            return None
        except Exception:
            return None

    def _get_current_context_tag(self):
        """辅助方法：获取当前窗口的Tag，用于心跳检测"""
        if self.window_manager.current_window:
            proc = self.window_manager.current_window.get('process', '')
            title = self.window_manager.current_window.get('title', '')
            return self.analyzer.analyze(proc, title)['tag']
        return "Other"

    def _get_browser_url(self, hwnd):
        """
        [轻量级] 通过 UI Automation 获取浏览器地址栏 URL
        """
        try:
            # 1. 获取窗口对象
            window = auto.ControlFromHandle(hwnd)
            if not window: return None

            # 2. 查找地址栏 (EditControl)
            # Edge/Chrome 的地址栏通常叫 "地址和搜索栏" (中文) 或 "Address and search bar" (英文)
            # Firefox 的 ID 是 "urlbar-input"
            # 为了性能，限制查找深度 maxDepth=4
            address_bar = window.FindFirstDescendant(
                lambda c, d: (
                        c.ControlTypeName == "EditControl" and (
                        "地址" in c.Name or
                        "Address" in c.Name or
                        "搜索" in c.Name or
                        c.AutomationId == "urlbar-input"
                )
                ),
                maxDepth=5
            )

            if address_bar:
                # 3. 获取 ValuePattern (比 Name 更准，Name 可能是 '输入搜索词...')
                return address_bar.GetValuePattern().Value
        except Exception:
            pass
        return None

    def _infer_custom_behavior(self, signature: Dict) -> Optional[str]:
        """
        根据 UI 特征匹配自定义行为标识（基于视口百分比映射 + 锚点策略）
        优化点：规则索引、多锚点校验、DPI 感知、容差优化、除零保护

        :param signature: UI 元素签名字典
            - Process: 进程名
            - AbsX/AbsY: 相对于窗口左上角的绝对坐标
            - W/H: 当前窗口宽高
            - ControlTypeName/AutomationId/Name: 控件特征
        :return: 匹配到的 intent_tag，未匹配返回 None
        """

        # === 1. 基础数据提取与校验 ===
        curr_x = signature.get("AbsX", 0)
        curr_y = signature.get("AbsY", 0)
        curr_w = max(signature.get("W", 1), 1)  # 除零保护
        curr_h = max(signature.get("H", 1), 1)
        process_name = signature.get("Process", "").lower().strip()

        if curr_w <= 0 or curr_h <= 0:
            return None

        # 计算当前点击的窗口百分比坐标 (0.0 ~ 1.0)
        curr_pct_x = curr_x / curr_w
        curr_pct_y = curr_y / curr_h

        # === 2. 规则索引优化 (只遍历当前进程相关的规则) ===
        # 如果已建立 rules_index，优先使用；否则全量遍历（兼容旧版）
        candidate_rules = getattr(self, 'rules_index', {}).get(process_name, [])
        if not candidate_rules:
            # 回退到全量遍历
            candidate_rules = self.behavior_rules

        # 同时合并 default 规则 (如果有全局规则)
        default_rules = getattr(self, 'rules_index', {}).get("default", [])
        if default_rules:
            candidate_rules = candidate_rules + default_rules

        # === 3. 遍历规则进行匹配 ===
        for rule in candidate_rules:
            # --- 第一关：基础静态特征匹配 ---
            match_cond = rule.get("match", {})
            is_match = True

            for key, val in match_cond.items():
                sig_val = str(signature.get(key, " "))
                rule_val = str(val).lower().strip()
                if rule_val and rule_val not in sig_val.lower():
                    is_match = False
                    break

            if not is_match:
                continue

            # 如果没有坐标规则，直接返回意图
            if "locate_rule" not in rule:
                return rule.get("intent_tag")

            # --- 第二关：坐标与缩放基准校验 ---
            locate = rule["locate_rule"]
            strategy = locate.get("strategy", "bottom_center").lower()
            mode = locate.get("mode", "anchor").lower()
            base = locate.get("baseline", {})

            if not base:
                continue

            # 基准数据提取（除零保护）
            ref_w = max(base.get("W", 1), 1)
            ref_h = max(base.get("H", 1), 1)
            ref_x = base.get("X", 0)
            ref_y = base.get("Y", 0)

            # --- 分支 A: 自适应/百分比模式 (adaptive/stretch) ---
            if mode == "adaptive" or "stretch" in strategy:
                # 计算基准百分比
                ref_pct_x = ref_x / ref_w
                ref_pct_y = ref_y / ref_h

                # 获取容差（支持像素容差和百分比容差）
                pct_tolerance = locate.get("tolerance_pct", 0.05)  # 默认 5%
                pixel_tolerance = locate.get("tolerance", 20)

                # 计算百分比误差
                diff_x_pct = abs(curr_pct_x - ref_pct_x)
                diff_y_pct = abs(curr_pct_y - ref_pct_y)

                # 计算像素误差（用于小窗口校验）
                diff_x_px = abs(curr_x - (ref_pct_x * curr_w))
                diff_y_px = abs(curr_y - (ref_pct_y * curr_h))

                # 多条件校验：百分比误差 OR 像素误差（取更宽松的）
                pct_match = diff_x_pct <= pct_tolerance and diff_y_pct <= pct_tolerance
                px_match = diff_x_px <= pixel_tolerance and diff_y_px <= pixel_tolerance

                if pct_match or px_match:
                    return rule.get("intent_tag")
                else:
                    continue  # 自适应模式不匹配，继续下一条规则

            # --- 分支 B: 锚定模式 (anchor) ---
            else:
                # 根据策略计算目标锚点坐标
                target_x, target_y = ref_x, ref_y

                if "top_right" in strategy:
                    # 右上角锚定：X 从右侧计算，Y 从顶部计算
                    target_x = curr_w - (ref_w - ref_x)
                    target_y = ref_y
                elif "bottom_left" in strategy:
                    # 左下角锚定：X 从左侧计算，Y 从底部计算
                    target_x = ref_x
                    target_y = curr_h - (ref_h - ref_y)
                elif "bottom_right" in strategy:
                    # 右下角锚定：X 从右侧计算，Y 从底部计算
                    target_x = curr_w - (ref_w - ref_x)
                    target_y = curr_h - (ref_h - ref_y)
                elif "bottom_center" in strategy:
                    # 底部中心锚定：X 居中，并加上原本相对于中心的偏移量！
                    target_x = curr_w / 2 + (ref_x - ref_w / 2)
                    target_y = curr_h - (ref_h - ref_y)
                elif "top_center" in strategy:
                    # 顶部中心锚定：X 居中，并加上原本相对于中心的偏移量！
                    target_x = curr_w / 2 + (ref_x - ref_w / 2)
                    target_y = ref_y
                elif "center" in strategy:
                    # 中心锚定
                    target_x = curr_w / 2 + (ref_x - ref_w / 2)
                    target_y = curr_h / 2 + (ref_y - ref_h / 2)

                # 获取容差
                tolerance = locate.get("tolerance", 20)
                tolerance_sq = tolerance ** 2

                # 计算欧氏距离平方
                dist_sq = (curr_x - target_x) ** 2 + (curr_y - target_y) ** 2

                if dist_sq <= tolerance_sq:
                    return rule.get("intent_tag")

        # 所有规则都不匹配
        return None

    def on_click(self, x, y, button, pressed):
        if not pressed: return
        with auto.UIAutomationInitializerInThread():
            try:
                control = auto.ControlFromPoint(x, y)
                if not control: return

                btn_map = {mouse.Button.left: "左键", mouse.Button.right: "右键", mouse.Button.middle: "中键"}
                click_type = btn_map.get(button, "点击")

                auto_id = control.AutomationId
                ctrl_type = control.ControlTypeName
                pid = control.ProcessId

                # 如果点击的是宠物自身的窗口，直接退出不记录
                if pid == self.current_pid:
                    return

                process_name = self._get_process_name_by_pid(pid) or ""

                # ==========================================
                # [新增] 突破“UI黑盒”：自动计算完美 Baseline 坐标
                # ==========================================
                rel_x_pct = 0.0
                rel_y_pct = 0.0
                baseline_x = 0
                baseline_y = 0
                rev_x = 0
                rev_y = 0
                win_w = 1
                win_h = 1

                try:
                    # 【核心修正】直接获取最顶层主窗口，作为坐标系的绝对基准
                    root = control.GetTopLevelControl()
                    if root:
                        root_rect = root.BoundingRectangle
                        win_w = root_rect.right - root_rect.left
                        win_h = root_rect.bottom - root_rect.top

                        if win_w > 0 and win_h > 0:
                            # 计算鼠标相对于【窗口左上角】的绝对坐标 (也就是 Baseline 中的 X 和 Y)
                            baseline_x = x - root_rect.left
                            baseline_y = y - root_rect.top

                            # 计算距离右侧和底部的距离 (用于推断锚点)
                            rev_x = win_w - baseline_x
                            rev_y = win_h - baseline_y

                            # 计算百分比
                            rel_x_pct = round((baseline_x / win_w) * 100, 1)
                            rel_y_pct = round((baseline_y / win_h) * 100, 1)
                except Exception:
                    pass

                # 探针签名 (与我们之前的自适应引擎完全匹配)
                element_signature = {
                    "Process": process_name,
                    "Name": control.Name or "",
                    "ControlTypeName": ctrl_type or "",
                    "AutomationId": auto_id or "",
                    "RelX": rel_x_pct,
                    "RelY": rel_y_pct,
                    "RevX": rev_x,
                    "RevY": rev_y,
                    "AbsX": baseline_x,
                    "AbsY": baseline_y,
                    "W": win_w,
                    "H": win_h
                }

                # 【超级贴心】在终端打印可以直接复制粘贴的 JSON 数据
                print(f"\033[90m🖱️ [UI探针] Process: {process_name} | Type: {ctrl_type}\033[0m")
                print(
                    f"\033[90m   ├─ 复制 Baseline ➡️  \"baseline\": {{\"W\": {win_w}, \"H\": {win_h}, \"X\": {baseline_x}, \"Y\": {baseline_y}}}\033[0m")
                print(
                    f"\033[90m   └─ 锚点参考值   ➡️  RevX(距右): {rev_x} | RevY(距底): {rev_y} | RelX: {rel_x_pct}%\033[0m")
                # ==========================================

                element_name = self._get_smart_element_name(control, process_name)
                action_type = "CLICK"
                intent = "普通点击"

                # 1. 优先使用你的持久化自定义规则匹配意图
                custom_intent = self._infer_custom_behavior(element_signature)
                if custom_intent:
                    intent = custom_intent
                    # 如果匹配上了，还可以改变 action_type 以便后续处理
                    # action_type = "CUSTOM_BEHAVIOR"

                # 2. 如果没匹配上自定义规则，走默认的智能判断
                elif auto_id == "Close" or control.Name == "关闭":
                    intent = "尝试关闭窗口"
                    action_type = "WINDOW_CONTROL"
                    self.last_window_intent = {"action": "Close", "process": process_name, "time": time.time()}
                elif auto_id == "Minimize" or control.Name == "最小化":
                    intent = "尝试最小化"
                    action_type = "WINDOW_CONTROL"
                    self.last_window_intent = {"action": "Minimize", "process": process_name, "time": time.time()}
                elif auto_id == "Maximize":
                    intent = "尝试最大化"
                    action_type = "WINDOW_CONTROL"
                elif auto_id == "TitleBar":
                    intent = "点击标题栏"

                root = control.GetTopLevelControl()
                window_title = root.Name if root else ""

                event_data = {
                    "type": "INTERACTION",
                    "action_type": action_type,
                    "intent": intent,  # 这里可能就是你自定义的 "切换代码文件"
                    "raw_process": process_name,
                    "window_title": window_title,
                    "mouse_button": click_type,
                    "target": element_name,
                    "control_type": ctrl_type,
                    "timestamp": time.time()
                }
                self.event_queue.put(event_data)
            except Exception:
                pass

    def _flush_key_buffer(self):
        """
        [聚合器] 将缓冲区内的零散字符合并为一条完整的“输入”事件。
        """
        if not self.typing_buffer:
            return

        # 兼容旧字符或新字典结构，提取合并文本
        text_content = "".join([item["char"] if isinstance(item, dict) else item for item in self.typing_buffer])

        # 获取第一下敲击发生时的真实环境作为该 Batch 的归属
        first_item = self.typing_buffer[0]
        if isinstance(first_item, dict):
            hist_process = first_item.get("raw_process", "")
            hist_title = first_item.get("window_title", "")
        else:
            # 兜底：如果缓冲里是旧格式（纯字符串），则退回当前全局状态
            hist_process = self.window_manager.current_window.get('process',
                                                                  '') if self.window_manager.current_window else ""
            hist_title = self.window_manager.current_window.get('title',
                                                                '') if self.window_manager.current_window else ""

        batch_event = {
            "type": "KEYBOARD_BATCH",
            "target": text_content,
            "timestamp": time.time(),
            "raw_process": hist_process,
            "window_title": hist_title,
            "action": "Type",
            "intent": f"输入文本: '{text_content}'"
        }

        # 清空缓冲
        self.typing_buffer = []

        # 提交处理
        self._process_finalized_event(batch_event)

    def _get_canonical_key_name(self, key):
        """
        获取按键的标准化名称 (统一左右键，修正大小写)
        """
        raw_name = None

        # 1. 解析原始名称
        if hasattr(key, 'name'):
            # 功能键 (ctrl_l, f1, enter)
            raw_name = key.name
        elif hasattr(key, 'char') and key.char:
            # 字符键
            code = ord(key.char)
            if 0 < code < 32:  # ASCII 控制字符
                raw_name = chr(code + 96)
            else:
                raw_name = key.char
        else:
            raw_name = str(key).replace('Key.', '')

        # 2. === 应用标准化映射 ===
        # 如果在映射表中 (如 ctrl_l -> Ctrl)，则返回标准化名称
        # 如果不在 (如 'a', 'f1')，则原样返回
        return self.KEY_NORMALIZATION.get(raw_name, raw_name)

    def _get_active_modifiers_str(self):
        """
        检查当前状态池，生成组合前缀 (如 'Ctrl+', 'Ctrl+Alt+')
        """
        mods = []
        # 检测 Ctrl
        if keyboard.Key.ctrl_l in self.current_keys or keyboard.Key.ctrl_r in self.current_keys:
            mods.append("Ctrl")
        # 检测 Alt
        if keyboard.Key.alt_l in self.current_keys or keyboard.Key.alt_r in self.current_keys:
            mods.append("Alt")
        # 检测 Shift (可选：有时候 Shift+字母 只想显示大写字母，这里为了演示组合逻辑先加上)
        if keyboard.Key.shift in self.current_keys or keyboard.Key.shift_r in self.current_keys:
            mods.append("Shift")
        # 检测 Win
        if keyboard.Key.cmd in self.current_keys or keyboard.Key.cmd_r in self.current_keys:
            mods.append("Win")

        return "+".join(mods)

    # === 智能获取元素名称的方法 ===
    def _get_smart_element_name(self, control,proc_name=""):
        """
        智能获取元素名称。
        如果当前点击的是资源管理器内部的‘名称’列，自动向上查找父级 ListItem 获取真实文件名。
        """
        try:
            name = control.Name
            type_name = control.ControlTypeName
            auto_id = control.AutomationId

            # 1. 标准窗口控制按钮
            if auto_id in ["Close", "Minimize", "Maximize"] or name in ["关闭", "最小化", "最大化", "还原"]:
                return f"窗口控制[{name or auto_id}]"

            # 2. 忽略通用名称
            generic_names = {"名称", "Name", "UIItem", "", "Pane", "Group", "Custom", "Document"}

            # 3. 有意义的名字直接返回
            if name and name not in generic_names:
                return name

            # 4. 针对“无名元素”的坐标推断逻辑
            if not name and type_name in ["PaneControl", "GroupControl", "CustomControl", "DocumentControl",
                                          "ToolBarControl"]:
                rect = control.BoundingRectangle
                root = control.GetTopLevelControl()

                if root:
                    root_rect = root.BoundingRectangle
                    relative_top = rect.top - root_rect.top

                    # 判断是否在窗口顶部区域 (0-80px)
                    if 0 <= relative_top < 80:
                        # [关键修改] 只有浏览器才叫 "浏览器标题栏"
                        if proc_name in ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"]:
                            # 简单判断宽度，防止是左上角的小图标
                            if (rect.right - rect.left) > 50:
                                return "浏览器标题栏/标签栏区域"
                        else:
                            # 对于 PyCharm (idea64.exe) 或其他应用，显示为通用顶部区域
                            return "顶部菜单/工具栏区域"

                # 降级：如果找不到父窗口，只能显示类型
                return f"未命名区域 ({type_name})"

            # 5. 向上查找父级 (处理列表项内部点击)
            if name in generic_names or type_name in ["TextControl", "EditControl", "ImageControl"]:
                parent = control.GetParentControl()
                for _ in range(3):
                    if not parent: break
                    if parent.ControlTypeName == "ListItemControl" and parent.Name:
                        return parent.Name
                    if parent.ControlTypeName == "TabItemControl" and parent.Name:
                        return f"标签页[{parent.Name}]"
                    if parent.Name and parent.Name not in generic_names:
                        return parent.Name
                    parent = parent.GetParentControl()

            return name if name else f"Unknown ({type_name})"

        except Exception:
            return "Unknown Element"

    def on_key_release(self, key):
        """
        按键释放：清除状态，允许下一次立即触发
        """
        try:
            # 1. 从当前按键池移除 (这是组合键判断的核心)
            if key in self.current_keys:
                self.current_keys.remove(key)

            # 2. 清除防抖计时
            key_name = self._get_canonical_key_name(key)
            if key_name in self.key_states:
                del self.key_states[key_name]
        except:
            pass

    def on_key_press(self, key):
        """
        按键按下：记录状态 -> 组合判断 -> 输出
        修复点：使用 _get_canonical_key_name 应用映射表，并恢复组合键逻辑
        """
        try:
            # 1. 立即加入状态池 (确保后续组合逻辑能读到它)
            self.current_keys.add(key)

            # === 获取标准化名称 (此处应用了 KEY_NORMALIZATION) ===
            base_key_name = self._get_canonical_key_name(key)

            # === 防抖动逻辑 ===
            current_time = time.time()
            is_repeat = False

            # 使用标准化名称进行防抖记录
            if base_key_name in self.key_states:
                last_time = self.key_states[base_key_name]
                if self.REPEAT_INTERVAL and (current_time - last_time < self.REPEAT_INTERVAL):
                    return  # 🔇 忽略重复触发
                else:
                    is_repeat = True

            # 更新最后触发时间
            self.key_states[base_key_name] = current_time
            # =================

            # === 核心：组合键推导 ===
            final_display_name = base_key_name

            # 如果当前按下的键本身不是修饰键 (例如按下了 'c')
            if key not in self.MODIFIER_KEYS:
                # 获取当前按住的修饰符前缀 (如 "Ctrl+")
                mod_str = self._get_active_modifiers_str()
                if mod_str:
                    final_display_name = f"{mod_str}+{base_key_name}"
            # =======================

            # 获取上下文
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)

            # 如果是自己在最前面（比如正在输入框打字），忽略键盘记录
            if pid == self.current_pid:
                return

            window_title = win32gui.GetWindowText(hwnd)
            process_name = self._get_process_name_by_pid(pid)

            event_data = {
                "type": "KEYBOARD",
                "raw_process": process_name,
                "window_title": window_title,
                "action": "PRESS",
                "target": final_display_name,  # 这里将输出 "Ctrl" 或 "Ctrl+c"
                "target_type": "Key",
                "is_repeat": is_repeat
            }
            self.event_queue.put(event_data)

        except Exception as e:
            print(f"Key Error: {e}")
            pass

    # --- 环境监控：集成栈管理器 ---
    def monitor_environment(self):
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)

                # 焦点在自己身上时，不将其记录为环境切换
                if pid == self.current_pid:
                    return

                title = win32gui.GetWindowText(hwnd)
                proc_name = self._get_process_name_by_pid(pid)

                if proc_name:
                    # 更新窗口栈
                    change_event = self.window_manager.update_focus(
                        hwnd, title, proc_name, self.last_window_intent
                    )

                    if change_event:
                        # === 浏览器 URL 增强检测 ===
                        # 只有当是浏览器，且发生了切换或标题变动时，才去读 URL (节省性能)
                        url_context_override = None
                        browser_url = ""

                        if proc_name.lower() in ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"]:
                            browser_url = self._get_browser_url(hwnd)
                            # 如果拿到了 URL，交给 analyzer 匹配
                            if browser_url:
                                url_context_override = self.analyzer.analyze_url(browser_url)

                        # 获取基础路径 (资源管理器)
                        explorer_path = None
                        if proc_name.lower() == "explorer.exe":
                            explorer_path = self._get_explorer_path(hwnd)

                        # 构造事件
                        event_data = {
                            "type": "FOCUS_SWITCH",
                            "raw_process": proc_name,
                            "window_title": title,
                            "explorer_path": explorer_path,
                            "browser_url": browser_url,  # 记录 URL 供调试
                            "switch_type": change_event['type'],
                            "stack_info": self.window_manager.get_stack_str(),
                            "popped_wins": change_event.get('popped_wins', [])
                        }

                        # === 如果 URL 匹配到了特定场景，强行覆写 Tag ===
                        if url_context_override:
                            event_data["context_tag"] = url_context_override["tag"]
                            event_data["context_desc"] = f"{url_context_override['desc']} ({proc_name})"

                        self.event_queue.put(event_data)
        except:
            pass

    def _get_current_reset_date(self):
        """获取当前的业务日期（以凌晨 4:00 为界）"""
        now = datetime.datetime.now()
        if now.hour < 4:
            # 如果还没到凌晨 4 点，算作前一天
            return (now - datetime.timedelta(days=1)).date()
        return now.date()

    def _update_game_timer(self):
        """记录用户游玩时间：支持多游戏独立计时与按日切分"""
        current_date_str = self._get_current_reset_date().isoformat()

        # 初始化防御
        if "daily" not in self.game_records: self.game_records["daily"] = {}
        if current_date_str not in self.game_records["daily"]:
            self.game_records["daily"][current_date_str] = {}
        if "total" not in self.game_records: self.game_records["total"] = {}

        # 1. 实时结算之前的会话时长
        if self.current_game_session is not None:
            prev_key = self.current_game_session["key"]
            elapsed = time.time() - self.current_game_session["start_time"]

            self.game_records["total"][prev_key] = self.game_records["total"].get(prev_key, 0.0) + elapsed
            self.game_records["daily"][current_date_str][prev_key] = self.game_records["daily"][current_date_str].get(
                prev_key, 0.0) + elapsed

            # 重置计时基准点
            self.current_game_session["start_time"] = time.time()

        # 2. 获取当前聚焦的应用
        curr_win = self.window_manager.current_window
        current_tag = 'Other'
        game_desc = 'Unknown Game'
        proc = ''

        if curr_win:
            proc = curr_win.get('process', '')
            title = curr_win.get('title', '')
            context = self.analyzer.analyze(proc, title)
            current_tag = context.get('tag', 'Other')
            game_desc = context.get('desc', 'Unknown Game')

        # 3. 游戏状态机检测
        if current_tag == "Game":
            game_key = f"{proc} | {game_desc}"
            # 刚切入或者换了新游戏
            if self.current_game_session is None or self.current_game_session["key"] != game_key:
                self.current_game_session = {"key": game_key, "start_time": time.time()}
                print(f"\033[92m🎮 [游戏计时] 正在游玩: {game_desc} ({proc})\033[0m")
        else:
            # 切出了游戏
            if self.current_game_session is not None:
                prev_key = self.current_game_session["key"]
                game_name = prev_key.split(' | ')[1]
                daily_total = self.game_records["daily"][current_date_str].get(prev_key, 0.0)
                m, s = divmod(int(daily_total), 60)
                h, m = divmod(m, 60)
                print(f"\033[93m⏸️ [游戏计时] 已切出游戏。{game_name} 今日游玩: {h}h {m}m {s}s\033[0m")
                self.current_game_session = None
                self._save_game_records()  # 切出时落地一次即可

    def print_console_log(self, event):
        """
        [调试展示] 在终端打印带颜色的、易于人类阅读的日志。
        包含：颜色高亮、图标、层级缩进等视觉辅助。
        """
        # 心跳事件通常不打印，除非为了深度调试
        if event['type'] == 'HEARTBEAT':
            return

        t = time.strftime("%H:%M:%S", time.localtime(event.get('timestamp', time.time())))
        tag = event.get('context_tag', 'Other')
        desc = event.get('context_desc', '')
        process = event.get('raw_process', '')

        # === 颜色定义 (ANSI Escape Codes) ===
        C_RESET = "\033[0m"
        C_TIME = "\033[90m"  # 深灰
        C_TAG = "\033[35m"  # 紫色 (Tag)
        C_APP = "\033[36m"  # 青色 (应用)
        C_ACT = "\033[33m"  # 黄色 (动作)
        C_OBJ = "\033[97m"  # 亮白 (对象)
        C_WARN = "\033[91m"  # 红色 (警告/关闭)
        C_OK = "\033[92m"  # 绿色 (打开/新建)

        # 格式化 Tag 头部： [10:00:00] [Coding   ]
        header = f"{C_TIME}[{t}]{C_RESET} {C_TAG}[{tag:<8}]{C_RESET}"

        if event['type'] == "INTERACTION":
            action = event.get('mouse_button', 'Click')
            intent = event.get('intent', 'Click')
            target = event.get('target', 'Unknown')

            # 区分窗口控制操作和普通操作
            if event.get('action_type') == 'WINDOW_CONTROL':
                print(f"{header} {C_WARN}{intent}{C_RESET} -> {target} ({C_APP}{desc}{C_RESET})")
            else:
                # 这是一个类似 "用户 在 Chrome 中 点击了 搜索框" 的句子
                print(
                    f"{header} {self.role}在 {C_APP}{desc}{C_RESET} {C_ACT}{intent}{C_RESET}: {C_OBJ}[{target}]{C_RESET}")

        elif event['type'] == "KEYBOARD":
            key = event['target']
            print(f"{header} {self.role}在 {C_APP}{desc}{C_RESET} 输入: {C_ACT}{key}{C_RESET}")

        elif event['type'] == "KEYBOARD_BATCH":
            text = event['target']
            # 使用不同的颜色或格式表示连续输入
            print(f"{header} {self.role}在 {C_APP}{desc}{C_RESET} 输入: {C_ACT}\"{text}\"{C_RESET}")

        elif event['type'] == "FOCUS_SWITCH":
            switch_type = event.get('switch_type')
            title = event.get('window_title', 'Unknown')
            stack = event.get('stack_info', '[]')

            if switch_type == "SWITCH_NEW":
                print(f"{header} {C_OK}>>> 切换聚焦{C_RESET}: {C_OBJ}{title}{C_RESET} {C_TIME}{stack}{C_RESET}")
            elif switch_type == "SWITCH_BACK":
                print(f"{header} {C_WARN}<<< 返回窗口{C_RESET}: {C_OBJ}{title}{C_RESET} {C_TIME}{stack}{C_RESET}")
            elif switch_type == "TITLE_UPDATE":
                print(f"{header} ... 标题更新: {title}")

    def _create_ai_memory(self, event):
        """
        [数据清洗] 生成专门给 AI/LLM 读取的结构化数据字典。
        特点：纯净、无格式化代码、语义明确。
        """
        timestamp = event.get('timestamp', time.time())
        time_str = time.strftime("%H:%M:%S", time.localtime(timestamp))

        # 基础结构
        memory_item = {
            "time": time_str,
            "tag": event.get('context_tag', 'Unknown'),
            "app_desc": event.get('context_desc', 'Unknown App'),
            "process": event.get('raw_process', ''),  # 保留进程名供 AI 辅助判断
            "type": event['type']
        }

        # 根据事件类型填充具体的语义内容
        if event['type'] == 'INTERACTION':
            memory_item["action"] = event.get('intent', 'Click')
            memory_item["target"] = event.get('target', 'Unknown Element')
            # 如果是双击，特别标注
            if "双击" in str(event.get('mouse_button', '')):
                memory_item["action"] = "Double Click"

        elif event['type'] == 'KEYBOARD':
            memory_item["action"] = "Type"
            memory_item["target"] = event.get('target', '')

        # 增加对 BATCH 的支持
        elif event['type'] == 'KEYBOARD_BATCH':
            memory_item["action"] = "Type Text"
            memory_item["target"] = f"\"{event.get('target', '')}\""  # 加上引号表示字符串

        elif event['type'] == 'SYSTEM_STATE' and event.get('action_type') == 'MUSIC_CHANGE':
            memory_item["action"] = "Song Changed To"
            memory_item["target"] = event.get('target', '')

        elif event['type'] == 'FOCUS_SWITCH':
            memory_item["action"] = "Switch Window"
            # 记录完整标题，这对 AI 理解当前工作内容至关重要
            memory_item["target"] = event.get('window_title', '')
            if event.get('explorer_path'):
                memory_item["path"] = event['explorer_path']

        return memory_item

    def _debug_visualize_packet(self, packet):
        """
        [调试专用] 生成一张包含“截图 + 日志流 + 触发信息”的组合诊断图。
        用于验证发送给 AI 的数据上下文是否符合预期。
        """
        try:
            # 1. 解包数据
            instruction = packet['instruction']
            logs = packet['recent_logs']
            trigger = packet['trigger_event']

            reason = instruction['reason']
            scope = instruction['capture_scope']
            tag = trigger['tag']

            # 2. 实时捕获一张截图用于预览 (模拟实际截图线程的工作)
            # 注意：实际生产中这一步是在独立线程做的，这里为了调试直接并在主线程做
            if scope == 'window':
                # 简易实现：调试模式下暂时截全屏，实际可用 win32gui 获取 rect 裁剪
                # 或者在图上画个框表示 focus 区域
                screen_img = ImageGrab.grab()
                capture_mode_text = "Mode: Active Window (Preview shows Full Screen)"
            else:
                screen_img = ImageGrab.grab()
                capture_mode_text = "Mode: Full Screen"

            # 3. 创建画布 (利用 Matplotlib)
            # 设置一个宽一点的图：左边放日志，右边放截图
            fig = plt.figure(figsize=(16, 9), dpi=100)
            fig.suptitle(f"AI Context Debugger - Trigger: [{reason}]", fontsize=16, color='red', weight='bold')

            # === 左侧：日志流 (Text) ===
            ax_log = fig.add_subplot(1, 3, 1)  # 占 1/3 宽度
            ax_log.axis('off')
            ax_log.set_title(f"Context Logs ({len(logs)} items)", fontsize=12, color='blue')

            # 构造日志文本
            log_text_lines = []
            for item in logs[-25:]:  # 只显示最近25条防止溢出
                t_str = item.get('time', '')
                act = item.get('action', '')
                tgt = str(item.get('target', ''))[:20]  # 截断过长目标
                line = f"[{t_str}] {act}: {tgt}"
                log_text_lines.append(line)

            # 加上触发事件（高亮）
            trigger_line = f"\n>>> TRIGGER: {trigger.get('action')} {trigger.get('target')}"
            log_text_lines.append(trigger_line)

            # 绘制文本
            ax_log.text(0.05, 0.95, "\n".join(log_text_lines),
                        transform=ax_log.transAxes,
                        fontsize=10, verticalalignment='top', fontfamily='monospace')

            # === 右侧：截图预览 (Image) ===
            ax_img = fig.add_subplot(1, 3, (2, 3))  # 占 2/3 宽度
            ax_img.axis('off')
            ax_img.set_title(f"Visual Input Preview [{tag}]", fontsize=12, color='green')
            ax_img.imshow(screen_img)

            # 在图片下方标注模式
            ax_img.text(0.5, -0.05, capture_mode_text,
                        transform=ax_img.transAxes, ha='center', fontsize=10, style='italic')

            # 4. 保存诊断图
            debug_dir = "./debug_captures"
            if not os.path.exists(debug_dir):
                os.makedirs(debug_dir)

            timestamp = int(time.time())
            filename = f"{debug_dir}/debug_{tag}_{timestamp}.png"
            plt.tight_layout()
            plt.savefig(filename)
            plt.close(fig)  # 释放内存

            print(f"   📊 [调试绘图] 诊断卡片已生成: {filename}")

        except Exception as e:
            print(f"⚠️ 调试绘图失败: {e}")

    def _generate_narrative(self, logs: List[Dict], trigger_event: Dict) -> str:
        """
        [Prompt Context] 将结构化日志转化为连贯的自然语言描述。
        保留时间流、应用上下文和操作细节，并在末尾标注触发点。
        """

        def format_time(total_seconds):
            h, rem = divmod(int(total_seconds), 3600)
            m, s = divmod(rem, 60)
            if h > 0:
                return f"{h}小时{m}分"
            elif m > 0:
                return f"{m}分{s}秒"
            else:
                return f"{s}秒"

        lines = []

        # 即使没有新日志，也保留上下文标题
        if logs or trigger_event:
            lines.append("### User Activity Context (Time Sequence):")

            display_logs = list(logs)[-10:]  # 只取最近的10条
            if trigger_event and (not display_logs or display_logs[-1].get('time') != trigger_event.get('time')):
                display_logs.append(trigger_event)

            for i, item in enumerate(display_logs):
                time_str = item.get('time', '00:00:00')
                app = item.get('app_desc', 'Unknown App').split('(')[0].strip()  # 清洗应用名
                action = item.get('action', '')
                target = item.get('target', '')
                tag = item.get('tag', 'Other')

                # 构造更自然的句子结构
                sentence = ""
                if action == "Switch Window":
                    sentence = f"Switched focus to window '{target}' ({app})."
                elif action == "Type":
                    sentence = f"Typed in {app}: [{target}]."
                elif action == "Type Text":
                    sentence = f"Typed text in {app}: {target}."
                elif action == "Double Click":
                    sentence = f"Double-clicked '{target}' in {app}."
                else:
                    sentence = f"{action} on '{target}' in {app}."

                line = f"[{time_str}] [{tag}] {sentence}"

                # 如果是最后一条，标注为触发点
                if i == len(display_logs) - 1:
                    line += " <--- (CURRENT TRIGGER / ACTION POINT)"

                lines.append(line)
        else:
            # 日志被清空且期间无操作时，给出占位提示
            lines.append("### User Activity Context:\n")

        log_text = "\n".join(lines)
        if self.last_chat == log_text:
            log_text = ""
        self.last_chat = log_text

        # 在末尾附加当前的实时聚焦状态
        if self.window_manager.current_window:
            curr_win = self.window_manager.current_window
            curr_title = curr_win.get('title', 'Unknown Title')
            curr_proc = curr_win.get('process', 'Unknown Process')

            # 使用 analyzer 获取当前窗口的语义化标签和描述
            curr_context = self.analyzer.analyze(curr_proc, curr_title)
            curr_tag = curr_context.get('tag', 'Other')
            curr_desc = curr_context.get('desc', 'Unknown App')

            log_text = f"""{log_text}
            ### Current Focus:
            {self.role} is currently focusing on: [{curr_tag}] '{curr_title}' ({curr_desc}).
            """

            today_str = self._get_current_reset_date().isoformat()

            # 1. Game：按今天和总计显示
            if curr_tag == 'Game':
                log_text += "\n### Game Playtime Statistics:\n"
                today_games = dict(self.game_records.get("daily", {}).get(today_str, {}))
                total_games = dict(self.game_records.get("total", {}))

                if today_games:
                    log_text += "【Today】\n"
                    sorted_today = sorted(today_games.items(), key=lambda x: x[1], reverse=True)
                    for key, total_time in sorted_today:
                        m, s = divmod(int(total_time), 60)
                        h, m = divmod(m, 60)
                        game_name = key.split(' | ')[1]
                        log_text += f"- {game_name}: {format_time(total_time)}\n"

                if total_games:
                    log_text += "【Past / Total】\n"
                    # 历史只显示前5，避免文本溢出
                    sorted_total = sorted(total_games.items(), key=lambda x: x[1], reverse=True)[:5]
                    for key, total_time in sorted_total:
                        m, s = divmod(int(total_time), 60)
                        h, m = divmod(m, 60)
                        game_name = key.split(' | ')[1]
                        log_text += f"- {game_name}: {format_time(total_time)}\n"

            # 2. Music：增加基于算分的今天和历史排序
            elif curr_tag == 'Music':
                log_text += "\n### Music Playlist Statistics:\n"
                if hasattr(self, 'last_seen_song') and self.last_seen_song:
                    log_text += f"【Currently Playing】: {self.last_seen_song}\n\n"
                today_music = self.music_records.get("daily", {}).get(today_str, {})
                total_music = self.music_records.get("total", {})

                def get_score(stats):
                    return (0.7 * stats.get('count', 0)) + (0.3 * (stats.get('duration', 0) / 60.0))

                if today_music:
                    log_text += "【Today's Top】\n"
                    sorted_today = sorted(today_music.items(), key=lambda x: get_score(x[1]), reverse=True)[:5]
                    for idx, (song, stats) in enumerate(sorted_today, 1):
                        count = stats['count']
                        m, s = divmod(int(stats['duration']), 60)
                        log_text += f"  {idx}. {song} (Play: {count} times, Time: {format_time(stats['duration'])})\n"

                if total_music:
                    log_text += "【All Time Top】\n"
                    sorted_total = sorted(total_music.items(), key=lambda x: get_score(x[1]), reverse=True)[:5]
                    for idx, (song, stats) in enumerate(sorted_total, 1):
                        count = stats['count']
                        m, s = divmod(int(stats['duration']), 60)
                        log_text += f"  {idx}. {song} (Play: {count} times, Time: {format_time(stats['duration'])})\n"

        return log_text

    def _process_finalized_event(self, event):
        """
        [核心调度] 处理已确认的事件：
        1. 完善语义 (Tagging) & 关联学习 (Associator)
        2. 生成 AI 记忆并存入缓存
        3. [通道 A] 文本快速通道 (Text Flush) - 语义映射修复版
        4. [通道 B] 视觉慢速通道 (Visual Attention) - 截图策略增强版
        5. 最终返回: { "text": str, "image": str|None }
        """
        # ==========================
        # 1. 基础处理
        # ==========================
        # 1.1 语义补全
        if 'context_tag' not in event:
            context = self.analyzer.analyze(event.get("raw_process"), event.get("window_title"))
            event.update({"context_tag": context["tag"], "context_desc": context["desc"]})

        # 1.2 关联学习
        if event['type'] == 'INTERACTION':
            self.associator.register_interaction(event)
        elif event['type'] == 'FOCUS_SWITCH' and event['context_tag'] == 'Other':
            event = self.associator.infer_context(event)

        # 1.3 生成 AI 记忆并存入缓存
        ai_memory_item = None
        # 【修改】排除 KEYBOARD 和 KEYBOARD_BATCH 类型，不加入 AI 日志栈
        if event['type'] != 'HEARTBEAT' and event['type'] not in ['KEYBOARD', 'KEYBOARD_BATCH']:
            ai_memory_item = self._create_ai_memory(event)
            self.log_history.append(ai_memory_item)
            self.print_console_log(event)

        # ==============================================================
        # [通道 A] 文本快速通道 (Text Flush)
        # ==============================================================
        triggered_text_flush = False
        current_tag = event.get('context_tag', 'Other')
        # 优先获取当前场景的完整策略配置
        current_policy = self.visual_attention._get_policy(current_tag)
        capture_mode = current_policy.get('capture_mode', 'hybrid')

        KEY_MAPPING = {
            "paste": ["ctrl+v", "cmd+v", "shift+insert", "paste"],
            "enter": ["enter", "return", "\r", "\n"],
            "copy": ["ctrl+c", "cmd+c"],
            "save": ["ctrl+s", "cmd+s"]
        }

        if current_tag in self.visual_attention.text_policies:
            triggers = self.visual_attention.text_policies[current_tag]
            is_hit = False

            if event['type'] == 'KEYBOARD':
                raw_target = str(event.get('target', '')).lower()
                for trigger in triggers:
                    trigger_lower = trigger.lower()
                    if raw_target == trigger_lower:
                        is_hit = True;
                        break
                    if trigger_lower in KEY_MAPPING and raw_target in KEY_MAPPING[trigger_lower]:
                        is_hit = True;
                        break

            elif event['type'] == 'INTERACTION':
                target_name = str(event.get('target', ''))
                intent = str(event.get('intent', ''))
                action_type = event.get('action_type', '')
                for trigger in triggers:
                    if trigger == "click_send":
                        keywords = ["发送", "send", "搜索", "search", "提交", "submit", "publish"]
                        if any(kw in target_name.lower() for kw in keywords) or \
                                any(kw in intent.lower() for kw in keywords):
                            is_hit = True;
                            break
                    if trigger == "paste" and action_type == 'PASTE':
                        is_hit = True;
                        break

            if is_hit:
                triggered_text_flush = True
                print(f"\033[96m📨 [文本同步] 触发快速上传 ({current_tag} -> {event.get('target')})\033[0m")

        # ==============================================================
        # [通道 B] 视觉慢速通道 (Visual Attention)
        # ==============================================================
        visual_instruction = self.visual_attention.process_event(event)

        # ==============================================================
        # [最终] 构造返回数据 (Prompt Payload)
        # ==============================================================
        # 获取当前场景的捕获模式 (优先使用视觉指令中的配置，否则默认为 hybrid)
        if visual_instruction and 'capture_mode' in visual_instruction:
            capture_mode = visual_instruction.get('capture_mode', capture_mode)

        # [策略判断] 是否需要生成数据包
        should_send = False

        if capture_mode == 'text_only':
            # 模式 1: 仅文本。只要触发了文本通道，就发送
            if triggered_text_flush or visual_instruction:
                should_send = True
                print(f"\033[96m📨 [文本同步] 触发上传 ({current_tag}) -> 模式：仅文本\033[0m ")

        elif capture_mode == 'visual_only':
            # 模式 2: 仅图片。只要触发了视觉通道，就发送
            if visual_instruction:
                should_send = True
                print(f"\033[93m📸 [视觉捕获] 触发截图 ({current_tag}) -> 模式：仅图片\033[0m ")

        elif capture_mode == 'hybrid':
            # 模式 3: 混合。任意通道触发都发送，且包含两者
            if triggered_text_flush or visual_instruction:
                should_send = True
                print(f"\033[95m🔄 [混合模式] 触发上传 ({current_tag}) -> 模式：文本 + 图片\033[0m ")

        if should_send:
            # ==============================================================
            # 针对音乐播放器的“防抢跑”延迟逻辑
            # ==============================================================
            # 如果当前操作的是音乐/媒体软件，且是一个点击互动事件
            if event['type'] == 'INTERACTION' and current_tag in ['Music', 'Media']:
                print("⏳ [状态同步] 正在等待播放器刷新歌名，延迟 1.5 秒发送给 AI...")
                time.sleep(1.5)  # 强行让主线程等 1.5 秒，留给音乐软件网络请求和切歌的时间

                # 强行在这个瞬间扫描一次最新的后台音乐，确保 `self.last_seen_song` 被正确改写
                self._scan_background_music()
            # ==============================================================

            result_packet = {
                "text": None,
                "image": None,
                "mode": capture_mode
            }

            # 1. 准备文本 (visual_only 模式跳过)
            if capture_mode in ['text_only', 'hybrid']:
                result_packet["text"] = self._generate_narrative(list(self.log_history), ai_memory_item)
                # 发送完文本后，清空历史操作日志，防止后续定时任务发送重复数据
                self.log_history.clear()

            # 2. 准备图片 (text_only 模式跳过)
            if capture_mode in ['visual_only', 'hybrid'] and visual_instruction:
                try:
                    save_dir = "./captures"
                    if not os.path.exists(save_dir):
                        os.makedirs(save_dir)

                    # ====== 延迟截图逻辑，等待当前人宠交互结束 ======
                    if hasattr(self, 'busy_check_callback') and self.busy_check_callback:
                        while self.busy_check_callback():
                            print("⏳ [视觉捕获] 检测到用户正在与宠物交互，延迟截图...")
                            time.sleep(2.0)
                    # ===================================================

                    # 使用 jpg 格式以便于控制压缩质量
                    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"capture_{current_tag}_{timestamp_str}.jpg"
                    full_path = os.path.abspath(os.path.join(save_dir, filename))

                    # --- A. 获取策略参数 ---
                    scope = visual_instruction.get('capture_scope', 'window')  # window / screen
                    quality_level = visual_instruction.get('quality', 'medium')  # high / medium / low

                    # --- B. 执行截图 (Scope Logic) ---
                    screen_img = None
                    captured_mode = "Screen"

                    # 1. 截图前触发隐藏回调，并稍微等待 UI 刷新
                    if self.before_capture_callback:
                        self.before_capture_callback()
                        time.sleep(0.15)

                    if scope == 'window':
                        try:
                            hwnd = win32gui.GetForegroundWindow()
                            if hwnd:
                                # 获取窗口坐标 (Left, Top, Right, Bottom)
                                rect = win32gui.GetWindowRect(hwnd)
                                x1, y1, x2, y2 = rect
                                w, h = x2 - x1, y2 - y1

                                # 只有当窗口尺寸有效且未最小化时才截窗口
                                if w > 10 and h > 10 and not win32gui.IsIconic(hwnd):
                                    # 处理 Windows 10/11 窗口边框阴影导致的负坐标偏移 (可选，视情况微调)
                                    # 通常 ImageGrab 能处理，但如果 x1 < 0 可能需要 max(0, x1)
                                    screen_img = ImageGrab.grab(bbox=rect)
                                    captured_mode = "Active Window"
                                else:
                                    screen_img = ImageGrab.grab()  # 回退到全屏
                                    captured_mode = "Screen (Fallback)"
                            else:
                                screen_img = ImageGrab.grab()
                        except Exception as e:
                            print(f"⚠️ Window capture error: {e}, using full screen.")
                            screen_img = ImageGrab.grab()
                    else:
                        # 默认全屏
                        screen_img = ImageGrab.grab()

                        # 2. 截图完毕后，立刻触发恢复回调
                        if self.after_capture_callback:
                            self.after_capture_callback()

                    # --- C. 处理画质 (Quality Logic) ---
                    if screen_img:
                        # 1. 转换为 RGB (JPEG 不支持 RGBA)
                        if screen_img.mode in ('RGBA', 'P'):
                            screen_img = screen_img.convert('RGB')

                        orig_w, orig_h = screen_img.size
                        save_quality = 85  # 默认 medium

                        # 根据配置调整分辨率和压缩率
                        if quality_level == 'low':
                            # 低画质: 长边限制 800px, 质量 60
                            max_side = 800
                            save_quality = 60
                            if max(orig_w, orig_h) > max_side:
                                ratio = max_side / max(orig_w, orig_h)
                                new_size = (int(orig_w * ratio), int(orig_h * ratio))
                                screen_img = screen_img.resize(new_size, Image.LANCZOS)

                        elif quality_level == 'medium':
                            # 中画质: 长边限制 1600px, 质量 80 (平衡点)
                            max_side = 1600
                            save_quality = 80
                            if max(orig_w, orig_h) > max_side:
                                ratio = max_side / max(orig_w, orig_h)
                                new_size = (int(orig_w * ratio), int(orig_h * ratio))
                                screen_img = screen_img.resize(new_size, Image.LANCZOS)

                        else:  # 'high'
                            # 高画质: 原尺寸, 质量 95
                            save_quality = 95

                        # 保存文件
                        screen_img.save(full_path, quality=save_quality, optimize=True)
                        image_path = full_path

                        reason = visual_instruction.get('reason', 'unknown')
                        final_size = screen_img.size
                        print(
                            f"\033[93m📸 [视觉捕获] Saved: {filename}\n   ├─ Mode: {captured_mode} | Reason: {reason}\n   └─ Quality: {quality_level} | Res: {final_size} | File: {full_path}\033[0m")
                        result_packet["image"] = full_path
                except Exception as e:
                    print(f"⚠️ Snapshot failed: {e}")

            return result_packet

        return None

    def run(self):
        print("🚀 监控主循环已启动 (集成心跳检测与日志缓存)...")
        try:
            while self.is_running:
                # 1. 自身环境轮询 (窗口栈更新)
                self.monitor_environment()

                # 触发后台扫描与计时器更新
                self._scan_background_music()
                self._update_game_timer()

                # 检查打字超时 (Timeout Flush)
                # 如果缓冲区有字，且很久没按键了，强制提交
                if self.typing_buffer and (time.time() - self.last_typing_time > self.TYPING_FLUSH_TIMEOUT):
                    self._flush_key_buffer()

                # 2. 检查缓冲的单击是否超时
                if self.pending_click:
                    if time.time() - self.pending_click['timestamp'] > self.DOUBLE_CLICK_LIMIT:
                        self._process_finalized_event(self.pending_click)  # 超时，作为单击处理
                        self.pending_click = None

                # 3. 获取事件 (带超时机制，实现心跳)
                try:
                    # timeout=0.5 意味着每 0.5 秒如果没有新事件，就会抛出 Empty 异常
                    # 这 0.5 秒就是我们的“时间粒度”，用于驱动 Game/Video 的自动熵值增加
                    event = self.event_queue.get(timeout=0.1)

                    # =========================================
                    # [核心] 输入聚合拦截逻辑
                    # =========================================
                    # 1. 如果有 非键盘事件 (鼠标、切窗口等)，先强制提交缓冲区
                    if event['type'] != 'KEYBOARD' and self.typing_buffer:
                        self._flush_key_buffer()

                    # 2. 处理键盘事件
                    if event['type'] == 'KEYBOARD':
                        key = event['target']

                        # 判断是否为“普通字符” (单字符，非功能键，非组合键)
                        # 简单的判断逻辑：长度为1 且 不是组合键(不含+)
                        is_char = len(key) == 1 and '+' not in key

                        if is_char:
                            # 记录打字时间
                            self.last_typing_time = time.time()
                            # 携带当时的真实窗口上下文入队
                            self.typing_buffer.append({
                                "char": key,
                                "raw_process": event.get("raw_process", ""),
                                "window_title": event.get("window_title", "")
                            })

                        elif key.lower() == 'backspace':
                            # 智能退格：如果缓存里有字，就删掉一个，不记录日志
                            if self.typing_buffer:
                                self.typing_buffer.pop()
                                self.last_typing_time = time.time()
                            else:
                                # 缓存空了还按退格，说明在删以前的内容，需要记录
                                self._flush_key_buffer()  # 防御性提交
                                self._process_finalized_event(event)

                        elif key.lower() in ['enter', 'tab', 'esc'] or '+' in key:
                            # 遇到回车、Tab、组合键 -> 立即提交缓冲区，再记录当前按键
                            self._flush_key_buffer()
                            self._process_finalized_event(event)

                        else:
                            # 其他功能键 (F1, Home等)
                            self._flush_key_buffer()
                            self._process_finalized_event(event)

                        # 跳过后续流程，进入下一次循环
                        continue

                    # === A. 有新事件发生 ===
                    # 判断是否为窗口控制 (关闭/最小化)，此类操作不走双击缓冲
                    is_window_control = event.get('action_type') == 'WINDOW_CONTROL'

                    # [双击检测逻辑]
                    if event['type'] == 'INTERACTION' and event['mouse_button'] == '左键' and not is_window_control:
                        if self.pending_click:
                            # 缓冲里已有点击 -> 检查是否构成双击
                            time_diff = event['timestamp'] - self.pending_click['timestamp']
                            is_same_target = event['target'] == self.pending_click['target']

                            if time_diff < self.DOUBLE_CLICK_LIMIT and is_same_target:
                                # -> 触发双击
                                event['intent'] = "双击打开/运行"
                                event['mouse_button'] = "左键双击"
                                self._process_finalized_event(event)  # 处理双击事件
                                self.pending_click = None  # 清空缓冲
                            else:
                                # -> 非双击 (目标不同或超时)
                                self._process_finalized_event(self.pending_click)  # 先把旧的发出
                                self.pending_click = event  # 存入新的
                        else:
                            # -> 第一下点击，存入缓冲
                            self.pending_click = event
                    else:
                        # -> 其他事件 (键盘、右键、Focus等)，直接处理
                        # 如果有缓冲的单击，先清理掉 (保持时间顺序)
                        if self.pending_click:
                            self._process_finalized_event(self.pending_click)
                            self.pending_click = None

                        self._process_finalized_event(event)

                except queue.Empty:
                    # === B. 超时 (无操作) -> 触发心跳 ===
                    # 即使没有用户操作，我们也需要告诉 VisualAttentionManager 时间在流逝
                    # 这对于 Game 和 Video 场景至关重要 (自动加分)

                    current_tag = self._get_current_context_tag()

                    heartbeat_event = {
                        "type": "HEARTBEAT",
                        "context_tag": current_tag,
                        "timestamp": time.time(),
                        # 可以在这里携带一些空字段防止报错
                        "raw_process": "",
                        "window_title": ""
                    }

                    # 心跳事件也会进入 process，但只会被视觉引擎消费，不会打印日志
                    self._process_finalized_event(heartbeat_event)

        except KeyboardInterrupt:
            self.mouse_listener.stop()
            self.keyboard_listener.stop()
            print("\n🛑 监控已停止")


if __name__ == "__main__":
    monitor = DesktopMonitor(role="用户")
    monitor.run()
