import os
import time
import random
import json
import base64
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright

# --- ⚙️ 配置 ---
WORKSPACE_DIR = "workspace"
AUTH_FILE = os.path.join(WORKSPACE_DIR, "auth_cookies.json")
RESULT_FILE = os.path.join(WORKSPACE_DIR, "final_payload.json")
MAX_SLICE_HEIGHT = 2000
SLICE_OVERLAP = 20

if not os.path.exists(WORKSPACE_DIR): os.makedirs(WORKSPACE_DIR)


# --- 🛡️ 基础工具 ---
def inject_stealth(page):
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    """)


def clean_page_visuals(page):
    # 稍微简化，避免清理脚本报错卡住流程
    try:
        page.evaluate("""
            () => {
                const keywords = ['cookie', 'modal', 'popup', 'overlay', 'login-mask', 'advert'];
                keywords.forEach(key => {
                    document.querySelectorAll(`[id*="${key}"], [class*="${key}"]`).forEach(el => {
                        el.style.display = 'none';
                    });
                });
            }
        """)
    except:
        pass


def robust_scroll(page):
    # 简易版滚动供参考：
    try:
        for _ in range(4):
            page.evaluate("window.scrollBy(0, window.innerHeight)")
            time.sleep(1)
        page.evaluate("window.scrollTo(0, 0)")
        clean_page_visuals(page)
    except:
        pass


# --- 🖼️ 视觉处理  ---
def PIL_to_base64(img):
    buffered = BytesIO()
    img = img.convert("RGB")
    img.save(buffered, format="JPEG", quality=80)
    return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"


def smart_slice_image(image_path):
    img = Image.open(image_path)
    width, height = img.size
    vision_content_list = []
    if height <= MAX_SLICE_HEIGHT:
        vision_content_list.append({"type": "image_url", "image_url": {"url": PIL_to_base64(img), "detail": "high"}})
        return vision_content_list

    top = 0
    while top < height:
        bottom = min(top + MAX_SLICE_HEIGHT, height)
        crop = img.crop((0, top, width, bottom))
        vision_content_list.append({"type": "image_url", "image_url": {"url": PIL_to_base64(crop), "detail": "high"}})
        if bottom == height: break
        top += (MAX_SLICE_HEIGHT - SLICE_OVERLAP)
    return vision_content_list


def capture_visual_content(page):
    robust_scroll(page)
    temp_path = os.path.join(WORKSPACE_DIR, f"temp_{int(time.time())}.png")
    try:
        page.screenshot(path=temp_path, full_page=True)
    except:
        page.screenshot(path=temp_path, full_page=False)
    return temp_path


def capture_text_content(page):
    try:
        page.wait_for_selector("body", state="visible", timeout=500)
    except:
        pass

    robust_scroll(page)  # 开始滚动加载
    try:
        return page.evaluate("document.body.innerText")[:10000]
    except:
        return "Extract Failed"


# --- 🚨 核心修复：更强的搜索逻辑 ---

def perform_bing_search(page, keyword):
    """
    更稳健的搜索动作
    """
    print(f"🔍 [Bing] 正在搜索: {keyword}")
    page.goto("https://cn.bing.com/", wait_until="domcontentloaded")
    time.sleep(2)  # 刚进去等一下，防反爬风控

    # 1. 尝试寻找输入框 (多种选择器备用)
    selectors = ['input[name="q"]', 'input[id="sb_form_q"]', 'textarea[name="q"]', '#sb_form_q']
    search_input = None

    for sel in selectors:
        if page.is_visible(sel):
            search_input = sel
            break

    if not search_input:
        print("❌ 找不到搜索框，Bing 页面结构可能变了，或需要登录。")
        # 截图看看发生了什么
        page.screenshot(path="debug_no_search_box.png")
        return False

    # 2. 模拟人类点击和输入
    page.click(search_input)
    page.fill(search_input, "")  # 清空
    time.sleep(0.5)
    page.keyboard.type(keyword, delay=100)  # 模拟打字
    time.sleep(0.5)
    page.keyboard.press("Enter")

    # 3. 等待结果 (不再死等 networkidle，而是等标题变化或元素出现)
    try:
        # 等待 URL 变化或者 title 变化
        page.wait_for_load_state("domcontentloaded")
        # 强制等待一下，因为 Bing 也是动态加载结果的
        time.sleep(3)
    except:
        pass

    return True


def extract_search_links(page, top_k):
    """
    更稳健的链接提取
    策略：
    1. 必须是 http/https
    2. 过滤掉 www.bing.com (用户指定：广告/推广)
    3. 保留 cn.bing.com/ck/ (这是有效的搜索结果跳转)
    4. 过滤掉不带 /ck/ 的其他 bing 链接 (防止抓到设置页、图片页等)
    """
    targets = []

    try:
        # 获取所有 h2 下的 a 标签 (Bing 的标题链接通常都在这里)
        elements = page.locator("h2 a").all()
        print(f"    👀 扫描到 {len(elements)} 个潜在链接...")

        for i, el in enumerate(elements):
            if len(targets) >= top_k:
                break

            # 使用 JS 获取绝对 URL
            try:
                url = el.evaluate("node => node.href")
                title = el.inner_text().strip()
            except:
                continue

            print(f"    Processing [{i}]: {title[:15]}... | {url}")

            # --- 🛡️ 过滤逻辑 ---

            # 1. 基础非空检查
            if not url or not title:
                continue

            # 2. 必须是 http 开头
            if not url.startswith("http"):
                continue

            # 3. 【核心修改】过滤 www.bing.com (广告/推广)
            if "www.bing.com" in url:
                continue

            # 4. 处理其他 Bing 链接
            # 如果链接包含 bing.com 或 microsoft.com
            if "bing.com" in url or "microsoft.com" in url:
                # 如果它包含 "/ck/"，说明是正常的搜索跳转，必须保留！
                if "/ck/" in url:
                    pass  # 这是好链接，放行
                else:
                    # 如果不带 /ck/，又含有 bing.com，通常是“相关搜索”、“地图”、“图片”等内部页
                    continue

            # 5. 过滤 JS 伪协议
            if "javascript" in url:
                continue

            # 6. 去重
            if any(t['url'] == url for t in targets):
                continue

            # --- ✅ 通过所有检查 ---
            targets.append({"url": url, "title": title})
            print("      -> ✅ 添加成功")

    except Exception as e:
        print(f"    ⚠️ 提取链接报错: {e}")

    return targets


# --- 主流程 ---

def search_and_process(keyword: str, top_k: int = 3, mode: str = "visual") -> dict:
    """
    模拟人类浏览器搜索行为，搜索目标信息
    :param keyword: 要搜索的内容
    :param top_k: 阅读多少个搜索的内容
    :param mode: 阅读的模式，是返回文本的数据（text），还是截图数据（visual）
    :return: 可直接用于OpenAI的messages，构成：{"model":"xxx","messages":{...}}
    """
    final_payload = {"model": "gpt-4o", "messages": [{"role": "system", "content": "助手"}]}
    user_content_list = [{"type": "text", "text": f"Keyword: {keyword}"}]

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="msedge",
            headless=False,  # 调试时务必开启 headless=False
            args=["--disable-blink-features=AutomationControlled"]
        )

        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        )

        # 如果有 Cookie 就加载，没有就拉倒
        if os.path.exists(AUTH_FILE):
            context = browser.new_context(storage_state=AUTH_FILE)

        page = context.new_page()
        inject_stealth(page)

        # --- 步骤 1: 执行搜索 ---
        success = perform_bing_search(page, keyword)
        if not success:
            browser.close()
            return

        # --- 步骤 2: 提取链接 ---
        targets = extract_search_links(page, top_k)
        print(f"✅ 成功提取 {len(targets)} 个目标。")

        if len(targets) == 0:
            print("❌ 未提取到有效链接，可能是反爬触发验证码，建议不要挂VPN。截图 debug_search_fail.png 已保存。")
            page.screenshot(path="debug_search_fail.png")
            browser.close()
            return

        # --- 步骤 3: 详情页处理 ---
        for i, target in enumerate(targets, 1):
            print(f"\n👉 [{i}] {target['title']}")
            detail_page = context.new_page()
            inject_stealth(detail_page)

            try:
                detail_page.goto(target['url'], timeout=30000, wait_until="domcontentloaded")
                # 尝试等待网络空闲 (即页面不再狂发请求时，通常意味着内容加载完了)
                # 设置 5秒超时，防止某些网页一直有后台请求导致卡死
                try:
                    detail_page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    pass  # 如果超时就不管了，继续往下走

                # 针对知乎等慢速渲染页面的“硬等待”
                # 这一步最“笨”但最有效，给 JS 渲染留出时间
                time.sleep(3)

                if mode == "text":
                    text = capture_text_content(detail_page)
                    user_content_list.append({"type": "text", "text": f"\nSrc {i}: {target['title']}\n{text}"})
                else:
                    img_path = capture_visual_content(detail_page)
                    slices = smart_slice_image(img_path)
                    user_content_list.append({"type": "text", "text": f"\nSrc {i}: {target['title']} (Visual)"})
                    user_content_list.extend(slices)
                    try:
                        os.remove(img_path)
                    except:
                        pass

            except Exception as e:
                print(f"    ❌ 访问失败: {e}")
            finally:
                detail_page.close()
                time.sleep(1)

        browser.close()

    final_payload["messages"].append({"role": "user", "content": user_content_list})
    with open(RESULT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_payload, f, ensure_ascii=False, indent=2)
    print(f"\n💾 完成。")
    return final_payload


if __name__ == "__main__":
    # 建议先用 text 模式跑通流程，再换 visual
    search_and_process("DeepSeek R1 介绍", top_k=2, mode="text")


    # ------------注册工具-------------------
    # from ToolRegistry import AdvancedToolRegistry
    #
    # registry = AdvancedToolRegistry(embedding_model_dir=r"E:\models\paraphrase-multilingual-MiniLM-L12-v2")
    #
    # registry.add_tool(
    #     func=search_and_process,
    #     name="bing_search",
    #     description="在浏览器中使用bing搜索，可进行各种内容的网页搜索"
    # )
    # -------------------------------

    #------------工具使用-------------
    # data = registry.call_tool(
    #     tool_name="bing_search",
    #     tool_args={"keyword": "LLM介绍", "top_k": 2, "mode": "text"}
    # )
    # print(data)
    # -------------------------------

    #注册详情
    # print(json.dumps(registry.get_tools(), ensure_ascii=False, indent=2,default=str))
