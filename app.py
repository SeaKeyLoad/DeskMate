import logging
from flask import (Flask, render_template, request, redirect, url_for,
                   Response, stream_with_context, jsonify, send_from_directory)
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from db import db
from LLModel import LLModel
from SessionContext import MemoryManager, STORAGE_ROOT
# 引入配置文件中的 prompt_config 和 DEFAULT_PROMPTS
from AIConfig import config, prompt_config, DEFAULT_PROMPTS
import json
import os
import base64
import time
from datetime import datetime
from AIService import ChatProcessor
from openai import OpenAI
from PIL import Image
import io
from dotenv import load_dotenv
load_dotenv()

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = config.secret_key

# Flask-Login 设置
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

memory_manager = MemoryManager()
# 初始化处理服务 (已彻底移除本地工具注册器依赖)
chat_processor = ChatProcessor(tool_registry=None)
active_users_status = {}


def update_user_status(user_id: str, chat_type: str):
    if user_id not in active_users_status:
        active_users_status[user_id] = {"web_chat": False, "pet_chat": False}
    if chat_type in active_users_status[user_id]:
        active_users_status[user_id][chat_type] = True


# ====== 核心修复：动态获取对应的 LLModel 实例 ======
def get_current_ll_model(user_id: str, requested_use_ollama=None):
    """
    根据用户当前的模式选择（或者传入的动态选择），实例化并返回对应的 LLModel。
    确保内容压缩、记忆初始化和聊天流式输出使用的是完全一致的模型配置。
    """
    if requested_use_ollama is not None:
        use_ollama = requested_use_ollama
        # 如果有明确请求，顺便更新数据库中的偏好
        db.update_user_model_mode(user_id=user_id, model_mode=0 if use_ollama else 1)
    else:
        # 否则从数据库读取用户偏好 (0=Ollama, 1=OpenAI)
        mode = db.get_user_model_mode(user_id) or 0
        use_ollama = (mode == 0)

    if use_ollama:
        return LLModel(
            chat_model=config.default_model,
            use_ollama=True,
            base_url=config.ollama_base_url,
            api_key=config.ollama_api_key,
            # 如果你有 embedding 模型配置也可以在这里传入
        )
    else:
        return LLModel(
            chat_model=config.openai_model,
            use_ollama=False,
            base_url=config.openai_base_url,
            api_key=config.openai_api_key,
        )


# --- 用户认证类 ---
class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role


@login_manager.user_loader
def load_user(user_id):
    u = db.get_user_by_id(user_id)
    if u:
        return User(u['id'], u['username'], u['role'])
    return None


@app.route('/api/ai/user_assets/<path:filename>')
@login_required
def user_assets(filename):
    parts = filename.split('/')
    if len(parts) >= 1 and parts[0] != str(current_user.id):
        pass
    return send_from_directory(STORAGE_ROOT, filename)


# --- 路由 ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        user_id = str(current_user.id)
        chat_type = "web_chat"
        last_sid = db.get_user_last_session(user_id)
        if last_sid:
            session_path = os.path.join(STORAGE_ROOT, user_id, chat_type, last_sid)
            if os.path.exists(session_path) and os.path.isdir(session_path):
                return redirect(url_for('chat', chat_type=chat_type, session_id=last_sid))
        return redirect(url_for('new_chat', chat_type=chat_type))
    return redirect(url_for('login'))


@app.route('/api/ai/init_pet')
@login_required
def init_pet():
    user_id = str(current_user.id)
    chat_type = "pet_chat"
    update_user_status(user_id, chat_type)
    sessions = memory_manager.list_user_sessions(user_id, chat_type)
    if sessions:
        last_sid = sessions[0]['session_id']
        return redirect(url_for('chat', chat_type=chat_type, session_id=last_sid))
    return redirect(url_for('new_chat', chat_type=chat_type))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember') == 'on'
        user_data = db.verify_user(username, password)
        if user_data:
            user = User(user_data['id'], user_data['username'], user_data['role'])
            login_user(user, remember=remember)
            db.log_user_login(user.id, request.remote_addr, request.user_agent.string)
            return redirect(url_for('index'))
        return render_template('login.html', error="用户名或密码错误")
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = 'admin' if 'admin' in username else 'user'
        if db.register_user(username, password, role):
            return redirect(url_for('login'))
        return render_template('register.html', error="用户名已存在")
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    user_id = str(current_user.id)
    if user_id in active_users_status:
        active_users_status[user_id] = {"web_chat": False, "pet_chat": False}
    logout_user()
    return redirect(url_for('login'))


def get_user_session_list(user_id, chat_type):
    user_dir = os.path.join(STORAGE_ROOT, user_id, chat_type)
    if not os.path.exists(user_dir): return []
    sessions = []
    try:
        for d in os.listdir(user_dir):
            session_path = os.path.join(user_dir, d)
            if os.path.isdir(session_path) and d != "long_term_memory":
                meta_path = os.path.join(session_path, "metadata.json")
                session_name, updated_time = d, 0
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                            session_name = meta.get('session_name', d)
                            updated_time = meta.get('last_updated', 0)
                            if meta.get('is_deleted', False): continue
                    except:
                        pass
                sessions.append({'id': d, 'name': session_name, 'updated': updated_time})
    except Exception as e:
        logger.error(f"Error getting session list: {e}")
    sessions.sort(key=lambda x: x['updated'], reverse=True)
    return sessions


def merge_consecutive_images(history):
    if not history: return []
    merged, i, n = [], 0, len(history)
    while i < n:
        current_msg = history[i]
        if current_msg.get('msg_type') == 'image':
            image_group = {'role': current_msg['role'], 'msg_type': 'image_group', 'content': [current_msg['content']]}
            j = i + 1
            while j < n and history[j].get('msg_type') == 'image' and history[j]['role'] == current_msg['role']:
                image_group['content'].append(history[j]['content'])
                j += 1
            merged.append(image_group if len(image_group['content']) > 1 else current_msg)
            i = j
        else:
            merged.append(current_msg)
            i += 1
    return merged


@app.route('/api/ai/new_chat/<chat_type>')
@login_required
def new_chat(chat_type):
    user_id = str(current_user.id)
    update_user_status(user_id, chat_type)
    default_name = f"新对话 {datetime.now().strftime('%H:%M')}"
    try:
        # 使用当前配置的动态 LLModel
        ll_model = get_current_ll_model(user_id)
        session_id = memory_manager.create_session(user_id, ll_model, default_name, chat_type)
        return redirect(url_for('chat', chat_type=chat_type, session_id=session_id))
    except Exception as e:
        return redirect(url_for('chat', chat_type=chat_type, session_id='error'))


# 在路由区域增加两个新接口：上传和删除背景图
@app.route('/api/ai/upload_bg', methods=['POST'])
@login_required
def upload_bg():
    data = request.json
    session_id = data.get('session_id')
    chat_type = data.get('chat_type', 'web_chat')
    image_data = data.get('image')
    # 新增：接收前端传来的视觉焦点百分比坐标
    focal_x = data.get('focal_x', 50)
    focal_y = data.get('focal_y', 50)

    if not session_id or not image_data:
        return jsonify({"error": "缺少必要参数"}), 400

    user_id = str(current_user.id)
    session_dir = os.path.join(STORAGE_ROOT, user_id, chat_type, session_id)
    os.makedirs(session_dir, exist_ok=True)

    filename = "background-image.jpg"
    file_path = os.path.join(session_dir, filename)
    meta_path = os.path.join(session_dir, "bg_meta.json")  # 焦点坐标保存路径

    try:
        header, encoded = image_data.split(",", 1) if "," in image_data else ("data:image/jpeg;base64", image_data)
        with open(file_path, "wb") as f:
            f.write(base64.b64decode(encoded))

        # 将焦点坐标持久化保存
        with open(meta_path, "w") as f:
            json.dump({"x": focal_x, "y": focal_y}, f)

        bg_url = url_for('user_assets',
                         filename=f"{user_id}/{chat_type}/{session_id}/{filename}") + f"?t={int(time.time())}"
        return jsonify({"status": "success", "url": bg_url, "x": focal_x, "y": focal_y})
    except Exception as e:
        logger.error(f"保存背景图失败: {e}")
        return jsonify({"error": "服务器内部错误"}), 500


@app.route('/api/ai/delete_bg', methods=['POST'])
@login_required
def delete_bg():
    data = request.json
    session_id = data.get('session_id')
    chat_type = data.get('chat_type', 'web_chat')
    user_id = str(current_user.id)

    bg_path = os.path.join(STORAGE_ROOT, user_id, chat_type, session_id, "background-image.jpg")
    if os.path.exists(bg_path):
        try:
            os.remove(bg_path)
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"status": "success"})


@app.route('/api/ai/chat/<chat_type>/<session_id>')
@login_required
def chat(chat_type, session_id):
    user_id = str(current_user.id)
    update_user_status(user_id, chat_type)

    ll_model = get_current_ll_model(user_id)
    session_ctx = memory_manager.get_session(user_id, session_id, chat_type, ll_model)

    if not session_ctx:
        return redirect(url_for('new_chat', chat_type=chat_type))

    db.update_last_session(user_id, session_id)
    raw_history = memory_manager.get_full_history(user_id, session_id, chat_type)
    processed_history = merge_consecutive_images(raw_history)
    session_list = get_user_session_list(user_id, chat_type)

    # 检查是否存在专属背景图
    session_dir = os.path.join(STORAGE_ROOT, user_id, chat_type, session_id)
    bg_image_url = ""
    bg_x, bg_y = 50, 50  # 默认在正中心

    if os.path.exists(os.path.join(session_dir, "background-image.jpg")):
        bg_image_url = url_for('user_assets',
                               filename=f"{user_id}/{chat_type}/{session_id}/background-image.jpg") + f"?t={int(time.time())}"
        # 读取焦点坐标
        meta_path = os.path.join(session_dir, "bg_meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                    bg_x, bg_y = meta.get("x", 50), meta.get("y", 50)
            except:
                pass

    return render_template('chat.html',
                           user=current_user,
                           history=processed_history,
                           current_session_id=session_id,
                           current_chat_type=chat_type,
                           session_list=session_list,
                           model_name=config.default_model,
                           user_model_mode=db.get_user_model_mode(user_id) or 0,
                           available_prompts=list(DEFAULT_PROMPTS.keys()),
                           current_prompt_name=prompt_config.data.get("selected_prompt_name", "温柔妹妹"),
                           current_user_role=prompt_config.get_user_role(),
                           bg_image_url=bg_image_url,
                           bg_x=bg_x, bg_y=bg_y)


@app.route('/api/ai/rename_session', methods=['POST'])
@login_required
def api_rename_session():
    data = request.json
    user_id = str(current_user.id)
    session_id = data.get('session_id')
    new_name = data.get('new_name')
    chat_type = data.get('chat_type', 'web_chat')

    if not session_id or not new_name:
        return jsonify({"error": "Missing parameters"}), 400

    # 获取当前模型配置，用于加载会话
    ll_model = get_current_ll_model(user_id)
    # 预加载会话到内存
    session = memory_manager.get_session(user_id, session_id, chat_type, ll_model)
    if session is None:
        return jsonify({"error": "Session not found"}), 404

    success = memory_manager.update_session_name(user_id, session_id, new_name, chat_type)
    if success:
        return jsonify({"status": "success", "new_name": new_name})
    else:
        return jsonify({"error": "Update failed"}), 500


@app.route('/api/ai/clear_history', methods=['POST'])
@login_required
def clear_history():
    data = request.json
    if data.get('session_id'):
        memory_manager.delete_session(str(current_user.id), data.get('session_id'), strategy="hard",
                                      chat_type=data.get('chat_type', 'web_chat'))
    return jsonify({"status": "success"})


@app.route('/api/ai/change_prompt', methods=['POST'])
@login_required
def change_prompt():
    data = request.json
    prompt_name = data.get('prompt_name')
    user_role = data.get('user_role')

    if prompt_name and user_role:
        prompt_config.update_config(prompt_name, "", user_role)
        return jsonify({"status": "success"})
    return jsonify({"error": "Invalid parameters"}), 400


def compress_image_b64(b64_string, max_size=1024, quality=85):
    """
    将 base64 图片解码、压缩（限制最大尺寸和质量），再重新转为 base64
    """
    try:
        image_data = base64.b64decode(b64_string)
        img = Image.open(io.BytesIO(image_data))

        # 转换为 RGB 模式（丢弃透明通道），为了能存为高压缩率的 JPEG
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")

        # 等比例缩放，限制最大宽高为 max_size
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        # 重新保存到内存中，格式设为 JPEG，调整 quality
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality)

        # 重新进行 base64 编码
        compressed_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return compressed_b64
    except Exception as e:
        logger.warning(f"图片压缩失败，将尝试使用原图: {e}")
        return b64_string


# --- 核心对话流 ---
# --- 核心对话流 ---
@app.route('/api/ai/chat_stream', methods=['POST'])
@login_required
def chat_stream():
    try:
        data = request.get_json(silent=True)
        user_message = data.get('message', '')
        session_id = data.get('session_id')
        chat_type, use_ollama = data.get('chat_type', 'web_chat'), data.get('use_ollama', True)
        user_id = str(current_user.id)

        ll_model = get_current_ll_model(user_id, requested_use_ollama=use_ollama)
        session_ctx = memory_manager.get_session(user_id, session_id, chat_type, ll_model)

        raw_images = data.get('images', [])
        if not raw_images and data.get('image'): raw_images = [data.get('image')]

        base64_for_vl = []

        # 1. 处理图片保存，并将图片路径持久化到上下文
        if raw_images:
            session_dir = os.path.join(STORAGE_ROOT, user_id, chat_type, session_id)
            os.makedirs(session_dir, exist_ok=True)
            for idx, raw_img_data in enumerate(raw_images):
                img_b64 = raw_img_data[0] if isinstance(raw_img_data, list) and raw_img_data else raw_img_data
                if not isinstance(img_b64, str): continue

                header, encoded = img_b64.split(",", 1) if "," in img_b64 else ("data:image/png;base64", img_b64)

                # 压缩发给 API 的 Base64
                compressed_encoded = compress_image_b64(encoded)
                base64_for_vl.append(compressed_encoded)

                # 下面依然使用原始的 encoded 保存到本地供前端展示，保证用户体验
                file_ext = header.split(';')[0].split('/')[1] if ";" in header and "/" in header else "png"
                filename = f"img_{int(time.time())}_{idx}.{file_ext}"
                with open(os.path.join(session_dir, filename), "wb") as f:
                    f.write(base64.b64decode(encoded))

                session_ctx.add_message("user", url_for('user_assets',
                                                        filename=f"{user_id}/{chat_type}/{session_id}/{filename}"),
                                        msg_type="image", allow_compress=False)

        # 2. 将用户的【原始文本输入】持久化到上下文（前端刷新显示的干净内容）
        if user_message:
            session_ctx.add_message("user",
                                    user_message,
                                    msg_type="text",
                                    system_role=prompt_config.system_role,
                                    allow_compress=False)

        # 3. 获取准备发送给大模型的上下文副本 (List of dicts)
        context_messages = list(session_ctx.get_full_context_for_ai())

        # 4. 多模态视觉预分析及【隐式注入】
        if base64_for_vl:
            try:
                vl_client = OpenAI(
                    api_key=config.openai_vl_api_key,
                    base_url=config.openai_vl_base_url
                )

                vl_prompt = "请详细描述以下图片的内容。"
                if user_message:
                    vl_prompt += f" 请特别结合用户的提问进行重点分析。用户的提问是：{user_message}"

                content = [{"type": "text", "text": vl_prompt}]
                for b64 in base64_for_vl:
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                    })

                logger.info(f"开始调用视觉模型 {config.vl_model} 分析...")

                # 直接调用 SDK 方法，无需自己拼凑 URL 和 Headers
                response = vl_client.chat.completions.create(
                    model=config.vl_model,
                    messages=[{"role": "user", "content": content}],
                    max_tokens=2048,
                    timeout=60  # 设置超时以防卡死
                )

                # 解析返回结果也变得更简洁
                vl_analysis_result = response.choices[0].message.content
                logger.info("视觉模型分析完成。")

                # --- 下面的隐式注入逻辑保持不变 ---
                enhanced_prefix = f"【系统提示：以下是视觉模型对当前上传图片的分析结果】\n{vl_analysis_result}\n\n"

                if user_message:
                    for i in range(len(context_messages) - 1, -1, -1):
                        if context_messages[i].get('role') == 'user':
                            new_msg = dict(context_messages[i])
                            new_msg['content'] = enhanced_prefix + f"【用户提问】\n{new_msg['content']}"
                            context_messages[i] = new_msg
                            break
                else:
                    context_messages.append({
                        "role": "user",
                        "content": enhanced_prefix + "【用户未输入文字，请根据上述图片内容自由回复】"
                    })

            except Exception as e:
                logger.error(f"视觉模型分析失败: {e}")
                error_prefix = f"【系统提示：尝试分析图片失败，错误信息：{str(e)}】\n\n"
                if user_message:
                    for i in range(len(context_messages) - 1, -1, -1):
                        if context_messages[i].get('role') == 'user':
                            new_msg = dict(context_messages[i])
                            new_msg['content'] = error_prefix + f"【用户提问】\n{new_msg['content']}"
                            context_messages[i] = new_msg
                            break
                else:
                    context_messages.append({"role": "user", "content": error_prefix + "【无图片信息，请自由回复】"})

        # 5. 系统设定与记忆合并
        system_instruction = prompt_config.get_system_prompt()
        if system_instruction:
            if context_messages and context_messages[0]['role'] == 'system':
                original_memory = context_messages[0]['content']
                context_messages[0]['content'] = f"{system_instruction}\n\n【历史记忆摘要】\n{original_memory}"
            else:
                context_messages.insert(0, {"role": "system", "content": system_instruction})

        # 6. 流式生成
        def generate():
            try:
                response_generator = chat_processor.process_pure_chat(
                    messages=context_messages,  # 这里传入的是带有视觉分析的隐藏副本
                    model=ll_model.chat_model,
                    api_key=ll_model.api_key,
                    base_url=ll_model.base_url,
                    max_token=8192,
                )

                full_assistant_response = ""
                for chunk_str in response_generator:
                    chunk = json.loads(chunk_str)
                    if "content" in chunk: full_assistant_response += chunk["content"]
                    yield f"data: {chunk_str}\n\n"

                # 助手回复内容正常持久化
                if full_assistant_response:
                    session_ctx.add_message("assistant", full_assistant_response, system_role=prompt_config.system_role)
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Chat Stream Error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return Response(stream_with_context(generate()), mimetype='text/event-stream')

    except Exception as e:
        logger.error(f"Fatal Error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8505)
