import os
from pathlib import Path
import json
import inspect
import pickle
import hashlib
import sys
import re
import torch
import importlib
import importlib.util
import numpy as np
from typing import Callable, Dict, Any, List, Type, get_type_hints
from pydantic import BaseModel, create_model, Field
from modelscope import AutoTokenizer, AutoModel
from openai import OpenAI


# ==========================================
# 1. 向量模型引擎 (基于 MiniLM-L12)
# ==========================================

class EmbeddingEngine:
    def __init__(self, model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'):
        print(f"🔄 [System] Loading embedding model: {model_name}...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device)
        print("✅ [System] Model loaded.")

    def _mean_pooling(self, model_output, attention_mask):
        """你提供的 Pooling 方法"""
        token_embeddings = model_output[0]
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

    def encode(self, texts: List[str]) -> np.ndarray:
        """将文本列表转换为向量"""
        # Tokenize
        encoded_input = self.tokenizer(texts, padding=True, truncation=True, return_tensors='pt').to(self.device)

        # Compute embeddings
        with torch.no_grad():
            model_output = self.model(**encoded_input)

        # Pooling
        sentence_embeddings = self._mean_pooling(model_output, encoded_input['attention_mask'])

        # Normalize embeddings (for cosine similarity)
        sentence_embeddings = torch.nn.functional.normalize(sentence_embeddings, p=2, dim=1)
        return sentence_embeddings.cpu().numpy()


# ==========================================
# 2. 增强版工具注册器
# ==========================================

class SmartToolRegistry:
    def __init__(self, use_vector_search=True,
                 embedding_model_dir="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                 cache_path="./tool_embeddings_cache.pkl",
                 registry_json_path="./tool_registry.json"):

        self._tools: Dict[str, Dict[str, Any]] = {}
        self.tool_embeddings = None
        self.tool_names_index = []
        self.embedding_model_dir = embedding_model_dir

        self.use_vector_search = use_vector_search
        self.cache_path = cache_path
        self.registry_json_path = registry_json_path  # <--- 保存 JSON 路径

        # 1. 加载向量缓存
        self.cache_data = self._load_cache()

        # 2. 加载工具注册表 (JSON) 并恢复函数
        self._load_registry_from_json()

        self._embedding_engine_instance = None

    @property
    def embedding_engine(self):
        """懒加载：只有缓存未命中时才加载大模型，极大提升启动速度"""
        if self._embedding_engine_instance is None:
            self._embedding_engine_instance = EmbeddingEngine(self.embedding_model_dir)
        return self._embedding_engine_instance

    def _load_cache(self) -> Dict:
        """从磁盘加载缓存"""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "rb") as f:
                    data = pickle.load(f)
                    print(f"💾 [System] Cache loaded from {self.cache_path} ({len(data)} tools)")
                    return data
            except Exception as e:
                print(f"⚠️ [System] Failed to load cache: {e}")
        return {}

    def save_cache(self):
        """手动保存缓存到磁盘"""
        if self.use_vector_search:
            try:
                with open(self.cache_path, "wb") as f:
                    pickle.dump(self.cache_data, f)
                print(f"💾 [System] Cache saved to {self.cache_path}")
            except Exception as e:
                print(f"⚠️ [System] Failed to save cache: {e}")

    def _get_func_file_path(self, func: Callable) -> str:
        """获取函数所在的绝对文件路径"""
        try:
            # 获取源文件路径
            file_path = inspect.getfile(func)
            # 转为绝对路径
            return os.path.abspath(file_path)
        except Exception:
            # 可能是内置函数或动态生成的函数，无法获取文件
            return ""

    def _save_registry_to_json(self):
        """将当前工具的元数据保存到 JSON 文件"""
        registry_data = {}
        for name, info in self._tools.items():
            func = info["func"]
            registry_data[name] = {
                "module": func.__module__,
                "func_name": func.__name__,
                "file_path": self._get_func_file_path(func),  # <--- 新增：保存绝对路径
                "description": info["description"],
                "enabled": info.get("enabled", True),
            }

        try:
            with open(self.registry_json_path, "w", encoding="utf-8") as f:
                json.dump(registry_data, f, indent=4, ensure_ascii=False)
            print(f"📄 [Registry] Metadata saved to {self.registry_json_path}")
        except Exception as e:
            print(f"⚠️ [Registry] Failed to save JSON: {e}")

    def _load_module_from_path(self, name: str, file_path: str):
        """核心魔法：根据文件路径动态加载模块"""
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"Source file not found: {file_path}")

        # 生成一个唯一的模块名，避免冲突
        # 例如: dynamic_tool_bing_search
        module_spec_name = f"dynamic_tool_{name}"

        try:
            # 1. 创建 Spec
            spec = importlib.util.spec_from_file_location(module_spec_name, file_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not create spec from {file_path}")

            # 2. 创建 Module
            module = importlib.util.module_from_spec(spec)

            # 3. 将模块加入 sys.modules (可选，但推荐，方便模块内部的相对引用)
            sys.modules[module_spec_name] = module

            # 4. 执行模块代码
            spec.loader.exec_module(module)

            return module
        except Exception as e:
            raise ImportError(f"Failed to load module from path: {e}")

    def _load_registry_from_json(self):
        """启动时从 JSON 加载工具并动态导入函数,加载逻辑：优先 import，失败则降级为文件路径加"""
        if not os.path.exists(self.registry_json_path):
            return

        print(f"📂 [Registry] Loading metadata from {self.registry_json_path}...")
        try:
            with open(self.registry_json_path, "r", encoding="utf-8") as f:
                registry_data = json.load(f)

            loaded_count = 0
            for name, meta in registry_data.items():
                module_path = meta.get("module")
                func_name = meta.get("func_name")
                file_path = meta.get("file_path")  # 读取路径
                description = meta.get("description")
                enabled = meta.get("enabled", True)

                func = None

                # 策略 1: 尝试标准 import (只要不是 __main__)
                if module_path and module_path != "__main__":
                    try:
                        mod = importlib.import_module(module_path)
                        func = getattr(mod, func_name)
                    except (ImportError, AttributeError):
                        print(f"   ⚠️ Standard import failed for '{name}', trying file path...")

                # 策略 2: 如果策略1失败 或 模块是 __main__，尝试通过绝对路径加载
                if func is None and file_path:
                    try:
                        mod = self._load_module_from_path(name, file_path)
                        func = getattr(mod, func_name)
                    except Exception as e:
                        print(f"   ❌ File load failed for '{name}': {e}")

                # 如果找到了函数，注册它
                if func:
                    # 使用 _skip_save_json 避免死循环保存
                    self.add_tool(func, name=name, description=description, _skip_save_json=True)
                    self._tools[name]["enabled"] = enabled
                    loaded_count += 1
                else:
                    print(f"   ❌ Could not restore tool '{name}' (Module: {module_path}, Path: {file_path})")

            print(f"✅ [Registry] Restored {loaded_count} tools.")

        except Exception as e:
            print(f"⚠️ [Registry] Error reading JSON registry: {e}")

    def _get_text_hash(self, text: str) -> str:
        """计算文本指纹，用于检测描述是否修改"""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def _parse_function_docstring(self, func: Callable) -> Dict[str, str]:
        """
        解析函数文档字符串，提取参数描述。
        支持格式:
        1. :param name: description (ReST/Sphinx 风格)
        2. Args: name: description (Google 风格 - 简化版)
        """
        doc = func.__doc__
        if not doc:
            return {}

        param_docs = {}

        # 1. 匹配 :param name: description
        # 正则含义：:param + 空格 + 变量名 + 冒号 + 任意空白 + 描述内容(直到换行或下一个tag)
        pattern_param = re.compile(r':param\s+(\w+):\s*(.*?)(?=(?:\n\s*:param)|(?:\n\s*:return)|$)', re.DOTALL)
        matches = pattern_param.findall(doc)
        for name, desc in matches:
            param_docs[name] = desc.strip().replace('\n', ' ')

        # 如果没有匹配到标准 param，可以尝试简单的 Google Style (Args: name (type): desc)
        # 这里为了稳定性，先主要支持标准 :param 格式，大部分 IDE 生成注释都是这种

        return param_docs

    def _func_to_pydantic_model(self, func: Callable) -> Type[BaseModel]:
        """
        核心魔法：利用 inspect, type hints 和 Docstring 自动生成带描述的 Pydantic 模型
        """
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)

        # 🔥 获取文档中的参数描述
        param_descriptions = self._parse_function_docstring(func)

        fields = {}

        for param_name, param in sig.parameters.items():
            # 跳过 self/cls
            if param_name in ('self', 'cls'):
                continue

            # 1. 获取类型，默认为 Any
            annotation = type_hints.get(param_name, Any)

            # 2. 获取默认值
            default_value = ...
            if param.default != inspect.Parameter.empty:
                default_value = param.default

            # 3. 获取描述 (从 docstring 中提取，如果没有则为空)
            description = param_descriptions.get(param_name, f"Parameter {param_name}")

            # 4. 构建 Field
            # 使用 Field(description=...) 让 Schema 包含描述
            fields[param_name] = (annotation, Field(default_value, description=description))

        # 动态创建 Pydantic 模型类
        model_name = f"{func.__name__}Args"
        try:
            return create_model(model_name, **fields)
        except Exception as e:
            # 容错处理：如果类型太复杂无法生成模型，降级处理
            print(f"⚠️ Failed to create Pydantic model for {func.__name__}: {e}")
            return create_model(model_name)

    def add_tool(self, func: Callable, name: str = None, description: str = None, _skip_save_json: bool = False):
        """
        显式添加工具，支持动态加载的函数。
        :param func: 目标函数对象
        :param name: 工具名称（缺省则使用函数名）
        :param description: 工具描述（缺省则尝试读取函数 docstring）
        """
        name = name or func.__name__
        description = description or func.__doc__ or "No description provided."

        args_model = self._func_to_pydantic_model(func)
        schema_raw = args_model.model_json_schema()

        parameters = {
            "type": "object",
            "properties": schema_raw.get("properties", {}),
            "required": schema_raw.get("required", [])
        }

        tool_def = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters
            }
        }

        self._tools[name] = {
            "func": func,
            "schema": tool_def,
            "args_model": args_model,
            "description": description,
            "enabled": True
        }

        # 向量化更新
        if self.use_vector_search:
            self._update_embedding_safe(name, description)

        # 保存到 JSON
        if not _skip_save_json:
            self._save_registry_to_json()
            if self.use_vector_search:
                self.save_cache()
            print(f"🚀 [Registry] Added & Saved: {name}")

        return func

    def register_from_module(self, module):
        """
        从给定的模块中自动注册所有函数。
        通常可以配合自定义属性过滤，例如只注册有 docstring 的函数。
        """
        import types
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            # 过滤：必须是函数，且不是内置/私有方法
            if isinstance(attr, types.FunctionType) and not attr_name.startswith("_"):
                # 如果函数没有 docstring，在实际生产中可以跳过或报错
                if attr.__doc__:
                    self.add_tool(attr)

    def register_from_config(self, func_map: Dict[str, Callable], config_path: str):
        """
        func_map: {"get_weather": get_weather_func_object}
        config_path: 包含描述信息的 JSON/YAML 文件
        """
        with open(config_path, 'r', encoding='utf-8') as f:
            descriptions = json.load(f)  # 格式: {"get_weather": "查询天气..."}

        for name, func in func_map.items():
            desc = descriptions.get(name)
            if desc:
                self.add_tool(func, name=name, description=desc)

    def register(self, name: str, description: str):
        return self._register_impl(name, description)

    def _register_impl(self, name, description):
        def decorator(func):
            # 直接调用 add_tool，复用里面的逻辑（包括保存 JSON）
            self.add_tool(func, name=name, description=description)
            return func

        return decorator

    def _update_embedding_safe(self, name: str, description: str):
        """智能更新向量：优先读缓存"""
        text_to_embed = f"{name}: {description}"
        current_hash = self._get_text_hash(text_to_embed)

        vector = None

        # 1. 检查缓存：名字存在 且 描述Hash一致
        if name in self.cache_data:
            cached_item = self.cache_data[name]
            if cached_item["hash"] == current_hash:
                print(f"⚡ [Cache] Hit for '{name}'")
                vector = cached_item["vector"]
            else:
                print(f"🔄 [Update] Description changed for '{name}', re-calculating...")

        # 2. 如果没有向量（缓存未命中），则计算
        if vector is None:
            # 此时才触发 EmbeddingEngine (如果还没加载，会在这里加载)
            vector = self.embedding_engine.encode([text_to_embed])
            # 更新缓存字典
            self.cache_data[name] = {
                "vector": vector,
                "hash": current_hash
            }

        # 3. 更新运行时的 Numpy 矩阵 (用于搜索)
        if self.tool_embeddings is None:
            self.tool_embeddings = vector
        else:
            self.tool_embeddings = np.vstack([self.tool_embeddings, vector])

        self.tool_names_index.append(name)

    def _update_embedding(self, name: str, description: str):
        """将新注册的工具加入向量索引"""
        # 构造用于嵌入的文本，通常 "名称: 描述" 的效果比纯描述好
        text_to_embed = f"{name}: {description}"
        vector = self.embedding_engine.encode([text_to_embed])

        if self.tool_embeddings is None:
            self.tool_embeddings = vector
        else:
            self.tool_embeddings = np.vstack([self.tool_embeddings, vector])

        self.tool_names_index.append(name)

    def soft_delete(self, tool_name: str):
        """
        [软删除] 禁用工具。
        工具保留在内存和缓存中，但在 get_tools 搜索时会被忽略。
        """
        if tool_name in self._tools:
            self._tools[tool_name]["enabled"] = False
            print(f"🚫 [System] Tool '{tool_name}' soft deleted.")
            self._save_registry_to_json()  # 更新 JSON 状态
        else:
            print(f"⚠️ [System] Tool '{tool_name}' not found.")

    def recover(self, tool_name: str):
        """
        [恢复] 重新启用被软删除的工具。
        """
        if tool_name in self._tools:
            self._tools[tool_name]["enabled"] = True
            print(f"✅ [System] Tool '{tool_name}' recovered.")
            self._save_registry_to_json()  # 更新 JSON 状态
        else:
            print(f"⚠️ [System] Tool '{tool_name}' not found.")

    def hard_delete(self, tool_name: str, save_immediately: bool = True):
        """
        [硬删除] 彻底移除工具。
        1. 从运行时注册表中移除。
        2. 从向量索引 (Numpy Array) 中物理移除。
        3. 从磁盘缓存数据中移除。
        """
        # 1. 运行时移除
        if tool_name in self._tools:
            del self._tools[tool_name]
            print(f"🗑️ [Runtime] Removed '{tool_name}'")

        # 2. 缓存移除
        if tool_name in self.cache_data:
            del self.cache_data[tool_name]

        # 3. 向量索引移除
        if tool_name in self.tool_names_index:
            try:
                idx = self.tool_names_index.index(tool_name)
                self.tool_names_index.pop(idx)
                if self.tool_embeddings is not None:
                    self.tool_embeddings = np.delete(self.tool_embeddings, idx, axis=0)
                    if self.tool_embeddings.shape[0] == 0:
                        self.tool_embeddings = None
            except ValueError:
                pass

        # 4. 保存更改
        if save_immediately:
            self.save_cache()  # 保存 pickle
            self._save_registry_to_json()  # 保存 JSON

    def clean_zombies(self):
        """
        [工具] 清理僵尸缓存。
        如果在 cache_data (pkl) 中存在，但在代码中没有通过 @register 注册的工具，将被硬删除。
        用于代码移除后清理 pkl 文件。
        """
        # 注意：cache_data 包含了历史所有工具，self._tools 只包含当前运行代码注册的工具
        cached_names = list(self.cache_data.keys())
        active_names = set(self._tools.keys())

        zombie_count = 0
        for name in cached_names:
            if name not in active_names:
                # 这是一个僵尸工具（pkl里有，代码里没了）
                del self.cache_data[name]
                # 注意：因为没有注册，它不会出现在 self.tool_names_index 中，
                # 所以不需要处理 vector index，只需要处理 cache_data
                zombie_count += 1
                print(f"💀 [Zombie] Cleaning dead tool '{name}' from cache.")

        if zombie_count > 0:
            self.save_cache()
            print(f"🧹 Cleaned {zombie_count} zombie tools.")
        else:
            print("✨ Cache is clean.")

    def get_tools(self, query: str = None, top_k: int = 3) -> List[Dict]:
        """
        获取工具 Schema。
        如果提供了 query，则使用向量相似度返回 Top K 最相关的工具。
        """
        if not query or not self.use_vector_search or self.tool_embeddings is None:
            # 如果没有 query 或没启用向量，返回所有工具
            return [t["schema"] for t in self._tools.values()]

        print(f"🔍 [Search] Semantic search for: '{query}'")

        # 1. 向量化 Query
        query_vec = self.embedding_engine.encode([query])  # Shape (1, 384)

        # 2. 计算余弦相似度 (Dot product works because vectors are normalized)
        # (1, 384) @ (N, 384).T -> (1, N)
        scores = np.dot(query_vec, self.tool_embeddings.T)[0]

        # 3. 获取 Top K 索引
        # argsort 返回从小到大的索引，所以取最后 k 个并反转
        top_indices = np.argsort(scores)[-top_k:][::-1]

        relevant_tools = []
        for idx in top_indices:
            tool_name = self.tool_names_index[idx]

            tool_obj = self._tools.get(tool_name)
            if not tool_obj:
                continue  # 防御性编程，防止索引错乱

            if not tool_obj.get("enabled", True):
                print(f"   🚫 Ignored soft-deleted match: {tool_name}")
                continue

            score = scores[idx]

            if score < 0.3:
                continue
            relevant_tools.append(tool_obj["schema"])

        return relevant_tools

    def call_tool(self, tool_name: str, tool_args: str | dict) -> Any:
        """
        执行工具，支持参数校验和错误回显。
        """
        if tool_name not in self._tools:
            return f"❌ Error: Tool '{tool_name}' not found."

        tool_info = self._tools[tool_name]
        func = tool_info["func"]
        args_model = tool_info["args_model"]

        try:
            # 1. 统一参数格式为 Dict
            if isinstance(tool_args, str):
                # 尝试清洗常见的 JSON 格式错误（如 markdown 代码块）
                clean_args = tool_args.strip()
                if clean_args.startswith("```json"):
                    clean_args = clean_args[7:-3].strip()
                elif clean_args.startswith("```"):
                    clean_args = clean_args[3:-3].strip()

                try:
                    args_dict = json.loads(clean_args)
                except json.JSONDecodeError:
                    return f"❌ Error: Invalid JSON format in arguments: {tool_args}"
            else:
                args_dict = tool_args

            # 2. Pydantic 校验 (这是关键步骤)
            # 如果参数名对不上，或者类型不对，这里会直接抛出 ValidationError
            validated_args = args_model(**args_dict)

            # 3. 执行函数
            # model_dump() 会返回清洗后的字典
            print(f"🔧 [Exec] Calling '{tool_name}' with: {validated_args.model_dump()}")
            result = func(**validated_args.model_dump())

            return result

        except Exception as e:
            # 捕获参数校验错误，返回给 LLM 让其重试
            error_msg = f"❌ Error executing '{tool_name}': {str(e)}"
            print(error_msg)
            return error_msg


# ==========================================
# 1. 定义意图拆解的输出结构
# ==========================================
class SearchQueries(BaseModel):
    queries: List[str] = Field(
        description="拆解并重写后的搜索关键词列表，用于在工具库中检索。每个关键词应简短、精确，匹配工具的功能描述。"
    )


# ==========================================
# 2. 意图拆解处理器 (Query Pre-processor)
# ==========================================
class IntentProcessor:
    def __init__(self, llm_client: OpenAI, model_name: str = "gpt-3.5-turbo"):
        self.client = llm_client
        self.model_name = model_name

    def decompose(self, user_input: str,
                  model: str = "qwen3-max",
                  base_url: str = None,
                  api_key: str = None
                  ) -> List[str]:
        """
        使用 LLM 将自然语言拆解为“工具搜索关键词”
        """
        system_prompt = """
        你是一个Agent系统的意图路由器。你的任务是将用户的输入拆解为独立的子任务，
        并将每个子任务转化为**针对API工具描述的搜索关键词**。

        原则：
        1. 去除口语化表达（如"帮我"、"我想知道"、"比如"）。
        2. 如果包含多个任务（如"查天气并算数"），拆分为多个关键词。
        3. 关键词应贴近技术文档或函数描述（例如："需不需要带伞" -> "查询天气 降雨概率"）。
        """
        decompose_client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )

        try:
            # 使用 Function Calling 或 JSON Mode 强制输出结构
            completion = decompose_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                tools=[{
                    "type": "function",
                    "function": {
                        "name": "generate_search_queries",
                        "description": "生成搜索关键词",
                        "parameters": SearchQueries.model_json_schema()
                    }
                }],
                tool_choice={"type": "function", "function": {"name": "generate_search_queries"}},
                temperature=0  # 保持确定性
            )

            tool_call = completion.choices[0].message.tool_calls[0]
            args = json.loads(tool_call.function.arguments)
            print("args", args)
            return args["queries"]

        except Exception as e:
            print(f"⚠️ [Intent] Decomposition failed: {e}")
            # 降级策略：如果LLM失败，直接使用原始Query
            return [user_input]


# ==========================================
# 3. 升级版注册器 (集成拆解逻辑)
# ==========================================
class AdvancedToolRegistry(SmartToolRegistry):
    def __init__(self,
                 use_vector_search=True,
                 cache_path=r"./Tool/tool_embeddings_cache.pkl",
                 registry_json_path=r"./Tool/tool_registry.json",
                 embedding_model_dir="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
                 ):
        # 1. 自动获取根目录并处理路径
        self.root_dir = self._find_project_root()
        processed_cache_path = self._get_absolute_path(cache_path)
        processed_json_path = self._get_absolute_path(registry_json_path)

        # 2. 调用父类初始化（传入处理后的绝对路径）
        super().__init__(use_vector_search, embedding_model_dir, processed_cache_path, processed_json_path)

    def _find_project_root(self, marker_files=None) -> Path:
        """
        递归向上查找项目根目录。
        检查同级、上级、上上级是否存在核心标记文件。
        """
        if marker_files is None:
            marker_files = {".git", ".env", "requirements.txt", "pyproject.toml"}

        # 从当前文件所在目录开始向上找
        current_path = Path(os.path.abspath(__file__)).resolve()

        # 向上查找 3 层（同级、上级、上上级）
        for _ in range(3):
            if any((current_path / marker).exists() for marker in marker_files):
                print(f"🏠 [System] Project root detected at: {current_path}")
                return current_path

            # 移动到父目录
            parent = current_path.parent
            if parent == current_path:  # 到达磁盘根目录
                break
            current_path = parent

        print(f"⚠️ [System] Root markers not found. Using current working directory.")
        return Path(os.getcwd())

    def _get_absolute_path(self, path_str: str) -> str:
        """
        检查是否为绝对路径，若不是则基于项目根目录拼接。
        适配 Windows (C:\\...) 和 Linux/macOS (/)。
        """
        if os.path.isabs(path_str):
            return path_str

        # 自动转换相对路径为基于根目录的绝对路径
        full_path = self.root_dir / path_str

        # 确保中间文件夹存在（可选）
        full_path.parent.mkdir(parents=True, exist_ok=True)

        return str(full_path)

    def decompose(self,
                  user_input: str,
                  model: str = "qwen3-max",
                  base_url: str = None,
                  api_key: str = None
                  ) -> List[str]:
        """
        使用 LLM 将自然语言拆解为“工具搜索关键词”
        """
        system_prompt = """
        你是一个Agent系统的意图路由器。你的任务是将用户的输入拆解为独立的子任务，
        并将每个子任务转化为**针对API工具描述的搜索关键词**。

        原则：
        1. 去除口语化表达（如"帮我"、"我想知道"、"比如"）。
        2. 如果包含多个任务（如"查天气并算数"），拆分为多个关键词。
        3. 关键词应贴近技术文档或函数描述（例如："需不需要带伞" -> "查询天气 降雨概率"）。
        4. 对于可以通过浏览器搜索的内容，我们保底使用一个浏览器搜索相关内容。
        """
        decompose_client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )

        try:
            # 使用 Function Calling 或 JSON Mode 强制输出结构
            completion = decompose_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                tools=[{
                    "type": "function",
                    "function": {
                        "name": "generate_search_queries",
                        "description": "生成搜索关键词",
                        "parameters": SearchQueries.model_json_schema()
                    }
                }],
                tool_choice={"type": "function", "function": {"name": "generate_search_queries"}},
                temperature=0  # 保持确定性
            )

            tool_call = completion.choices[0].message.tool_calls[0]
            args = json.loads(tool_call.function.arguments)
            print("args", args)
            return args["queries"]

        except Exception as e:
            print(f"⚠️ [Intent] Decomposition failed: {e}")
            # 降级策略：如果LLM失败，直接使用原始Query
            return [user_input]

    def get_tools_smart(self,
                        user_query: str | list,
                        model: str = "qwen3-max",
                        base_url: str = "http://localhost:11434/v1",
                        api_key: str = "ollama",
                        top_k_per_query: int = 1,
                        use_llm=False) -> List[Dict]:
        """
        智能获取工具：
        User Query -> LLM Decompose -> [Query1, Query2] -> Vector Search -> Unique Tools
        """
        if not self.use_vector_search:
            return [t["schema"] for t in self._tools.values()]

        # 1. 意图拆解 (转化步骤)
        print(f"\n🧠 [Thought] Analyzing query: '{user_query}'")
        if use_llm:
            if isinstance(user_query, list):
                user_query = ",".join(user_query)
            search_keywords = self.decompose(user_query, model, base_url, api_key)
        else:
            if isinstance(user_query, str):
                search_keywords = [user_query]
            else:
                search_keywords = user_query
        print(f"🔄 [Rewriting] Search Keywords: {search_keywords}")

        # 2. 多路检索
        matched_tools_map = {}  # 使用字典去重 (name -> schema)

        for keyword in search_keywords:
            # 使用父类的向量搜索方法 (假设父类方法名为 _search_embeddings 或你需要将原 get_tools 拆分)
            # 这里为了演示，我直接复用之前的逻辑片段

            vec = self.embedding_engine.encode([keyword])
            scores = np.dot(vec, self.tool_embeddings.T)[0]
            top_indices = np.argsort(scores)[-top_k_per_query:][::-1]

            print(f"   🔍 Searching for '{keyword}':")
            for idx in top_indices:
                score = scores[idx]
                tool_name = self.tool_names_index[idx]

                # --- 检查软删除状态 ---
                tool_obj = self._tools.get(tool_name)
                if not tool_obj or not tool_obj.get("enabled", True):
                    continue

                # 设定一个更合理的阈值，因为现在的 keyword 更精准了
                if score > 0.35:
                    print(f"      -> Hit: {tool_name} (Score: {score:.4f})")
                    matched_tools_map[tool_name] = self._tools[tool_name]["schema"]
                else:
                    print(f"      -> Miss: {tool_name} (Score: {score:.4f} - too low)")

        return list(matched_tools_map.values())


# ==========================================
# 3. 实战测试
# ==========================================

if __name__ == "__main__":
    # 初始化
    registry = AdvancedToolRegistry(embedding_model_dir=r"E:\models\paraphrase-multilingual-MiniLM-L12-v2")


    # --- 1. 极简注册 (无需手动定义 Pydantic Class) ---
    @registry.register(name="get_weather", description="查询某个城市或地区的当前天气情况，包括温度和天气状况。")
    def get_weather(location: str, unit: str = "celsius"):
        # unit 有默认值，schema 里会体现
        return json.dumps({"location": location, "temp": 24, "unit": unit})


    @registry.register(name="calculator", description="执行数学计算，支持加减乘除。")
    def calculator(expression: str):
        return str(eval(expression))


    @registry.register(name="search_knowledge_base",
                       description="在公司内部知识库文档中搜索相关信息，如报销流程、IT手册等。")
    def search_knowledge_base(keywords: str):
        return "Found relevant documents..."


    @registry.register(name="send_email", description="发送电子邮件给指定联系人。")
    def send_email(recipient: str, subject: str, body: str):
        return "Email sent."


    print("\n" + "=" * 50)

    # --- 2. 测试语义检索 (RAG for Tools) ---

    q1 = "上海今天出门需要带伞吗？"
    # 预期拆解: ["查询上海天气 降雨"] -> 此时和 "查询城市天气..." 相似度会很高
    tools = registry.get_tools_smart(q1)
    print(f"📦 Final Tools: {[t['function']['name'] for t in tools]}")

    print("\n" + "-" * 30)

    # --- 测试案例 2: 复杂多意图 ---
    q2 = "帮我查一下现在的汇率，然后给老板发个邮件汇报结果"
    # 预期拆解: ["查询汇率", "发送邮件"]
    # 注意：如果库里没有"查询汇率"工具，那一项会落空，但"发送邮件"会被召回
    tools = registry.get_tools_smart(q2)
    print(f"📦 Final Tools: {[t['function']['name'] for t in tools]}")

    # 确保保存一次初始状态
    registry.save_cache()

    print("\n" + "=" * 50)
    print("🧪 测试删除功能")

    # --- 测试 1: 软删除 (Soft Delete) ---
    print("\n[Step 1] 软删除 'get_weather'...")
    registry.soft_delete("get_weather")

    # 再次搜索天气，应该找不到或者被忽略
    q_weather = "上海今天下雨吗"
    print(f"Query: {q_weather}")
    tools = registry.get_tools_smart(q_weather)
    print(f"📦 Result after soft delete: {[t['function']['name'] for t in tools]} (Expect empty or others)")

    # --- 测试 2: 恢复 (Recover) ---
    print("\n[Step 2] 恢复 'get_weather'...")
    registry.recover("get_weather")
    tools = registry.get_tools_smart(q_weather)
    print(f"📦 Result after recovery: {[t['function']['name'] for t in tools]} (Expect ['get_weather'])")


    # --- 测试 3: 硬删除 (Hard Delete) ---
    # 假设我们有一个临时工具
    @registry.register("temp_tool", "一个临时测试工具")
    def temp_tool(): pass


    print(f"\n[Step 3] 注册了临时工具 'temp_tool'。当前工具总数: {len(registry.tool_names_index)}")

    print("执行硬删除 'temp_tool'...")
    registry.hard_delete("temp_tool")

    print(f"当前工具索引列表: {registry.tool_names_index}")
    # 验证缓存文件里是否还有
    cached_data = registry._load_cache()
    print(f"缓存文件是否包含 'temp_tool': {'temp_tool' in cached_data}")

    # --- 测试 4: 僵尸清理 (Zombie Clean) ---
    # 模拟场景：手动往 cache 里塞一个假数据，模拟代码被删但缓存还在的情况
    registry.cache_data["deleted_feature"] = {"vector": [], "hash": "old"}
    registry.save_cache()
    print("\n[Step 4] 模拟注入了一个僵尸工具 'deleted_feature' 到缓存中。")

    registry.clean_zombies()
    # 再次检查缓存
    cached_data = registry._load_cache()
    print(f"清理后缓存是否包含 'deleted_feature': {'deleted_feature' in cached_data}")
