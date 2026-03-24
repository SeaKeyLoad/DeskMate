import os
import json
import traceback
import base64
from datetime import datetime
from db import db
from LLModel import LLModel
from SessionContext import MemoryManager, STORAGE_ROOT
from AIConfig import config, prompt_config
from ToolRegistry import AdvancedToolRegistry
from AIService import ChatProcessor


class PetChatCore:
    def __init__(self, user_role="哥哥"):
        # 初始默认使用 config 配置，登录后会被真实用户偏好覆盖
        self.apply_model_config(config.use_ollama)
        # 初始化核心组件
        self.memory_manager = MemoryManager()
        self.registry = AdvancedToolRegistry(embedding_model_dir=config.embedding_model_dir)
        self.chat_processor = ChatProcessor(self.registry)
        self.chat_type = "pet_chat"

        # --- 角色与提示词管理 ---
        self.user_role = user_role
        self.ai_role = prompt_config.data.get("selected_prompt_name", "温柔妹妹")
        self.system_prompt_template = prompt_config.get_system_prompt()
        self.last_chat = ""
        self.stickers = config.stickers

    def apply_model_config(self, use_ollama: bool):
        """动态应用模型配置并实例化 LLM"""
        self.use_ollama = use_ollama
        if self.use_ollama:
            self.base_url = config.ollama_base_url
            self.api_key = config.ollama_api_key
            self.model_name = config.default_model
        else:
            self.base_url = config.openai_base_url
            self.api_key = config.openai_api_key
            self.model_name = config.openai_model

        self.ll_model = LLModel(
            chat_model=self.model_name,
            use_ollama=self.use_ollama,
            base_url=self.base_url,
            api_key=self.api_key,
            embedding_model_dir=config.qwen_embedding_dir,
            rerank_model_dir=config.qwen_rerank_dir
        )

    def update_role_and_prompt(self, user_role, prompt_template=None):
        """动态更新用户称呼和系统提示词"""
        self.user_role = user_role
        if prompt_template:
            self.system_prompt_template = prompt_template
        else:
            # 如果未提供模板，从配置重新加载
            self.system_prompt_template = prompt_config.get_system_prompt()

    def login(self, username, password):
        """本地验证登录，并返回 (user_id, model_mode)"""
        user_data = db.verify_user(username, password)
        if user_data:
            user_id = str(user_data['id'])
            # 读取用户数据库里的模型使用偏好 (0=Ollama, 1=OpenAI)
            model_mode = db.get_user_model_mode(user_id) or 0

            # 登录时立即应用用户偏好
            self.apply_model_config(model_mode == 0)
            return user_id, model_mode
        return None, None

    def update_user_model_mode(self, user_id, use_ollama: bool):
        """持久化保存用户的模型偏好并立即生效"""
        mode = 0 if use_ollama else 1
        db.update_user_model_mode(user_id=user_id, model_mode=mode)
        self.apply_model_config(use_ollama)

    def init_session(self, user_id):
        """获取或创建宠物的专属会话"""
        sessions = self.memory_manager.list_user_sessions(user_id, self.chat_type)
        if sessions:
            return sessions[0]['session_id']
        else:
            default_name = f"宠物对话 {datetime.now().strftime('%H:%M')}"
            session_id = self.memory_manager.create_session(user_id, self.ll_model, default_name, self.chat_type)
            return session_id

    def chat_stream(self, user_id, session_id, message):
        """流式对话生成器"""
        try:
            session_ctx = self.memory_manager.get_session(user_id, session_id, self.chat_type, self.ll_model)
            if not session_ctx:
                raise Exception("会话不存在或已失效")

            if message:
                session_ctx.add_message("user", message, msg_type="text", user_role=self.user_role,
                                        ai_role=self.ai_role)

            context_messages = session_ctx.get_full_context_for_ai()

            # --- 优化：动态获取并格式化系统提示词 ---
            # 确保使用最新的 user_role 填充模板
            current_system_instruction = (self.system_prompt_template
                                          .replace("{user_role}", self.user_role)
                                          .replace("{stickers}", self.stickers))

            if current_system_instruction:
                if context_messages and context_messages[0]['role'] == 'system':
                    # 保留原有的系统消息（通常是压缩后的记忆摘要），将人设提示词放在最前面
                    original_memory = context_messages[0]['content']
                    context_messages[0]['content'] = f"{current_system_instruction}\n\n【历史记忆摘要】\n{original_memory}"
                else:
                    # 如果没有历史记忆，直接插入新的人设
                    context_messages.insert(0, {"role": "system", "content": current_system_instruction})

            history_chat = ""
            for chat_dict in context_messages:
                # 1. 获取时间戳
                timestamp = chat_dict.get('timestamp', 0)

                # 2. 转换为现代格式 (YYYY-MM-DD HH:MM:SS)
                dt_object = datetime.fromtimestamp(timestamp)
                time_str = dt_object.strftime('%Y-%m-%d %H:%M:%S')

                # 3. 拼接字符串，将时间加在角色前面
                role = chat_dict.get('role', 'unknown')
                content = chat_dict.get('content', '')

                history_chat += f"[{time_str}] {role}: {content}\n"

            def hook_bing_search(args: dict) -> dict:
                args['top_k'] = min(args.get('top_k', 3), config.bing_search_max_k)
                args['mode'] = 'text'
                return args

            tool_hooks = {"bing_search": hook_bing_search}

            output = self.ll_model.model_chat_json(
                system_prompt=config.intent_recognition_prompt.replace("{{history_chat}}", history_chat),
                use_ollama=self.use_ollama,
                model=self.model_name,
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=600
            )

            mode = output.get('mode', 'chat')
            print("当前的模式：", mode)

            if mode == "chat":
                response_generator = self.chat_processor.process_pure_chat(
                    messages=context_messages,
                    model=self.model_name,
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=600
                )
            elif mode == "local_tool":
                response_generator = self.chat_processor.process_tool_call(
                    messages=context_messages,
                    model=self.model_name,
                    api_key=self.api_key,
                    use_llm=True,
                    base_url=self.base_url,
                    user_query=message,
                    tool_hooks=tool_hooks,
                    timeout=600
                )
            elif mode == "network":
                response_generator = self.chat_processor.process_with_search(
                    messages=context_messages,
                    model=self.model_name,
                    api_key=self.api_key,
                    base_url=self.base_url,
                    user_query=message,
                    vl_api_key=config.openai_vl_api_key,
                    vl_base_url=config.openai_vl_base_url,
                    search_top_k=output.get("top_k", 2),
                    search_mode=output.get("search_mode", "text"),  # 动态获取，不要硬编码
                    vl_model=config.vl_model,
                    timeout=600
                )
            else:
                response_generator = []

            full_assistant_response = ""
            for chunk_str in response_generator:
                try:
                    chunk = json.loads(chunk_str)
                    if "content" in chunk:
                        content_piece = chunk["content"]
                        full_assistant_response += content_piece
                        yield content_piece

                except Exception as e:
                    print(traceback.format_exc())
                    pass

            if full_assistant_response:
                session_ctx.add_message("assistant", full_assistant_response, user_role=self.user_role,
                                        ai_role=self.ai_role)

        except Exception as e:
            traceback.print_exc()
            yield f"[Error] 发生错误：{str(e)}"

    def _encode_image(self, image_path):
        """将本地图片编码为 Base64"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def active_trigger_stream(self, user_id, session_id, context_text, image_path=None):
        """主动事件触发的专属流式对话生成器（视觉分析与文本回复解耦）"""
        try:
            session_ctx = self.memory_manager.get_session(user_id, session_id, self.chat_type, self.ll_model)
            if not session_ctx:
                raise Exception("会话不存在或已失效")

            messages = []

            # 提取近期对话上下文 (避免宠物忘记刚聊过的内容)
            history = session_ctx.get_full_context_for_ai()
            if len(history) == 0 or history[0]['role'] != 'system':
                # 构建系统提示词
                current_system_instruction = (self.system_prompt_template
                                              .replace("{user_role}", self.user_role)
                                              .replace("{stickers}", self.stickers))
                system_instruction = current_system_instruction or f"你是一个桌面宠物。请根据{self.user_role}的操作状态，主动、简短、有趣地搭话。"
                messages = [{"role": "system", "content": system_instruction}]
            else:
                # 始终确保 system prompt 使用了最新的
                messages.append(history[0])

            messages.extend([m for m in history[-4:] if m['role'] != 'system'])

            # ==========================================
            # 阶段 1：专门的视觉分析 (如果提供了截图)
            # ==========================================
            vision_analysis_result = ""
            # 标记文件是否已被清理，避免重复操作
            image_cleaned = False

            if image_path and os.path.exists(image_path):
                try:
                    base64_image = self._encode_image(image_path)

                    # 仅要求模型客观描述画面，屏蔽寒暄。将文本上下文一并提供，进行多模态锚定。
                    vl_prompt = (
                        f"这是{self.user_role}当前的屏幕截图。系统拦截到的当前操作上下文与焦点信息如下：\n"
                        f"-------------------\n"
                        f"{context_text}\n"
                        f"-------------------\n"
                        f"请结合上述环境信息，详细描述这张图片中的具体内容，特别是{self.user_role}当前正在关注的主要场景、软件界面或核心元素。\n"
                        f"只需客观、精准地描述画面内容，不要做任何情感分析或多余的对话寒暄。"
                    )
                    vl_messages = [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": vl_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }]

                    # 注意：这里强制使用 AIConfig 中配置的专有 VL 参数
                    vl_generator = self.chat_processor.process_pure_chat(
                        messages=vl_messages,
                        model=config.vl_model,
                        api_key=config.openai_vl_api_key,
                        base_url=config.openai_vl_base_url,
                        max_token=1024,
                        temperature=0.6,
                        timeout=600
                    )

                    # 同步等待视觉模型分析完毕 (收集完整描述)
                    for chunk_str in vl_generator:
                        try:
                            chunk = json.loads(chunk_str)
                            if "content" in chunk:
                                vision_analysis_result += chunk["content"]
                        except Exception:
                            pass
                except Exception as ve:
                    # 视觉模型出错时不应中断后续的主动聊天
                    vision_analysis_result = f"（视觉分析失败：未能成功读取当前屏幕画面。）"
                finally:
                    # 【优化点】无论分析成功与否，分析完成后立即删除临时截图，防止磁盘积累
                    try:
                        if os.path.exists(image_path):
                            os.remove(image_path)
                            image_cleaned = True
                    except Exception as de:
                        # 记录删除失败日志，但不抛出异常以免中断对话
                        print(f"[Warning] 临时截图清理失败 {image_path}: {str(de)}")

            # ==========================================
            # 阶段 2：文本模型基于分析结果进行回复
            # ==========================================
            prompt = f"【主动触发】{self.user_role}最近的操作状态如下：\n{context_text}\n"

            if vision_analysis_result:
                prompt = f"\n【屏幕画面视觉分析结果】：\n{vision_analysis_result}\n" + prompt
                prompt += f"\n请结合以上视觉分析结果和操作状态，以你设定的角色性格，合理地对{self.user_role}发起聊天。你要注意历史会话的时间，不要有不合理的对话内容。"
            else:
                prompt += f"\n请主动与{self.user_role}聊天。"

            user_msg = {"role": "user", "content": prompt}
            messages.append(user_msg)

            # 调用底层的文本 LLM 进行纯粹的对话生成，并向外流式输出
            # 此时回归正常的文本模型参数：self.model_name, self.api_key, self.base_url
            response_generator = self.chat_processor.process_pure_chat(
                messages=messages,
                model=self.model_name,
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=600
            )

            full_assistant_response = ""
            for chunk_str in response_generator:
                try:
                    chunk = json.loads(chunk_str)
                    if "content" in chunk:
                        content_piece = chunk["content"]
                        full_assistant_response += content_piece
                        yield content_piece
                except Exception:
                    pass

            # 持久化记忆
            if full_assistant_response:
                # 把视觉分析和状态一并存入用户记忆，保持上下文连贯
                memory_text = context_text if context_text else "无特定操作状态"
                if vision_analysis_result:
                    memory_text = f" | 当前屏幕内容：{vision_analysis_result}" + memory_text

                if memory_text != self.last_chat:
                    session_ctx.add_message("user", f"[主动事件触发] {memory_text}", msg_type="text",
                                            user_role=self.user_role, ai_role=self.ai_role)
                    self.last_chat = memory_text

                session_ctx.add_message("assistant", full_assistant_response, user_role=self.user_role,
                                        ai_role=self.ai_role)

        except Exception as e:
            traceback.print_exc()
            yield f"[Error] 主动触发异常：{str(e)}"
