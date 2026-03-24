import yaml
import time
import os
import threading
from typing import Dict, Any, Optional


class VisualAttentionManager:
    def __init__(self, config_path: str = "./context_templates/visual_config.yaml"):
        self.config_path = config_path
        self.text_policies = {}
        self.config = {}
        self.config_lock = threading.RLock()  # 读写锁，保证热重载安全

        # 熵池状态 { "Coding": 120.5, "Social": 10.0 }
        self.entropy_pools: Dict[str, float] = {}
        self.last_process_time = time.time()
        self.current_tag = "Other"

        # 初始化加载
        self.reload_config()

    def reload_config(self) -> bool:
        """
        [API] 热重载配置。
        UI界面保存yaml后调用此方法，立即更新策略。
        """
        if not os.path.exists(self.config_path):
            print(f"⚠️ 配置文件不存在: {self.config_path}")
            return False

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                new_config = yaml.safe_load(f)
                policies = {}
                for tag, rule in new_config.get('policies', {}).items():
                    if 'text_flush_actions' in rule:
                        policies[tag] = rule['text_flush_actions']

            with self.config_lock:
                self.config = new_config
                self.text_policies = policies
                print(f"✅ 视觉策略已重载 (包含 {len(self.config.get('policies', {}))} 个场景定义)")
            return True
        except Exception as e:
            print(f"❌ 配置文件加载失败: {e}")
            return False

    def _get_policy(self, tag: str) -> Dict:
        """获取指定Tag的策略配置，如果未定义则回退到 'Other'"""
        with self.config_lock:
            policies = self.config.get('policies', {})
            # 1. 尝试直接获取
            if tag in policies:
                return policies[tag]
            # 2. 尝试回退到 'Other'
            return policies.get('Other', {})

    def _apply_time_evolution(self, current_time: float):
        """
        应用时间演化：
        1. 熵值自然衰减 (Decay)
        2. 时间自动加分 (Tick, 用于视频/游戏)
        """
        delta = current_time - self.last_process_time
        # 防止过高频率计算，设定最小时间片为 0.5秒
        if delta < 0.5:
            return

        self.last_process_time = current_time

        with self.config_lock:
            # 遍历所有活跃的熵池
            for tag in list(self.entropy_pools.keys()):
                policy = self._get_policy(tag)

                # A. 检查是否启用，禁用的Tag直接清零
                if not policy.get('enabled', True):
                    self.entropy_pools[tag] = 0.0
                    continue

                # B. 时间加分 (Tick) - 仅针对当前前台应用
                # 只有当用户真的在这个场景里，时间流逝才有意义
                if tag == self.current_tag:
                    tick_score = policy.get('actions', {}).get('tick', 0)
                    if tick_score > 0:
                        self.entropy_pools[tag] += (tick_score * delta)

                # C. 自然衰减 (Decay) - 针对所有池子
                decay_rate = policy.get('decay_rate', 0)
                if decay_rate > 0 and self.entropy_pools[tag] > 0:
                    # 计算衰减量
                    decay_amount = decay_rate * delta
                    self.entropy_pools[tag] = max(0.0, self.entropy_pools[tag] - decay_amount)

    def process_event(self, event: Dict) -> Optional[Dict[str, Any]]:
        """
        核心处理循环。
        :return: None (不截图) 或 包含截图指令的字典
        """
        current_time = time.time()

        # 1. 更新主场景聚焦
        # 我们假设外部传入的 event 已经包含了 context_tag
        new_tag = event.get('context_tag', 'Other')
        self.current_tag = new_tag

        # 2. 执行时间演化 (衰减与Tick)
        self._apply_time_evolution(current_time)

        # 3. 获取当前策略
        policy = self._get_policy(new_tag)

        # [判断1] 是否全局禁用该场景
        if not policy.get('enabled', True):
            return None

        # 初始化池子
        if new_tag not in self.entropy_pools:
            self.entropy_pools[new_tag] = 0.0

        # 4. 计算动作得分 (Action Score)
        actions_map = policy.get('actions', {})
        score = 0.0
        event_type = event.get('type')

        if event_type == 'FOCUS_SWITCH':
            # 只有切换进入新窗口才加分
            if event.get('switch_type') == 'SWITCH_NEW':
                score = actions_map.get('switch_in', 0)

        elif event_type == 'KEYBOARD':
            key_target = str(event.get('target', '')).lower()

            # 优先匹配特定按键配置
            if key_target in ['enter', 'return']:
                score = actions_map.get('enter', 0) or actions_map.get('special_key', 0)
            elif 'ctrl' in event.get('target', '') and 'v' in event.get('target', ''):  # 简易判断粘贴
                score = actions_map.get('paste', 0)
            elif len(key_target) > 1:  # Tab, Esc, Backspace 等
                score = actions_map.get('special_key', 0)
            else:
                score = actions_map.get('keypress', 0)

        elif event_type == 'INTERACTION':
            # 可以扩展：识别特定按钮名称
            target_name = str(event.get('target', ''))
            if "发送" in target_name or "搜索" in target_name or "提交" in target_name:
                score = actions_map.get('click_send', 0)
            else:
                score = actions_map.get('click', 0)

        # 5. 更新熵池
        if score > 0:
            self.entropy_pools[new_tag] += score
            # 可选：打印调试信息
            # print(f"📊 [{new_tag}] +{score} => {self.entropy_pools[new_tag]:.1f}")

        # 6. 阈值判断
        threshold = policy.get('threshold', 100.0)

        if self.entropy_pools[new_tag] >= threshold:
            # === 触发截图 ===
            print(f"📸 [视觉触发] 场景: {new_tag} | 熵值: {self.entropy_pools[new_tag]:.1f}/{threshold}")

            # 清空池子 (也可改为减去阈值，保留溢出部分)
            self.entropy_pools[new_tag] = 0.0

            # 构造返回指令
            return {
                "should_capture": True,
                "reason": f"threshold_met_{new_tag}",
                "tag": new_tag,
                "capture_scope": policy.get('capture_scope', 'window'),
                "quality": policy.get('snapshot_quality', 'medium'),
                "include_logs": 10,
                "capture_mode": policy.get('capture_mode', 'hybrid')  # 传递模式配置
            }

        return None