import json
import logging
import traceback
from typing import List, Dict, Any, Callable, Generator, Optional
from openai import OpenAI

# 配置日志
logger = logging.getLogger(__name__)


class ChatProcessor:
    def __init__(self, tool_registry):
        self.registry = tool_registry

    def _create_client(self, api_key: str, base_url: str) -> OpenAI:
        return OpenAI(api_key=api_key, base_url=base_url)

    # --- 1. 纯聊天/多模态流式调用 ---
    def process_pure_chat(self,
                          messages: List[Dict],
                          model: str,
                          api_key: str,
                          base_url: str,
                          temperature: float = 0.7,
                          max_token=128) -> Generator[str, None, None]:
        """
        适用于纯对话、多模态分析。
        如果 messages 中包含 image_url，OpenAI 兼容模型会自动识别。
        """
        client = self._create_client(api_key, base_url)

        logger.info(f"💬 Starting Pure Chat. Model: {model}")

        try:
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                temperature=temperature,
                max_tokens=max_token
            )

            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield json.dumps({"content": delta.content}, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Chat Error: {str(e)}")
            yield json.dumps({"error": f"Chat API Error: {str(e)}"}, ensure_ascii=False)

    # --- 2. 强制工具调用的流式输出 ---
    def process_tool_call(self,
                          messages: List[Dict],
                          model: str,
                          api_key: str,
                          base_url: str,
                          user_query: str,
                          use_llm: bool = False,
                          tool_hooks: Optional[Dict[str, Callable]] = None,
                          temperature: float = 0.3) -> Generator[str, None, None]:
        """
        强制工具执行逻辑：
        1. 注入 System Message 明确指令。
        2. 设置 tool_choice 为 'required' 或指定特定工具。
        3. 循环处理工具执行结果。
        """
        client = self._create_client(api_key, base_url)

        # 智能检索相关工具
        available_tools_schemas = self.registry.get_tools_smart(
            user_query,
            model=model,
            base_url=base_url,
            api_key=api_key,
            use_llm=use_llm,
            top_k_per_query=5
        )

        if not available_tools_schemas:
            yield json.dumps({"error": "No relevant tools found for this task."}, ensure_ascii=False)
            return

        # 构造强制工具调用的上下文
        current_messages = messages.copy()

        # 插入强暗示 Prompt (如果最后一条不是 system，可以考虑在首部插入)
        force_prompt = {
            "role": "system",
            "content": "You are a specialized assistant that MUST use the provided tools to fulfill the user's request. Do not answer directly without using tools unless you are summarizing the tool results."
        }
        current_messages.insert(0, force_prompt)

        max_turns = 5
        turn_count = 0

        logger.info(f"🛠️ Starting Forced Tool Process. Model: {model}")

        while turn_count < max_turns:
            turn_count += 1

            current_tool_choice = "required" if turn_count == 1 else "auto"

            try:
                # 使用动态的 current_tool_choice
                stream = client.chat.completions.create(
                    model=model,
                    messages=current_messages,
                    tools=available_tools_schemas,
                    tool_choice=current_tool_choice,  # 修改这一行
                    stream=True,
                    temperature=temperature
                )
            except Exception as e:
                yield json.dumps({"error": f"Tool Loop Error: {str(e)}"}, ensure_ascii=False)
                return

            tool_calls_buffer = {}
            content_buffer = ""

            # --- 解析流 ---
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    content_buffer += delta.content
                    yield json.dumps({"content": delta.content}, ensure_ascii=False)

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {"id": tc.id, "name": tc.function.name, "arguments": ""}
                        if tc.function.arguments:
                            tool_calls_buffer[idx]["arguments"] += tc.function.arguments

            # 如果本轮没有工具调用，说明已经根据工具结果完成了最终总结
            if not tool_calls_buffer:
                break

            # --- 处理工具执行 ---
            executed_calls = []
            for idx in sorted(tool_calls_buffer.keys()):
                call_data = tool_calls_buffer[idx]
                executed_calls.append({
                    "id": call_data["id"],
                    "type": "function",
                    "function": {
                        "name": call_data["name"],
                        "arguments": call_data["arguments"]
                    }
                })

            current_messages.append({
                "role": "assistant",
                "content": content_buffer if content_buffer else None,
                "tool_calls": executed_calls,
                "msg_type": "text"
            })

            yield json.dumps({
                "status": "tool_executing",
                "tools": [c['function']['name'] for c in executed_calls]
            }, ensure_ascii=False)

            for tool_call in executed_calls:
                func_name = tool_call["function"]["name"]
                args_str = tool_call["function"]["arguments"]
                call_id = tool_call["id"]

                try:
                    args_dict = json.loads(args_str) if args_str else {}

                    # Apply Hooks
                    if tool_hooks and func_name in tool_hooks:
                        args_dict = tool_hooks[func_name](args_dict)

                    tool_result = self.registry.call_tool(func_name, args_dict)
                    result_str = json.dumps(tool_result, ensure_ascii=False) if isinstance(tool_result,
                                                                                           (dict, list)) else str(
                        tool_result)

                except Exception as e:
                    result_str = f"Error: {str(e)}"
                    logger.error(f"Execution Error in {func_name}: {result_str}")

                current_messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": func_name,
                    "content": result_str,
                    "msg_type": "tool"
                })

                yield json.dumps({
                    "tool_result": {
                        "name": func_name,
                        "output": result_str,
                        "raw_output": tool_result  # 把工具返回的原生对象传给 app.py
                    }
                }, ensure_ascii=False)

        logger.info("✅ Tool process completed.")

    # --- 3. 专用联网搜索方法（无需工具查询）---
    def process_with_search(self,
                            messages: List[Dict],
                            model: str,
                            api_key: str,
                            base_url: str,
                            user_query: str,
                            vl_api_key: Optional[str] = None,  # 新增视觉专属 API Key
                            vl_base_url: Optional[str] = None,  # 新增视觉专属 Base URL
                            search_top_k: int = 3,
                            search_mode: str = "visual",
                            vl_model: str = "qwen-vl-plus",
                            temperature: float = 0.7) -> Generator[str, None, None]:
        """
        在此方法中解耦视觉分析与最终文本生成。
        严格确保 vl_model 使用 vl_api_key/vl_base_url，常规 model 使用常规 api_key/base_url。
        """
        logger.info(f"🌐 Starting Web Search Process. Query: '{user_query}', Mode: {search_mode}")

        try:
            # 1. 调用 bing_search 获取 Payload
            search_result = self.registry.call_tool(
                "bing_search",
                {"keyword": user_query, "top_k": search_top_k, "mode": search_mode}
            )

            if isinstance(search_result, dict) and "messages" in search_result:
                tool_messages = search_result.get("messages", [])
                tool_user_msg = next((msg for msg in tool_messages if msg.get("role") == "user"), None)

                # --- 阶段 1：如果是 Visual 模式，严格使用视觉凭据请求视觉模型 ---
                if search_mode == "visual" and vl_api_key and vl_base_url and tool_user_msg:
                    logger.info("👁️ Executing Stage 1: Visual Analysis for Search Results.")
                    yield json.dumps({"status": "analyzing_vision", "using_model": vl_model}, ensure_ascii=False)

                    # 构造纯客观分析的 Prompt
                    vl_prompt = "请客观详细地提取并总结这些搜索结果图片中的核心数据和文字信息。"
                    vl_messages = [{"role": "system", "content": vl_prompt}, tool_user_msg]

                    # 调用纯聊天核心，严格传入 vl 系列参数
                    vl_generator = self.process_pure_chat(
                        messages=vl_messages,
                        model=vl_model,
                        api_key=vl_api_key,
                        base_url=vl_base_url,
                        temperature=0.3,
                        max_token=512
                    )

                    vision_analysis_result = ""
                    for chunk_str in vl_generator:
                        try:
                            chunk = json.loads(chunk_str)
                            if "content" in chunk:
                                vision_analysis_result += chunk["content"]
                        except Exception:
                            pass

                    # --- 阶段 2：重组为纯文本供主模型使用 ---
                    original_text = ""
                    if isinstance(tool_user_msg.get("content"), list):
                        for item in tool_user_msg["content"]:
                            if item["type"] == "text":
                                original_text += item["text"] + "\n"
                    else:
                        original_text = str(tool_user_msg.get("content", ""))

                    # 剥离图片，将视觉模型的分析结果作为文本拼接回去
                    new_content = f"{original_text}\n\n【搜索配图的视觉分析提炼】：\n{vision_analysis_result if vision_analysis_result else '（未能提取有效的图片信息）'}"
                    tool_user_msg = {"role": "user", "content": new_content}

                # 记录状态
                yield json.dumps({"status": "search_completed", "mode": search_mode}, ensure_ascii=False)

                # 拼接消息给文本主模型
                enhanced_messages = messages.copy()
                if tool_user_msg:
                    if enhanced_messages and enhanced_messages[-1]["role"] == "user":
                        enhanced_messages[-1] = tool_user_msg
                    else:
                        enhanced_messages.append(tool_user_msg)
                else:
                    enhanced_messages = tool_messages

            else:
                error_msg = "Search tool did not return the expected payload format."
                logger.error(error_msg)
                yield json.dumps({"warning": error_msg}, ensure_ascii=False)
                return

            yield json.dumps({"status": "generating_response", "using_model": model, "mode": "text_final"},
                             ensure_ascii=False)

            # --- 阶段 3：使用主文本模型（和对应的 api_key/base_url）生成带有人设的最终回复 ---
            yield from self.process_pure_chat(
                messages=enhanced_messages,
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature
            )

        except Exception as e:
            error_msg = f"Search process failed: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            yield json.dumps({"error": error_msg}, ensure_ascii=False)
