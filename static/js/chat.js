// 获取 HTML 中埋下的 Session ID 和 Chat Type
const currentSessionId = document.getElementById('currentSessionId').value;
const configModelName = document.getElementById('configModelName').value; // 获取后端配置的模型名
const currentChatType = document.getElementById('currentChatType') ? document.getElementById('currentChatType').value : 'web_chat'; // 新增

// 背景图功能
const bgImageBtn = document.getElementById('bgImageBtn');
const bgFileInput = document.getElementById('bgFileInput');
const messagesBox = document.getElementById('messagesBox');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const apiModeToggle = document.getElementById('apiModeToggle');
const modeLabel = document.getElementById('modeLabel');
const sidebarModelIndicator = document.getElementById('sidebarModelIndicator');
let selectedImages = []; // 存储 Base64 字符串的数组

// ====== 系统提示词(人设)相关元素与事件 ======
const promptSelect = document.getElementById('promptSelect');
const userRoleInput = document.getElementById('userRoleInput');


// ==========================================
// 移动端模拟下拉刷新 (针对 messagesBox)
// ==========================================
let touchStartY = 0;
let touchEndY = 0;

messagesBox.addEventListener('touchstart', (e) => {
    // 只有在滚动条位于最顶部时，才记录起始位置
    if (messagesBox.scrollTop === 0) {
        touchStartY = e.changedTouches[0].screenY;
    }
}, { passive: true });

messagesBox.addEventListener('touchend', (e) => {
    if (messagesBox.scrollTop === 0 && touchStartY > 0) {
        touchEndY = e.changedTouches[0].screenY;
        // 如果手指向下滑动超过 80px，触发页面刷新
        if (touchEndY - touchStartY > 80) {
            showToast('正在刷新...', 'processing');
            setTimeout(() => {
                location.reload();
            }, 500);
        }
    }
    touchStartY = 0; // 重置状态
}, { passive: true });

// 侧边栏折叠
const sidebarToggle = document.getElementById('sidebarToggle');
const container = document.querySelector('.container');
const mobileOverlay = document.getElementById('mobile-overlay');

const isMobile = window.innerWidth <= 768;
let isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';

// ====== 侧边栏折叠与响应式逻辑 ======
// 模式切换监听 (更新侧边栏中的指示器)
if (apiModeToggle) {
    apiModeToggle.addEventListener('change', (e) => {
        const isApi = e.target.checked;
        if (modeLabel) modeLabel.textContent = isApi ? "云端 API" : "本地模型 (Ollama)";
        if (sidebarModelIndicator) {
            sidebarModelIndicator.textContent = isApi ? "Cloud API Mode" : `${configModelName} (Local)`;
        }
    });
}

if (isMobile) {
    isCollapsed = true; // 手机端始终默认折叠
}

// 初始化图标
if (isCollapsed) {
    container.classList.add('sidebar-collapsed');
    sidebarToggle.querySelector('i').className = 'fas fa-bars';
} else {
    sidebarToggle.querySelector('i').className = 'fas fa-chevron-left';
}

// 按钮点击切换逻辑
sidebarToggle.addEventListener('click', () => {
    container.classList.toggle('sidebar-collapsed');
    const collapsed = container.classList.contains('sidebar-collapsed');
    localStorage.setItem('sidebarCollapsed', collapsed);

    const icon = sidebarToggle.querySelector('i');
    if (collapsed) {
        icon.className = 'fas fa-bars'; // 收起时显示汉堡菜单
    } else {
        icon.className = 'fas fa-chevron-left'; // 展开时显示向左箭头（提示点击收起）
    }
});

// 点击遮罩层收回侧边栏
if (mobileOverlay) {
    mobileOverlay.addEventListener('click', () => {
        container.classList.add('sidebar-collapsed');
        localStorage.setItem('sidebarCollapsed', 'true');
        sidebarToggle.querySelector('i').className = 'fas fa-bars';
    });
}

async function updateSystemPrompt() {
    if (!promptSelect || !userRoleInput) return;
    const promptName = promptSelect.value;
    const userRole = userRoleInput.value.trim() || '用户'; // 兜底防止为空

    try {
        const res = await fetch('/api/ai/change_prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompt_name: promptName,
                user_role: userRole
            })
        });
        if (!res.ok) console.error("保存人设失败");
    } catch (err) {
        console.error("网络请求失败", err);
    }
}

// 绑定修改事件：切换下拉框或修改称呼后离开焦点即自动保存
if (promptSelect) promptSelect.addEventListener('change', updateSystemPrompt);
if (userRoleInput) userRoleInput.addEventListener('blur', updateSystemPrompt);

// ====== 背景图与自定义弹窗相关 ======
// ====== 全新：双层背景与视觉焦点拾取 ======
const currentBgUrl = document.getElementById('currentBgUrl') ? document.getElementById('currentBgUrl').value : '';
let currentBgX = document.getElementById('currentBgX') ? document.getElementById('currentBgX').value : 50;
let currentBgY = document.getElementById('currentBgY') ? document.getElementById('currentBgY').value : 50;

let selectedFocalX = 50;
let selectedFocalY = 50;
let base64ToUpload = null;

// 统一切换背景和 CSS 变量的函数
function applyBackground(url, x, y) {
    const chatArea = document.querySelector('.chat-area');
    if (url) {
        chatArea.style.setProperty('--bg-image', `url('${url}')`);
        chatArea.style.setProperty('--bg-x', `${x}%`);
        chatArea.style.setProperty('--bg-y', `${y}%`);
        chatArea.classList.add('has-bg');
    } else {
        chatArea.classList.remove('has-bg');
        chatArea.style.removeProperty('--bg-image');
    }
}

// 页面加载时恢复背景状态
if (currentBgUrl) applyBackground(currentBgUrl, currentBgX, currentBgY);

// 点击图片选择文件
bgImageBtn.addEventListener('click', () => { bgFileInput.click(); });

bgFileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => { openBgCropModal(e.target.result); };
    reader.readAsDataURL(file);
    bgFileInput.value = '';
});

// 监听图片上的点击，移动准星红点 (带安全校验)
const focalContainer = document.getElementById('focal-container');
const focalPoint = document.getElementById('focal-point');
if (focalContainer && focalPoint) {
    focalContainer.addEventListener('click', (e) => {
        const rect = focalContainer.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        selectedFocalX = (x / rect.width) * 100;
        selectedFocalY = (y / rect.height) * 100;

        focalPoint.style.left = `${selectedFocalX}%`;
        focalPoint.style.top = `${selectedFocalY}%`;
    });
} else {
    console.warn("未能找到视觉焦点拾取器，请检查 HTML 结构");
}

// 打开模态框，并利用 Canvas 压缩图片，防止传原图导致浏览器崩溃
function openBgCropModal(imageUrl) {
    const modal = document.getElementById('bg-crop-modal');
    const image = document.getElementById('crop-image');

    const imgObj = new Image();
    imgObj.onload = () => {
        const canvas = document.createElement('canvas');
        let w = imgObj.width, h = imgObj.height;
        // 自动缩放机制，最长边不超过 1920
        if (w > 1920 || h > 1920) {
            const ratio = Math.min(1920 / w, 1920 / h);
            w *= ratio; h *= ratio;
        }
        canvas.width = w; canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(imgObj, 0, 0, w, h);
        base64ToUpload = canvas.toDataURL('image/jpeg', 0.85);

        image.src = base64ToUpload;

        // 重置中心点为正中心 50%
        selectedFocalX = 50; selectedFocalY = 50;
        focalPoint.style.left = '50%'; focalPoint.style.top = '50%';
        modal.style.display = 'block';
    };
    imgObj.src = imageUrl;
}

function closeBgCropModal() {
    document.getElementById('bg-crop-modal').style.display = 'none';
    base64ToUpload = null;
}

// 提交原图压缩版和焦点坐标
async function applyCroppedBackground() {
    if (!base64ToUpload) return;

    // 【关键修复】：先把准备好的图片数据存到一个局部变量里
    const imageDataToSubmit = base64ToUpload;

    // 现在关闭模态框（清理全局变量）就不会影响提交了
    closeBgCropModal();
    showToast('正在应用背景...', 'processing');

    try {
        const res = await fetch('/api/ai/upload_bg', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: currentSessionId,
                chat_type: currentChatType,
                image: imageDataToSubmit, // 使用刚才保存的局部变量
                focal_x: selectedFocalX,
                focal_y: selectedFocalY
            })
        });

        const data = await res.json();
        if (res.ok) {
            applyBackground(data.url, data.x, data.y);
            showToast('背景已更新', 'success');
        } else {
            showToast(data.error || '背景上传失败', 'error');
        }
    } catch (err) {
        showToast('网络错误，保存失败', 'error');
    }
}

// 双击清除背景图
bgImageBtn.addEventListener('dblclick', async () => {
    const confirmDelete = await customConfirm("确定要清除当前会话的专属背景图吗？");
    if(!confirmDelete) return;

    try {
        const res = await fetch('/api/ai/delete_bg', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, chat_type: currentChatType })
        });
        if (res.ok) {
            applyBackground('', 50, 50); // 清理 CSS 变量和 class
            showToast('背景已清除', 'success');
        }
    } catch(err) {
        showToast('清除背景失败', 'error');
    }
});

function customConfirm(message) {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'custom-dialog-overlay';
        overlay.innerHTML = `
            <div class="custom-dialog">
                <p>${message}</p>
                <div class="custom-dialog-btns">
                    <button class="btn-cancel" id="dialogCancel">取消</button>
                    <button class="btn-confirm" id="dialogConfirm">确定</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        document.getElementById('dialogConfirm').onclick = () => { overlay.remove(); resolve(true); };
        document.getElementById('dialogCancel').onclick = () => { overlay.remove(); resolve(false); };
    });
}

// --- 美化版 Prompt ---
function customPrompt(message, defaultValue = '') {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'custom-dialog-overlay';
        overlay.innerHTML = `
            <div class="custom-dialog">
                <p>${message}</p>
                <input type="text" id="dialogInput" value="${defaultValue}">
                <div class="custom-dialog-btns">
                    <button class="btn-cancel" id="dialogCancel">取消</button>
                    <button class="btn-confirm" id="dialogConfirm">确定</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        const input = document.getElementById('dialogInput');
        input.focus();

        document.getElementById('dialogConfirm').onclick = () => { overlay.remove(); resolve(input.value); };
        document.getElementById('dialogCancel').onclick = () => { overlay.remove(); resolve(null); };
    });
}

// ==========================================
// 页面初始化：自动滚动到最底部
// ==========================================
function scrollToBottom() {
    if (messagesBox) {
        messagesBox.scrollTop = messagesBox.scrollHeight;
    }
}

// 1. DOM 结构加载完成后立即滚动一次 (应对纯文本)
document.addEventListener('DOMContentLoaded', scrollToBottom);

// 2. 页面所有资源（包括历史图片）加载完成后再滚动一次，防止图片撑开页面导致滚动条反弹
window.addEventListener('load', scrollToBottom);

// 3. 针对历史记录中的图片，单独监听加载事件，每加载完一张就往下滚一下
document.querySelectorAll('.messages-box img').forEach(img => {
    img.addEventListener('load', scrollToBottom);
});

// 图片处理相关变量
let currentImageBase64 = null;

// 处理文件选择
async function handleFileSelect(input) {
    if (input.files && input.files.length > 0) {
        const files = Array.from(input.files);

        // 使用 Promise.all 并发读取所有图片
        const readPromises = files.map(file => {
            return new Promise((resolve) => {
                const reader = new FileReader();
                reader.onload = (e) => resolve(e.target.result);
                reader.readAsDataURL(file);
            });
        });

        const newImages = await Promise.all(readPromises);

        // 追加到当前列表 (而不是覆盖)
        selectedImages = [...selectedImages, ...newImages];

        // 渲染预览
        renderPreview();
    }
    // 清空 input，允许重复选择同一文件
    input.value = '';
}

// ==========================================
// 全局拖拽上传图片功能
// ==========================================
const dragOverlay = document.getElementById('dragOverlay');
let dragCounter = 0; // 解决 dragenter/dragleave 在子元素上频发闪烁的问题

document.addEventListener('dragenter', (e) => {
    e.preventDefault();
    dragCounter++;
    // 只在拖入文件时显示遮罩
    if (dragCounter === 1 && e.dataTransfer.types.includes('Files')) {
        dragOverlay.classList.add('active');
    }
});

document.addEventListener('dragleave', (e) => {
    e.preventDefault();
    dragCounter--;
    if (dragCounter === 0) {
        dragOverlay.classList.remove('active');
    }
});

document.addEventListener('dragover', (e) => {
    e.preventDefault(); // 必须阻止默认行为，否则 drop 事件不会触发
});

document.addEventListener('drop', async (e) => {
    e.preventDefault();
    dragCounter = 0;
    dragOverlay.classList.remove('active');

    // 过滤出图片文件
    const files = Array.from(e.dataTransfer.files).filter(file => file.type.startsWith('image/'));

    if (files.length > 0) {
        const readPromises = files.map(file => {
            return new Promise((resolve) => {
                const reader = new FileReader();
                reader.onload = (ev) => resolve(ev.target.result);
                reader.readAsDataURL(file);
            });
        });

        const newImages = await Promise.all(readPromises);
        selectedImages = [...selectedImages, ...newImages];
        renderPreview();
        showToast(`成功添加 ${files.length} 张图片`, 'success');
    } else if (e.dataTransfer.files.length > 0) {
        showToast('请拖入图片类型的文件', 'error');
    }
});

// 3. 渲染预览函数
function renderPreview() {
    const container = document.getElementById('imagePreviewContainer');
    const list = document.getElementById('previewList');

    if (selectedImages.length === 0) {
        container.style.display = 'none';
        list.innerHTML = '';
        return;
    }

    container.style.display = 'block';
    list.innerHTML = selectedImages.map((img, index) => `
        <div class="preview-item">
            <img src="${img}">
            <div class="remove-btn" onclick="removeImage(${index})">×</div>
        </div>
    `).join('');
}

// 4. 删除单个图片函数
function removeImage(index) {
    selectedImages.splice(index, 1);
    renderPreview();
}


// 清除已选图片
function clearImage() {
    selectedImages = [];
    renderPreview();
}


// 菜单切换
function toggleMenu(e, sessId) {
    e.stopPropagation(); // 阻止点击 div 触发跳转

    // 先关闭所有其他的菜单
    document.querySelectorAll('.dropdown-menu').forEach(m => {
        if (m.id !== `menu-${sessId}`) m.classList.remove('show');
    });

    const menu = document.getElementById(`menu-${sessId}`);
    if (menu) menu.classList.toggle('show');
}

// 点击外部关闭所有菜单
document.addEventListener('click', () => {
    document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('show'));
});

// 删除会话
async function deleteSession(e, sessionIdToDelete) {
    if (e) e.stopPropagation();
    // 替换 confirm
    const isConfirmed = await customConfirm("确定要永久删除该会话吗？");
    if(!isConfirmed) return;

    try {
        const res = await fetch('/api/ai/clear_history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionIdToDelete,
                chat_type: currentChatType
            })
        });

        if(res.ok) {
            if (sessionIdToDelete === currentSessionId) {
                showToast("当前会话已删除", "success");
                setTimeout(() => window.location.href = '/', 1000); // 给toast一点展示时间
            } else {
                const item = document.getElementById(`sess-item-${sessionIdToDelete}`);
                if (item) {
                    item.style.opacity = '0';
                    setTimeout(() => item.remove(), 300);
                }
            }
        } else {
            showToast("删除失败", "error"); // 替换 alert
        }
    } catch(err) {
        showToast("网络请求失败", "error"); // 替换 alert
    }
}

const modal = document.getElementById("imageModal");
const modalImg = document.getElementById("img01");
function showModal(src) {
    modal.style.display = "block";
    modalImg.src = src;
}

function closeModal() {
    modal.style.display = "none";
}

// 按 ESC 关闭模态窗
document.addEventListener('keydown', function(event) {
    if (event.key === "Escape") {
        closeModal();
    }
});


// 发送消息 (修复：添加 session_id)
async function sendMessage() {
    const text = userInput.value.trim();
    if (!text && selectedImages.length === 0) return;

    if (selectedImages.length > 0) {
        let imagesHtml = '<div class="image-group-container">';
        selectedImages.forEach(imgSrc => {
            imagesHtml += `<img src="${imgSrc}" class="image-thumbnail" onclick="showModal(this.src)">`;
        });
        imagesHtml += '</div>';
        appendMessage('user', imagesHtml);
    }

    if (text) appendMessage('user', text);
    const imagesToSend = [...selectedImages];
    userInput.value = '';
    clearImage();

    const aiMessageDiv = appendMessage('assistant', '<i class="fas fa-spinner fa-spin"></i>');
    const contentDiv = aiMessageDiv.querySelector('.content');
    const useOllama = !apiModeToggle.checked;

    try {
        const response = await fetch('/api/ai/chat_stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                images: imagesToSend,
                use_ollama: useOllama,
                session_id: currentSessionId,
                chat_type: currentChatType // 注入
            })
        });

        contentDiv.innerHTML = '';
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const jsonStr = line.slice(6);
                    if (jsonStr === '[DONE]') break;

                    try {
                        const data = JSON.parse(jsonStr);
                        if (data.error) {
                            contentDiv.innerHTML = `<span style="color:red">Error: ${data.error}</span>`;
                            return;
                        }
                        if (data.info) {
                            console.log(data.info);
                        }
                        if (data.content) {
                            fullText += data.content;
                            renderContent(contentDiv, fullText);
                            messagesBox.scrollTop = messagesBox.scrollHeight;
                        }
                    } catch (e) { console.error(e); }
                }
            }
        }
    } catch (err) {
        contentDiv.innerHTML = "网络连接错误";
    }
}


function appendMessage(role, htmlContent) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    // 这里的 content 可能包含 HTML (如img标签)，所以不用 innerText
    div.innerHTML = `
        <div class="avatar">
            ${role === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>'}
        </div>
        <div class="content markdown-body">${htmlContent}</div>
    `;
    messagesBox.appendChild(div);
    messagesBox.scrollTop = messagesBox.scrollHeight;

    // 如果是纯文本内容，进行一次 Markdown 渲染以防万一
    // 但因为我们允许 htmlContent (图片), 所以只有当不包含 html 标签时才解析MD
    if (!htmlContent.includes('<img') && !htmlContent.includes('<div')) {
         renderContent(div.querySelector('.content'), htmlContent);
    }

    return div;
}


// 核心渲染函数：处理 <think> 标签和 Markdown
function renderContent(element, rawText) {
    let html = '';

    const thinkMatch = rawText.match(/<think>([\s\S]*?)(?:<\/think>|$)/);

    if (thinkMatch) {
        const thinkingContent = thinkMatch[1];
        // 生成折叠的 thinking-box
        html += `
            <div class="thinking-box" onclick="this.classList.toggle('expanded')">
                <div class="thinking-summary">
                    <i class="fas fa-brain"></i> 思考过程... <span style="float:right">点击展开</span>
                </div>
                <div class="thinking-content">
                    ${marked.parse(thinkingContent)}
                </div>
            </div>
        `;
        const mainContent = rawText.replace(/<think>[\s\S]*?(?:<\/think>|$)/, '');
        html += marked.parse(mainContent);
    } else {
        html = marked.parse(rawText);
    }

    element.innerHTML = html;
    element.querySelectorAll('pre code').forEach((block) => {
        hljs.highlightElement(block);
    });
}

// 重命名会话
async function renameSession(e, sessionId, oldName) {
    if (e) e.stopPropagation();
    document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('show'));

    // 替换 prompt
    const newName = await customPrompt("重命名会话:", oldName);
    if (!newName || newName.trim() === "" || newName === oldName) return;

    try {
        const res = await fetch('/api/ai/rename_session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                new_name: newName.trim(),
                chat_type: currentChatType
            })
        });

        const data = await res.json();
        if (res.ok) {
            const titleEl = document.getElementById(`title-${sessionId}`);
            if (titleEl) {
                titleEl.innerHTML = `<i class="fas fa-comment-dots" style="margin-right: 8px;"></i> ${data.new_name}`;
                // location.reload(); // 可以考虑不再刷新页面，提升体验
                showToast("重命名成功", "success");
            }
        } else {
            showToast("重命名失败: " + (data.error || "未知错误"), "error"); // 替换 alert
        }
    } catch (err) {
        console.error(err);
        showToast("网络请求失败", "error"); // 替换 alert
    }
}

// 支持 Shift+Enter 换行，Enter 发送
// 自动调整输入框高度
userInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

// Shift+Enter换行
userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// 页面加载时处理历史消息的 Markdown (如果是服务器直接渲染HTML则不需要)
document.querySelectorAll('.message .content').forEach(el => {
    // 1. 尝试找到隐藏的原始数据容器
    const rawTextarea = el.querySelector('.raw-markdown');

    if (rawTextarea) {
        // 2. 如果找到了原始数据，使用 rawTextarea.value (它保留了格式和换行)
        renderContent(el, rawTextarea.value);
    } else if (!el.querySelector('img') && !el.querySelector('.image-thumbnail')) {
        // 3. 兼容旧数据或无 hidden area 的情况 (兜底)
        renderContent(el, el.innerText);
    }
});

let cropper = null; // 全局保存 cropper 实例

function showToast(message, type = 'info', minDuration = 2000) {
    // 1. 查找或创建全局容器
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    // 2. 创建并追加 Toast 元素
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    // 3. 动画时间控制 (单位: 毫秒)
    const enterDuration = 300;
    const exitDuration = 300;
    const stayDuration = Math.max(minDuration, 1000);

    // 设置动画序列
    toast.style.animation = `
        toastSlideIn ${enterDuration}ms cubic-bezier(0.2, 0.8, 0.2, 1) forwards,
        toastFadeOut ${exitDuration}ms ease-in forwards ${enterDuration + stayDuration}ms
    `;

    container.appendChild(toast);

    // 4. 自动清理
    setTimeout(() => {
        toast.remove();
        // 如果容器里没弹窗了，顺手把容器也销毁，保持 DOM 干净
        if (container.childNodes.length === 0) {
            container.remove();
        }
    }, enterDuration + stayDuration + exitDuration);

    return toast;
}