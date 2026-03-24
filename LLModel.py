import json
import re
import time
import io
import hashlib
import base64
import mimetypes
import os
import torch
from pathlib import Path
import torch.nn.functional as F
from typing import Any, Dict, Generator, List, Optional, Union, Tuple
from urllib.parse import urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from openai import OpenAI, OpenAIError
from torch import Tensor

# 可选依赖：仅在需要时导入
try:
    from PIL import Image, ImageOps

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = ImageOps = None

try:
    import cv2

    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    cv2 = None

# 可选依赖：仅在使用重排/向量化功能时导入
try:
    from modelscope import AutoTokenizer, AutoModel, AutoModelForCausalLM
except ImportError:
    AutoTokenizer = AutoModel = AutoModelForCausalLM = None


class LLModel:
    """统一的大语言模型接口类，支持聊天、重排和向量化功能"""

    def __init__(
            self,
            chat_model: str = "qwen:latest",
            api_key: Optional[str] = None,
            base_url: Optional[str] = None,
            use_ollama: bool = False,
            timeout: Optional[float] = None,
            device: str = "cpu",
            embedding_model_dir: Optional[str] = "Qwen/Qwen3-Embedding-0.6B",
            rerank_model_dir: Optional[str] = "Qwen/Qwen3-Reranker-0.6B",
            # ===== 多模态精细化控制 =====
            auto_compress_image: bool = False,  # 图片是否自动压缩
            max_image_size: int = 1024,  # 图片最大边长（仅当auto_compress_image=True时生效）
            auto_extract_video_frames: bool = False,  # 视频是否自动抽帧
            max_video_frames: int = 3,  # 视频最大抽帧数（仅当auto_extract_video_frames=True时生效）
            # ===== 临时文件管理 =====
            temp_download_dir: Optional[str] = None,  # 自定义临时下载目录（默认: 项目目录/temp/download）
            download_timeout: int = 30,  # URL下载超时（秒）
            cleanup_downloaded_files: bool = True,  # 是否自动清理下载的临时文件
    ):
        """
        初始化LLModel

        Args:
            chat_model: 聊天模型名称（默认值仅作参考，调用时可覆盖）
            api_key: OpenAI API密钥（Ollama模式可省略）
            base_url: API基础URL
            use_ollama: 是否使用Ollama本地服务
            timeout: API 请求超时时间
            device: 模型运行设备（cpu/cuda）
        """
        # 聊天模型配置（仅作默认参考，调用时可覆盖）
        self.chat_model = chat_model
        self.api_key = api_key
        self.base_url = base_url
        self.use_ollama = use_ollama
        self.timeout = timeout

        # 客户端缓存：避免相同配置重复创建
        self._client_cache: Dict[Tuple[str, str, Optional[float]], OpenAI] = {}

        # 重排模型配置
        self.rerank_model_dir = rerank_model_dir
        self.reranker_tokenizer = None
        self.reranker_model = None
        self.reranker_device = device
        self._reranker_prefix = None
        self._reranker_suffix = None
        self._token_true_id = None
        self._token_false_id = None

        # 向量化模型配置
        self.embedding_model_dir = embedding_model_dir
        self.embedding_tokenizer = None
        self.embedding_model = None
        self.embedding_device = device

        # 常量配置
        self.max_length = 8192
        # ===== 新增多模态控制参数 =====
        self.auto_compress_image = auto_compress_image
        self.max_image_size = max_image_size
        self.auto_extract_video_frames = auto_extract_video_frames
        self.max_video_frames = max_video_frames

        # ===== 临时文件管理 =====
        self.download_timeout = download_timeout
        self.cleanup_downloaded_files = cleanup_downloaded_files

        # 设置临时下载目录（项目级）
        if temp_download_dir:
            self.temp_download_dir = Path(temp_download_dir).resolve()
        else:
            # 自动定位项目根目录（向上查找直到找到pyproject.toml/setup.py）
            project_root = self._find_project_root()
            self.temp_download_dir = project_root / "temp" / "download"

        self._ensure_temp_dirs()
        self._downloaded_files: List[Path] = []  # 跟踪下载的临时文件（用于清理）

    def _find_project_root(self) -> Path:
        """智能定位项目根目录（向上查找直到找到项目标识文件）"""
        current = Path.cwd()
        max_depth = 10

        # 项目标识文件列表（按优先级）
        project_markers = [
            "pyproject.toml",
            "setup.py",
            "requirements.txt",
            ".git",
            "src",
            "app",
            ".env"
        ]

        for _ in range(max_depth):
            if any((current / marker).exists() for marker in project_markers):
                return current
            parent = current.parent
            if parent == current:  # 到达根目录
                break
            current = parent

        # 未找到项目根目录，回退到当前工作目录
        return Path.cwd()

    def _ensure_temp_dirs(self):
        """确保临时目录存在且有写入权限"""
        try:
            self.temp_download_dir.mkdir(parents=True, exist_ok=True)
            # 创建清理锁文件目录（用于跨进程安全清理）
            (self.temp_download_dir / ".locks").mkdir(exist_ok=True)
        except PermissionError as e:
            raise PermissionError(
                f"无法创建临时目录 {self.temp_download_dir}，请检查权限:\n{str(e)}"
            )

    # ==================== URL下载与临时文件管理 ====================
    def _is_url(self, path: str) -> bool:
        """判断是否为有效URL"""
        try:
            result = urlparse(path)
            return all([result.scheme in ("http", "https"), result.netloc])
        except Exception:
            return False

    def _download_file(self, url: str) -> Path:
        """安全下载URL到临时目录（带重试和校验）"""
        # 生成唯一文件名（避免重复下载相同URL）
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        parsed = urlparse(url)
        ext = os.path.splitext(parsed.path)[1] or ".bin"
        safe_filename = f"{url_hash}_{int(time.time())}{ext}"
        temp_path = self.temp_download_dir / safe_filename

        # 配置带重试的session
        session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))
        session.mount("http://", HTTPAdapter(max_retries=retries))

        try:
            response = session.get(
                url,
                timeout=self.download_timeout,
                stream=True,
                headers={"User-Agent": "LLModel/1.0"}
            )
            response.raise_for_status()

            # 流式下载（避免大文件内存溢出）
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # 验证文件大小（防止空文件）
            if temp_path.stat().st_size == 0:
                temp_path.unlink()
                raise ValueError(f"下载的文件为空: {url}")

            # 记录下载文件（用于后续清理）
            self._downloaded_files.append(temp_path)
            return temp_path

        except requests.RequestException as e:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise RuntimeError(f"URL下载失败 ({url}): {str(e)}") from e
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise RuntimeError(f"文件处理异常 ({url}): {str(e)}") from e

    def _cleanup_temp_files(self):
        """清理所有下载的临时文件（安全模式）"""
        if not self.cleanup_downloaded_files:
            return

        for file_path in self._downloaded_files[:]:  # 复制列表避免迭代时修改
            try:
                if file_path.exists():
                    # 获取文件锁（防止多进程冲突）
                    lock_file = self.temp_download_dir / ".locks" / f"{file_path.name}.lock"
                    try:
                        lock_file.touch(exist_ok=True)
                        file_path.unlink()
                        self._downloaded_files.remove(file_path)
                    finally:
                        lock_file.unlink(missing_ok=True)
            except Exception as e:
                print(f"⚠️  临时文件清理失败 {file_path}: {str(e)}")

        # 定期清理过期临时文件（>24小时）
        self._cleanup_expired_files()

    def _cleanup_expired_files(self, max_age_hours: int = 24):
        """清理过期临时文件（避免磁盘占满）"""
        try:
            cutoff = time.time() - (max_age_hours * 3600)
            for item in self.temp_download_dir.iterdir():
                if item.is_file() and item.stat().st_mtime < cutoff:
                    # 跳过锁文件
                    if item.name.endswith(".lock"):
                        continue
                    try:
                        item.unlink()
                    except Exception:
                        pass  # 忽略清理失败
        except Exception:
            pass  # 静默失败（不影响主流程）

    def _process_files_for_vision(
            self,
            files: List[str],
            user_prompt: str = ""
    ) -> Tuple[List[Dict[str, Any]], List[Path]]:
        """
        处理多模态文件（支持URL+精细化控制）

        Returns:
            content: OpenAI Vision格式内容数组
            temp_files: 需要后续清理的临时文件列表
        """
        if not files:
            return ([{"type": "text", "text": user_prompt}] if user_prompt else [], [])

        content = []
        temp_files_to_cleanup: List[Path] = []

        if user_prompt:
            content.append({"type": "text", "text": user_prompt})

        for file_input in files:
            # 步骤1: 处理URL → 本地路径
            if self._is_url(file_input):
                local_path = self._download_file(file_input)
                temp_files_to_cleanup.append(local_path)
                file_path = local_path
            else:
                file_path = Path(file_input).resolve()
                if not file_path.exists():
                    raise FileNotFoundError(f"文件不存在: {file_path}")

            # 步骤2: 检测MIME类型
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if mime_type is None:
                ext = file_path.suffix.lower()
                if ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]:
                    mime_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else f"image/{ext[1:]}"
                elif ext in [".mp4", ".avi", ".mov", ".mkv", ".webm"]:
                    mime_type = "video/mp4" if ext != ".webm" else "video/webm"
                else:
                    raise ValueError(f"无法识别文件类型: {file_path} (扩展名: {ext})")

            # 步骤3: 分类型处理（带开关控制）
            if mime_type.startswith("image/"):
                # 图片处理（带压缩开关）
                if self.auto_compress_image and PIL_AVAILABLE:
                    base64_str = self._encode_image(file_path, mime_type)
                else:
                    # 无压缩模式：直接读取原始文件
                    with open(file_path, "rb") as f:
                        base64_str = base64.b64encode(f.read()).decode('utf-8')

                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_str}",
                        "detail": "high" if self.auto_compress_image else "low"
                    }
                })

            elif mime_type.startswith("video/"):
                if not self.auto_extract_video_frames:
                    raise ValueError(
                        f"视频处理已禁用 (auto_extract_video_frames=False)。"
                        f"如需分析视频，请启用抽帧或手动提取关键帧后作为图片传入。"
                    )

                if not OPENCV_AVAILABLE:
                    raise ImportError(
                        f"视频处理需要 OpenCV: pip install opencv-python\n"
                        f"文件: {file_path}"
                    )

                # 视频抽帧（带帧数控制）
                frames = self._extract_video_frames(file_path, max_frames=self.max_video_frames)
                temp_files_to_cleanup.extend(frames)  # 记录临时帧文件

                for i, frame_path in enumerate(frames):
                    # 帧图片处理（使用图片压缩设置）
                    if self.auto_compress_image and PIL_AVAILABLE:
                        base64_str = self._encode_image(frame_path, "image/jpeg")
                    else:
                        with open(frame_path, "rb") as f:
                            base64_str = base64.b64encode(f.read()).decode('utf-8')

                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_str}",
                            "detail": "low"  # 视频帧统一使用low detail
                        }
                    })

            else:
                raise ValueError(f"不支持的文件类型: {mime_type} ({file_path})")

        if not content:
            raise ValueError("未生成有效的内容（无文本且无有效文件）")

        return content, temp_files_to_cleanup

    def _encode_image(
            self,
            image_path: Path,
            mime_type: str
    ) -> str:
        """智能图片压缩（带开关控制）"""
        if not PIL_AVAILABLE:
            raise ImportError("Pillow未安装，无法处理图片压缩")

        try:
            img = Image.open(image_path)

            # 透明通道处理
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = background

            # 仅当启用压缩时执行缩放
            if self.auto_compress_image and max(img.size) > self.max_image_size:
                img.thumbnail((self.max_image_size, self.max_image_size), Image.Resampling.LANCZOS)

            # 优化格式（减小体积）
            buffer = io.BytesIO()
            save_format = "JPEG" if mime_type.startswith("image/jpeg") else "PNG"
            save_kwargs = {"quality": 85, "optimize": True} if save_format == "JPEG" else {}
            img.save(buffer, format=save_format, **save_kwargs)
            buffer.seek(0)

            return base64.b64encode(buffer.getvalue()).decode('utf-8')

        except Exception as e:
            raise RuntimeError(f"图片处理失败 {image_path}: {str(e)}") from e

    def _extract_video_frames(
            self,
            video_path: Path,
            max_frames: int = 3
    ) -> List[Path]:
        """智能视频抽帧（带帧数控制）"""
        if not OPENCV_AVAILABLE:
            raise ImportError("OpenCV未安装，无法处理视频")

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"无法打开视频文件: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        duration = total_frames / fps if fps > 0 else 0

        # 计算抽帧位置（均匀分布，跳过开头/结尾黑场）
        frame_indices = []
        if total_frames <= max_frames:
            frame_indices = list(range(total_frames))
        else:
            # 跳过前5%和后5%（通常为黑场/片头片尾）
            start_idx = int(total_frames * 0.05)
            end_idx = int(total_frames * 0.95)
            usable_frames = end_idx - start_idx

            if usable_frames <= max_frames:
                frame_indices = list(range(start_idx, end_idx))
            else:
                step = usable_frames / (max_frames + 1)
                frame_indices = [
                    start_idx + int(i * step)
                    for i in range(1, max_frames + 1)
                ]

        # 提取帧
        temp_frames = []
        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                # 转换为RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # 保存为临时文件
                temp_path = self.temp_download_dir / f"frame_{hash(video_path)}_{idx}_{int(time.time())}.jpg"
                cv2.imwrite(str(temp_path), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
                temp_frames.append(temp_path)

        cap.release()
        return temp_frames

    # ==================== 聊天模型功能 ===================
    def _get_chat_client(
            self,
            api_key: Optional[str] = None,
            base_url: Optional[str] = None,
            use_ollama: Optional[bool] = None,
            timeout: Optional[float] = None,
    ) -> OpenAI:
        """根据参数动态创建或获取缓存的OpenAI客户端"""
        # 确定实际使用的参数值（调用参数 > 初始化参数 > 默认值）
        use_ollama_actual = use_ollama if use_ollama is not None else self.use_ollama
        timeout_actual = timeout if timeout is not None else self.timeout

        if use_ollama_actual:
            base_url_actual = base_url or "http://localhost:11434/v1"
            api_key_actual = api_key or "ollama"
        else:
            base_url_actual = base_url or self.base_url or "https://api.openai.com/v1"
            api_key_actual = api_key or self.api_key
            if not api_key_actual:
                raise ValueError("OpenAI 模式需要提供 api_key")

        # 生成缓存键
        cache_key = (api_key_actual, base_url_actual, timeout_actual)

        # 检查缓存
        if cache_key in self._client_cache:
            return self._client_cache[cache_key]

        # 创建新客户端
        client = OpenAI(
            api_key=api_key_actual,
            base_url=base_url_actual,
            timeout=timeout_actual
        )

        # 缓存客户端（避免高频调用重复创建）
        self._client_cache[cache_key] = client
        return client

    def model_chat(
            self,
            system_prompt: str=None,
            user_prompt: str=None,
            files: Optional[List[str]] = None,
            temperature: float = 0.6,
            model: Optional[str] = None,
            stream: bool = False,
            to_json: bool = False,
            max_tokens: Optional[int] = None,
            top_p: Optional[float] = None,
            json_schema: Optional[Dict[str, Any]] = None,
            auto_compress_image: Optional[bool] = None,
            auto_extract_video_frames: Optional[bool] = None,
            api_key: Optional[str] = None,
            base_url: Optional[str] = None,
            use_ollama: Optional[bool] = None,
            timeout: Optional[float] = None,
    ) -> Union[str, Dict[str, Any], Generator[str, None, None]]:
        """
        增强版聊天方法：支持多模态文件输入

        Args:
            files: 文件路径列表（支持图片/视频）
                - 图片: .jpg/.jpeg/.png/.gif/.bmp/.webp
                - 视频: .mp4/.avi/.mov/.mkv（自动抽关键帧）
            auto_compress_image: 覆盖初始化设置（True/False/None=使用初始化值）
            auto_extract_video_frames: 覆盖视频抽帧设置
            其他参数同原有方法
        """
        # 保存原始设置（用于恢复）
        original_compress = self.auto_compress_image
        original_extract = self.auto_extract_video_frames
        if system_prompt is None:
            system_prompt = ""
        if user_prompt is None:
            user_prompt = ""
        try:
            if base_url is None and use_ollama:
                base_url = "http://localhost:11434/v1"
                api_key = api_key or "ollama"

            # 应用覆盖参数
            if auto_compress_image is not None:
                self.auto_compress_image = auto_compress_image
            if auto_extract_video_frames is not None:
                self.auto_extract_video_frames = auto_extract_video_frames
            # 获取客户端（根据覆盖参数或初始化配置）
            client = self._get_chat_client(
                api_key=api_key,
                base_url=base_url,
                use_ollama=use_ollama,
                timeout=timeout
            )

            # 确定实际使用的模型
            model_actual = model or self.chat_model
            if not model_actual:
                raise ValueError("必须指定聊天模型名称")

            # 处理多模态输入
            content, temp_files = self._process_files_for_vision(files or [], user_prompt)

            # 构建增强系统提示
            messages = [
                {"role": "system", "content": self._build_system_prompt(system_prompt, to_json, json_schema)},
                {"role": "user", "content": content}
            ]

            extra_params = {}
            if max_tokens is not None:
                extra_params["max_tokens"] = max_tokens
            if top_p is not None:
                extra_params["top_p"] = top_p

            # OpenAI专属JSON模式
            if to_json and not (use_ollama if use_ollama is not None else self.use_ollama):
                if json_schema:
                    extra_params["response_format"] = {"type": "json_object", "schema": json_schema}
                else:
                    extra_params["response_format"] = {"type": "json_object"}

            try:
                response = client.chat.completions.create(
                    model=model_actual,
                    messages=messages,
                    temperature=temperature,
                    stream=stream,
                    **extra_params
                )
            except OpenAIError as e:
                # 增强错误提示（多模态相关）
                if "image" in str(e).lower() or "vision" in str(e).lower():
                    raise RuntimeError(
                        f"多模态请求失败: {str(e)}\n"
                        f"可能原因:\n"
                        f"  1. 模型不支持视觉 ({model_actual})\n"
                        f"  2. auto_compress_image={self.auto_compress_image} 导致图片过大\n"
                        f"  3. auto_extract_video_frames={self.auto_extract_video_frames} 且传入了视频"
                    ) from e
                raise RuntimeError(f"API 调用失败: {str(e)}") from e

            if stream:
                def stream_with_cleanup():
                    try:
                        for chunk in self._stream_handler(response, to_json):
                            yield chunk
                    finally:
                        self._cleanup_temp_files()
                        # 清理本次调用的临时帧文件
                        for f in temp_files:
                            f.unlink(missing_ok=True)

                return stream_with_cleanup()
            else:
                full_content = response.choices[0].message.content.strip()
                result = self._parse_json_response(full_content) if to_json else full_content

                # 非流式：立即清理临时文件
                self._cleanup_temp_files()
                for f in temp_files:
                    f.unlink(missing_ok=True)

                return result
        finally:
            # 恢复原始设置
            self.auto_compress_image = original_compress
            self.auto_extract_video_frames = original_extract

    def model_chat_json(
            self,
            system_prompt: str=None,
            user_prompt: str=None,
            files: Optional[List[str]] = None,
            model: Optional[str] = None,
            api_key: Optional[str] = None,
            base_url: Optional[str] = None,
            use_ollama: Optional[bool] = None,
            timeout: Optional[float] = None,
            **kwargs
    ) -> Dict[str, Any]:
        """专用JSON接口：强制返回并解析JSON（支持动态指定API配置）"""
        kwargs.pop("to_json", None)  # 确保强制JSON模式
        return self.model_chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            files=files,
            to_json=True,
            model=model,
            temperature=kwargs.pop("temperature", 0.3),
            max_tokens=kwargs.pop("max_tokens", 2048),
            api_key=api_key,
            base_url=base_url,
            use_ollama=use_ollama,
            timeout=timeout,
            **kwargs
        )

    def _build_system_prompt(
            self,
            base_prompt: str,
            require_json: bool,
            json_schema: Optional[Dict[str, Any]] = None
    ) -> str:
        """构建增强版系统提示词"""
        if not require_json:
            return base_prompt

        json_instruction = (
            "\n\n[重要] 请严格以纯 JSON 格式返回结果，不要包含任何额外文本、"
            "Markdown 标记或说明。只输出 JSON 对象。"
        )
        if json_schema:
            schema_str = json.dumps(json_schema, ensure_ascii=False, indent=2)
            json_instruction += f"\n\nJSON Schema 要求:\n{schema_str}"

        return base_prompt + json_instruction

    def _stream_handler(
            self,
            response: Any,
            to_json: bool
    ) -> Generator[str, None, None]:
        """流式响应处理器"""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
        if to_json:
            yield "\n[注意：流式模式下 JSON 需由调用方拼接完整后手动解析]"

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """智能解析JSON响应（含修复机制与脏字符清洗）"""

        # --- 步骤 0: 核心修复 (清洗隐形字符) ---
        content = content.replace('\xa0', ' ')  # 不间断空格
        content = content.replace('\u3000', ' ')  # 全角空格
        content = content.strip()

        # --- 尝试 1: 直接解析 ---
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # --- 尝试 2: 提取 Markdown 代码块 ---
        pattern = r"```(?:json|JSON)?\s*(.*?)\s*```"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            code_content = match.group(1)
            try:
                return json.loads(code_content)
            except json.JSONDecodeError:
                pass

        # --- 尝试 3: 暴力提取首尾花括号 ---
        match = re.search(r'(\{[\s\S]*})', content)
        if match:
            json_str = match.group(1)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        raise ValueError(
            f"❌ 无法解析 JSON 响应。可能原因：格式错误或包含非法字符。\n原始内容片段:\n{content[:300]}..."
        )

    # ==================== 重排模型功能 ====================

    def load_reranker(
            self,
            model_name: str = "Qwen/Qwen3-Reranker-0.6B",
            use_flash_attention: bool = False
    ):
        """加载重排模型（懒加载）"""
        if self.reranker_model is not None:
            return

        if AutoModelForCausalLM is None:
            raise ImportError(
                "缺少 modelscope 库。请安装：pip install modelscope transformers>=4.51.0"
            )

        self.reranker_tokenizer = AutoTokenizer.from_pretrained(
            model_name, padding_side='left'
        )

        model_kwargs = {"pretrained_model_name_or_path": model_name}
        if use_flash_attention:
            model_kwargs.update({
                "torch_dtype": torch.float16,
                "attn_implementation": "flash_attention_2"
            })
            if self.reranker_device != "cpu":
                model_kwargs["device_map"] = self.reranker_device

        self.reranker_model = AutoModelForCausalLM.from_pretrained(**model_kwargs).eval()
        if not use_flash_attention and self.reranker_device != "cpu":
            self.reranker_model.to(self.reranker_device)

        # 预计算特殊token和模板
        self._token_false_id = self.reranker_tokenizer.convert_tokens_to_ids("no")
        self._token_true_id = self.reranker_tokenizer.convert_tokens_to_ids("yes")

        prefix = '</think>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".\n</tool_call>user\n'
        suffix = '\n<think>assistant\n<think>\n\n</think>\n\n'
        self._reranker_prefix = self.reranker_tokenizer.encode(prefix, add_special_tokens=False)
        self._reranker_suffix = self.reranker_tokenizer.encode(suffix, add_special_tokens=False)

    def _format_rerank_instruction(
            self,
            instruction: Optional[str],
            query: str,
            document: str
    ) -> str:
        """格式化重排输入"""
        if instruction is None:
            instruction = 'Given a web search query, retrieve relevant passages that answer the query'
        return f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {document}"

    def _process_rerank_inputs(self, pairs: List[str]) -> Dict[str, torch.Tensor]:
        """处理重排输入"""
        inputs = self.reranker_tokenizer(
            pairs,
            padding=False,
            truncation='longest_first',
            return_attention_mask=False,
            max_length=self.max_length - len(self._reranker_prefix) - len(self._reranker_suffix)
        )

        for i in range(len(inputs['input_ids'])):
            inputs['input_ids'][i] = (
                    self._reranker_prefix + inputs['input_ids'][i] + self._reranker_suffix
            )

        inputs = self.reranker_tokenizer.pad(
            inputs,
            padding=True,
            return_tensors="pt",
            max_length=self.max_length
        )
        return {k: v.to(self.reranker_model.device) for k, v in inputs.items()}

    @torch.no_grad()
    def model_rerank(
            self,
            queries: List[str],
            documents: List[str],
            task: Optional[str] = None,
            use_flash_attention: bool = False
    ) -> List[float]:
        """
        计算查询与文档的相关性分数

        Args:
            queries: 查询列表
            documents: 文档列表（需与queries一一对应）
            task: 重排任务描述
            use_flash_attention: 是否使用FlashAttention-2

        Returns:
            相关性分数列表 [0.0, 1.0]
        """
        if len(queries) != len(documents):
            raise ValueError("queries和documents长度必须相同")

        if self.reranker_model is None:
            self.load_reranker(use_flash_attention=use_flash_attention, model_name=self.rerank_model_dir)

        pairs = [
            self._format_rerank_instruction(task, q, d)
            for q, d in zip(queries, documents)
        ]

        inputs = self._process_rerank_inputs(pairs)
        logits = self.reranker_model(**inputs).logits[:, -1, :]

        true_scores = logits[:, self._token_true_id]
        false_scores = logits[:, self._token_false_id]
        combined = torch.stack([false_scores, true_scores], dim=1)
        probs = torch.nn.functional.log_softmax(combined, dim=1)[:, 1].exp()

        return probs.cpu().tolist()

    # ==================== 向量化模型功能 ====================

    def load_embedding(
            self,
            model_name: str = "Qwen/Qwen3-Embedding-0.6B",
            use_flash_attention: bool = False
    ):
        """加载向量化模型（懒加载）"""
        if self.embedding_model is not None:
            return

        if AutoModel is None:
            raise ImportError(
                "缺少 modelscope 库。请安装：pip install modelscope transformers>=4.51.0"
            )

        self.embedding_tokenizer = AutoTokenizer.from_pretrained(
            model_name, padding_side='left'
        )

        model_kwargs = {"pretrained_model_name_or_path": model_name}
        if use_flash_attention:
            model_kwargs.update({
                "torch_dtype": torch.float16,
                "attn_implementation": "flash_attention_2"
            })
            if self.embedding_device != "cpu":
                model_kwargs["device_map"] = self.embedding_device

        self.embedding_model = AutoModel.from_pretrained(**model_kwargs)
        if not use_flash_attention and self.embedding_device != "cpu":
            self.embedding_model.to(self.embedding_device)
        self.embedding_model.eval()

    def _last_token_pool(
            self,
            last_hidden_states: Tensor,
            attention_mask: Tensor
    ) -> Tensor:
        """获取最后一个有效token的表示"""
        left_padding = (attention_mask[:, -1].sum() == attention_mask.shape[0])
        if left_padding:
            return last_hidden_states[:, -1]
        else:
            sequence_lengths = attention_mask.sum(dim=1) - 1
            batch_size = last_hidden_states.shape[0]
            return last_hidden_states[
                torch.arange(batch_size, device=last_hidden_states.device),
                sequence_lengths
            ]

    def model_embed(
            self,
            texts: List[str],
            task: Optional[str] = None,
            normalize: bool = True,
            use_flash_attention: bool = False
    ) -> torch.Tensor:
        """
        生成文本的嵌入向量

        Args:
            texts: 文本列表
            task: 任务描述（仅用于查询，文档不需要）
            normalize: 是否归一化向量
            use_flash_attention: 是否使用FlashAttention-2

        Returns:
            归一化的嵌入向量张量 [batch_size, hidden_size]
        """
        if self.embedding_model is None:
            self.load_embedding(use_flash_attention=use_flash_attention, model_name=self.embedding_model_dir)

        # 为查询添加任务指令（仅当提供task时）
        if task:
            texts = [f"Instruct: {task}\nQuery: {text}" for text in texts]

        batch_dict = self.embedding_tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt"
        ).to(self.embedding_model.device)

        with torch.no_grad():
            outputs = self.embedding_model(**batch_dict)
            embeddings = self._last_token_pool(
                outputs.last_hidden_state,
                batch_dict['attention_mask']
            )

        if normalize:
            embeddings = F.normalize(embeddings, p=2, dim=1)

        return embeddings.cpu()

    def compute_similarity(
            self,
            queries: List[str],
            documents: List[str],
            task: Optional[str] = None,
            use_flash_attention: bool = False
    ) -> List[List[float]]:
        """
        计算查询与文档的相似度矩阵

        Args:
            queries: 查询列表
            documents: 文档列表
            task: 任务描述
            use_flash_attention: 是否使用FlashAttention-2

        Returns:
            相似度矩阵 [[q1-d1, q1-d2, ...], [q2-d1, q2-d2, ...]]
        """
        query_embeddings = self.model_embed(queries, task=task, use_flash_attention=use_flash_attention)
        doc_embeddings = self.model_embed(documents, use_flash_attention=use_flash_attention)
        similarity = (query_embeddings @ doc_embeddings.T).tolist()
        return similarity

    def describe_image(
            self,
            image_path: str,
            detail_level: str = "high",
            auto_compress: Optional[bool] = None,
            **kwargs
    ) -> str:
        """图片描述（支持压缩控制）"""
        return self.model_chat(
            system_prompt="你是一个专业的视觉助手，请详细描述图片内容",
            user_prompt="描述这张图片",
            files=[image_path],
            auto_compress_image=auto_compress if auto_compress is not None else self.auto_compress_image,
            **kwargs
        )

    def analyze_video(
            self,
            video_path: str,
            task: str = "总结视频内容",
            max_frames: Optional[int] = None,
            auto_extract: Optional[bool] = None,
            **kwargs
    ) -> str:
        """视频分析（支持抽帧控制）"""
        # 临时覆盖抽帧设置
        original_max = self.max_video_frames
        try:
            if max_frames:
                self.max_video_frames = max_frames

            return self.model_chat(
                system_prompt="你是一个视频分析专家，请基于关键帧分析视频内容",
                user_prompt=task,
                files=[video_path],
                auto_extract_video_frames=auto_extract if auto_extract is not None else self.auto_extract_video_frames,
                **kwargs
            )
        finally:
            if max_frames:
                self.max_video_frames = original_max


if __name__ == "__main__":
    # 初始化（项目级临时目录）
    model = LLModel(
        chat_model="qwen3vl-2b",
        use_ollama=True,
        auto_compress_image=False,  # 启用图片压缩
        max_image_size=1024,
        auto_extract_video_frames=False,  # 启用视频抽帧
        max_video_frames=3,
        temp_download_dir=None,  # 自动定位项目目录
        cleanup_downloaded_files=True  # 自动清理下载文件
    )

    print(f"📁 临时下载目录: {model.temp_download_dir}")

    # 示例1: 本地图片（启用压缩）
    print("\n📸 本地图片识别（自动压缩）:")
    try:
        result = model.model_chat(
            system_prompt="描述图片内容",
            files=[r"E:\ai绘画\bananna焚诀\Gemini_Generated_Image_dp5p9ydp5p9ydp5p.png"],
            auto_compress_image=False  # 显式启用（默认）
        )
        print(result)
    except Exception as e:
        print(f"❌ 失败: {e}")
