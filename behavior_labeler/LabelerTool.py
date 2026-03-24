"""
🎯 行为坐标标注工具 v2.2
优化：
1. 扩大默认窗口尺寸并增加最小尺寸限制，解决高DPI下内容展示不全的问题。
2. 增加独立的 JSON 预览窗口，支持滚动查看并内置复制按钮。
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import psutil
import win32gui
import win32process
import datetime
import os
from typing import Dict, List, Optional

# 引入 UI Automation
try:
    import uiautomation as auto
    HAS_UIA = True
    auto.SetGlobalSearchTimeout(1.0)
except ImportError:
    HAS_UIA = False
    print("⚠️ 未安装 uiautomation，控件类型自动提取功能将不可用。建议运行：pip install uiautomation")


# ==========================================
# 屏幕覆盖层（框选工具）
# ==========================================
class ScreenOverlay:
    def __init__(self, parent, callback):
        self.parent = parent
        self.callback = callback
        self.top = None
        self.canvas = None
        self.start_x = 0
        self.start_y = 0
        self.rect_id = None
        self.selection = None

    def show(self):
        self.top = tk.Toplevel(self.parent)
        self.top.attributes('-fullscreen', True)
        self.top.attributes('-topmost', True)
        self.top.attributes('-alpha', 0.3)
        self.top.configure(cursor="cross")
        self.top.configure(bg='black')

        screen_w = self.top.winfo_screenwidth()
        screen_h = self.top.winfo_screenheight()

        self.canvas = tk.Canvas(self.top, width=screen_w, height=screen_h, bg='black', highlightthickness=0)
        self.canvas.pack()

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Escape>", lambda e: self.close())

        self.canvas.create_text(screen_w // 2, 50, text="拖动鼠标框选目标区域 | ESC 取消", fill='white', font=('Microsoft YaHei', 16, 'bold'))

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect_id = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline='#00ff00', width=2, fill='', stipple='gray50')

    def on_drag(self, event):
        if self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)

        if x2 - x1 < 10 or y2 - y1 < 10:
            x1, y1 = event.x - 5, event.y - 5
            x2, y2 = event.x + 5, event.y + 5

        self.selection = {
            'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
            'center_x': (x1 + x2) // 2, 'center_y': (y1 + y2) // 2,
            'width': x2 - x1, 'height': y2 - y1
        }
        self.close()
        self.callback(self.selection)

    def close(self):
        if self.top:
            self.top.destroy()
            self.top = None


# ==========================================
# 窗口与进程管理器
# ==========================================
class WindowProcessManager:
    @staticmethod
    def get_all_processes() -> List[Dict]:
        proc_dict = {}
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                name = proc.info['name']
                if name and name not in proc_dict:
                    proc_dict[name] = {'name': name, 'pid': proc.info['pid']}
            except:
                continue
        return sorted(proc_dict.values(), key=lambda x: x['name'].lower())

    @staticmethod
    def get_windows_by_process(process_name: str) -> List[Dict]:
        windows = []
        def enum_callback(hwnd, lParam):
            if win32gui.IsWindowVisible(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    proc_name = psutil.Process(pid).name()
                    if proc_name.lower() == process_name.lower():
                        title = win32gui.GetWindowText(hwnd)
                        rect = win32gui.GetWindowRect(hwnd)
                        if title:
                            windows.append({
                                'hwnd': hwnd,
                                'title': title,
                                'pid': pid,
                                'rect': rect,
                                'width': rect[2] - rect[0],
                                'height': rect[3] - rect[1]
                            })
                except:
                    pass
            return True

        win32gui.EnumWindows(enum_callback, None)
        return windows

    @staticmethod
    def get_control_info_at_point(x: int, y: int) -> Optional[Dict]:
        if not HAS_UIA:
            return None
        try:
            with auto.UIAutomationInitializerInThread():
                control = auto.ControlFromPoint(x, y)
                if not control: return None

                root = control.GetTopLevelControl()
                win_w, win_h = 1, 1
                root_left, root_top = 0, 0

                if root:
                    root_rect = root.BoundingRectangle
                    win_w = root_rect.right - root_rect.left
                    win_h = root_rect.bottom - root_rect.top
                    root_left = root_rect.left
                    root_top = root_rect.top

                baseline_x = x - root_left
                baseline_y = y - root_top
                rev_x = win_w - baseline_x
                rev_y = win_h - baseline_y

                return {
                    'Name': control.Name or '',
                    'ControlTypeName': control.ControlTypeName or '',
                    'AutomationId': control.AutomationId or '',
                    'ClassName': control.ClassName or '',
                    'ProcessId': control.ProcessId,
                    'BaselineX': baseline_x,
                    'BaselineY': baseline_y,
                    'WinW': win_w,
                    'WinH': win_h,
                    'RevX': rev_x,
                    'RevY': rev_y,
                    'RelX': round((baseline_x / win_w) * 100, 1) if win_w > 0 else 0,
                    'RelY': round((baseline_y / win_h) * 100, 1) if win_h > 0 else 0
                }
        except Exception as e:
            print(f"⚠️ 控件信息提取失败：{e}")
            return None


# ==========================================
# 标注工具主界面
# ==========================================
class BehaviorLabeler:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("🎯 行为坐标标注工具 v2.2")

        # [优化 1] 扩大默认尺寸，并设置最小尺寸限制
        self.root.geometry("1100x950")
        self.root.minsize(1000, 850)

        self.current_selection = None
        self.current_control_info = None
        self.window_info = {}
        self.rules_list = []
        self.process_list = []
        self.window_list = []

        self.default_tolerance = 35
        self.default_tolerance_pct = 0.05

        self._init_ui()
        self._load_processes()

    def _init_ui(self):
        select_frame = ttk.LabelFrame(self.root, text="📋 第一步：选择目标窗口", padding=10)
        select_frame.pack(fill='x', padx=10, pady=5)

        row1 = ttk.Frame(select_frame)
        row1.pack(fill='x', pady=5)
        ttk.Label(row1, text="选择进程:", width=12).pack(side='left')
        self.process_var = tk.StringVar()
        self.process_combo = ttk.Combobox(row1, textvariable=self.process_var, width=40, state='readonly')
        self.process_combo.pack(side='left', padx=5)
        self.process_combo.bind('<<ComboboxSelected>>', self._on_process_selected)
        ttk.Button(row1, text="🔄 刷新", command=self._load_processes).pack(side='left', padx=10)

        row2 = ttk.Frame(select_frame)
        row2.pack(fill='x', pady=5)
        ttk.Label(row2, text="选择窗口:", width=12).pack(side='left')
        self.window_var = tk.StringVar()
        self.window_combo = ttk.Combobox(row2, textvariable=self.window_var, width=60, state='readonly')
        self.window_combo.pack(side='left', padx=5)
        self.window_combo.bind('<<ComboboxSelected>>', self._on_window_selected)

        row3 = ttk.Frame(select_frame)
        row3.pack(fill='x', pady=5)
        ttk.Label(row3, text="窗口尺寸:", width=12).pack(side='left')
        self.win_w_entry = ttk.Entry(row3, width=10, state='readonly')
        self.win_w_entry.pack(side='left', padx=5)
        ttk.Label(row3, text="×").pack(side='left')
        self.win_h_entry = ttk.Entry(row3, width=10, state='readonly')
        self.win_h_entry.pack(side='left', padx=5)
        ttk.Label(row3, text="进程名:", width=10).pack(side='left', padx=(20, 0))
        self.proc_entry = ttk.Entry(row3, width=30, state='readonly')
        self.proc_entry.pack(side='left', padx=5)

        capture_frame = ttk.LabelFrame(self.root, text="🎯 第二步：框选目标 & 自动提取控件信息", padding=10)
        capture_frame.pack(fill='both', expand=True, padx=10, pady=5)

        btn_row = ttk.Frame(capture_frame)
        btn_row.pack(fill='x', pady=10)
        ttk.Button(btn_row, text="🖱️ 框选目标区域", command=self._start_selection).pack(side='left', padx=5)
        ttk.Button(btn_row, text="🔍 重新提取", command=self._extract_control_info).pack(side='left', padx=5)

        self.coord_label = ttk.Label(capture_frame, text="请点击【框选目标区域】按钮选择屏幕区域", font=('Microsoft YaHei', 11), foreground='gray')
        self.coord_label.pack(pady=5)

        detail_frame = ttk.Frame(capture_frame)
        detail_frame.pack(fill='x', pady=10)

        left_grid = ttk.LabelFrame(detail_frame, text="📐 坐标数据 (Baseline)", padding=10)
        left_grid.pack(side='left', fill='both', expand=True, padx=5)

        self.abs_x_entry = self._make_grid_row(left_grid, "绝对坐标 X:", 0)
        self.abs_y_entry = self._make_grid_row(left_grid, "绝对坐标 Y:", 1)
        self.abs_w_entry = self._make_grid_row(left_grid, "框选宽度 W:", 2)
        self.abs_h_entry = self._make_grid_row(left_grid, "框选高度 H:", 3)
        self.rel_x_entry = self._make_grid_row(left_grid, "相对 X %:", 4)
        self.rel_y_entry = self._make_grid_row(left_grid, "相对 Y %:", 5)

        right_grid = ttk.LabelFrame(detail_frame, text="🔧 控件特征 (UI探针)", padding=10)
        right_grid.pack(side='left', fill='both', expand=True, padx=5)

        self.ctrl_type_entry = self._make_grid_row(right_grid, "ControlType:", 0, 25)
        self.auto_id_entry = self._make_grid_row(right_grid, "AutomationId:", 1, 25)
        self.name_entry = self._make_grid_row(right_grid, "Name:", 2, 25)
        self.class_entry = self._make_grid_row(right_grid, "ClassName:", 3, 25)
        self.rev_x_entry = self._make_grid_row(right_grid, "距右 RevX:", 4)
        self.rev_y_entry = self._make_grid_row(right_grid, "距底 RevY:", 5)

        rule_frame = ttk.LabelFrame(self.root, text="⚙️ 第三步：配置行为规则", padding=10)
        rule_frame.pack(fill='x', padx=10, pady=5)

        row1 = ttk.Frame(rule_frame)
        row1.pack(fill='x', pady=3)
        ttk.Label(row1, text="意图标签:", width=12).pack(side='left')
        self.intent_entry = ttk.Entry(row1, width=50)
        self.intent_entry.pack(side='left', padx=5)
        self.intent_entry.insert(0, "点击目标按钮")

        row2 = ttk.Frame(rule_frame)
        row2.pack(fill='x', pady=3)
        ttk.Label(row2, text="匹配模式:", width=12).pack(side='left')
        self.mode_var = tk.StringVar(value="anchor")
        mode_combo = ttk.Combobox(row2, textvariable=self.mode_var, width=20, state='readonly')
        mode_combo['values'] = ['anchor', 'adaptive']
        mode_combo.pack(side='left', padx=5)

        ttk.Label(row2, text="定位策略:", width=12).pack(side='left', padx=(20, 0))
        self.strategy_var = tk.StringVar(value="bottom_center")
        strategy_combo = ttk.Combobox(row2, textvariable=self.strategy_var, width=20, state='readonly')
        strategy_combo['values'] = ['top_left', 'top_right', 'top_center', 'bottom_left', 'bottom_right', 'bottom_center', 'center', 'stretch']
        strategy_combo.pack(side='left', padx=5)

        row3 = ttk.Frame(rule_frame)
        row3.pack(fill='x', pady=3)
        ttk.Label(row3, text="像素容差:", width=12).pack(side='left')
        self.tolerance_entry = ttk.Entry(row3, width=10)
        self.tolerance_entry.pack(side='left', padx=5)
        self.tolerance_entry.insert(0, str(self.default_tolerance))

        ttk.Label(row3, text="百分比容差:", width=12).pack(side='left', padx=(20, 0))
        self.tolerance_pct_entry = ttk.Entry(row3, width=10)
        self.tolerance_pct_entry.pack(side='left', padx=5)
        self.tolerance_pct_entry.insert(0, str(self.default_tolerance_pct))

        row4 = ttk.Frame(rule_frame)
        row4.pack(fill='x', pady=3)
        ttk.Label(row4, text="控件类型限制:", width=12).pack(side='left')
        self.match_ctrl_entry = ttk.Entry(row4, width=20)
        self.match_ctrl_entry.pack(side='left', padx=5)

        ttk.Label(row4, text="ID限制:", width=8).pack(side='left', padx=(10, 0))
        self.match_id_entry = ttk.Entry(row4, width=20)
        self.match_id_entry.pack(side='left', padx=5)

        btn_frame = ttk.Frame(self.root, padding=10)
        btn_frame.pack(fill='x', padx=10)
        ttk.Button(btn_frame, text="📋 预览并生成 JSON", command=self._generate_json).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="💾 添加到列表", command=self._add_to_list).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="📁 导出所有", command=self._export_file).pack(side='right', padx=5)

        list_frame = ttk.LabelFrame(self.root, text="📝 已生成的规则列表", padding=10)
        list_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self.rules_listbox = tk.Listbox(list_frame, font=('Consolas', 9), selectmode='extended')
        self.rules_listbox.pack(side='left', fill='both', expand=True)

        self.status_var = tk.StringVar(value="就绪 | 已更新窗口尺寸与预览功能")
        ttk.Label(self.root, textvariable=self.status_var, relief='sunken', anchor='w').pack(fill='x', side='bottom')

    def _make_grid_row(self, parent, label_text, row_idx, width=12):
        ttk.Label(parent, text=label_text, width=15).grid(row=row_idx, column=0, sticky='e', pady=3)
        entry = ttk.Entry(parent, width=width)
        entry.grid(row=row_idx, column=1, pady=3)
        return entry

    def _load_processes(self):
        self.process_list = WindowProcessManager.get_all_processes()
        self.process_combo['values'] = [p['name'] for p in self.process_list]

    def _on_process_selected(self, event):
        proc_name = self.process_var.get()
        self.window_list = WindowProcessManager.get_windows_by_process(proc_name)
        if self.window_list:
            self.window_combo['values'] = [f"[{w['width']}×{w['height']}] {w['title']}" for w in self.window_list]
            self.window_combo.current(0)
            self._on_window_selected(None)

    def _on_window_selected(self, event):
        idx = self.window_combo.current()
        if idx < 0: return
        win = self.window_list[idx]
        self.window_info = win

        for entry in (self.win_w_entry, self.win_h_entry, self.proc_entry):
            entry.config(state='normal')
            entry.delete(0, 'end')

        self.win_w_entry.insert(0, str(win['width']))
        self.win_h_entry.insert(0, str(win['height']))
        self.proc_entry.insert(0, self.process_var.get())

        for entry in (self.win_w_entry, self.win_h_entry, self.proc_entry):
            entry.config(state='readonly')

    def _start_selection(self):
        if not self.window_info:
            messagebox.showwarning("提示", "请先选择目标窗口！")
            return

        self.root.iconify()
        self.root.after(300, self._show_overlay)

    def _show_overlay(self):
        overlay = ScreenOverlay(self.root, self._on_selection_done)
        overlay.show()

    def _on_selection_done(self, selection):
        self.current_selection = selection
        self.root.deiconify()
        self.root.focus_force()

        info_text = f"✓ 框选区域：({selection['x1']}, {selection['y1']}) → ({selection['x2']}, {selection['y2']}) | 尺寸：{selection['width']}×{selection['height']}"
        self.coord_label.config(text=info_text, foreground='green')

        self.abs_w_entry.delete(0, 'end')
        self.abs_w_entry.insert(0, str(selection['width']))
        self.abs_h_entry.delete(0, 'end')
        self.abs_h_entry.insert(0, str(selection['height']))

        # =========================================
        # [核心优化] 根据用户的框选大小自动计算容差 (Tolerance)
        # 算法：取框选区域宽和高的最大值的一半，加上 5px 的冗余缓冲
        # =========================================
        auto_tol = max(selection['width'], selection['height']) // 2 + 5
        self.tolerance_entry.delete(0, 'end')
        self.tolerance_entry.insert(0, str(auto_tol))

        # 同时计算百分比容差
        win_w = self.window_info.get('width', 1920)
        auto_tol_pct = round(auto_tol / win_w, 3) if win_w > 0 else 0.05
        self.tolerance_pct_entry.delete(0, 'end')
        self.tolerance_pct_entry.insert(0, str(auto_tol_pct))

        self._extract_control_info()

    def _update_ui_fields(self, ctrl_type, auto_id, name, cls_name, abs_x, abs_y, rev_x, rev_y, rel_x, rel_y):
        def set_val(entry, val):
            entry.delete(0, 'end')
            entry.insert(0, str(val))

        set_val(self.ctrl_type_entry, ctrl_type)
        set_val(self.auto_id_entry, auto_id)
        set_val(self.name_entry, name)
        set_val(self.class_entry, cls_name)
        set_val(self.abs_x_entry, int(abs_x))
        set_val(self.abs_y_entry, int(abs_y))
        set_val(self.rev_x_entry, int(rev_x))
        set_val(self.rev_y_entry, int(rev_y))
        set_val(self.rel_x_entry, rel_x)
        set_val(self.rel_y_entry, rel_y)

    def _extract_control_info(self):
        if not self.current_selection: return

        cx, cy = self.current_selection['center_x'], self.current_selection['center_y']

        win_rect = self.window_info.get('rect', (0, 0, 1, 1))
        win_left, win_top = win_rect[0], win_rect[1]
        win_w = self.window_info.get('width', 1)
        win_h = self.window_info.get('height', 1)

        base_x = cx - win_left
        base_y = cy - win_top
        rel_x = round((base_x / win_w) * 100, 1) if win_w > 0 else 0
        rel_y = round((base_y / win_h) * 100, 1) if win_h > 0 else 0
        rev_x = win_w - base_x
        rev_y = win_h - base_y

        self._update_ui_fields("", "", "", "", base_x, base_y, rev_x, rev_y, rel_x, rel_y)
        self.match_ctrl_entry.delete(0, 'end')
        self.match_id_entry.delete(0, 'end')

        control_info = WindowProcessManager.get_control_info_at_point(cx, cy)

        if control_info:
            self._update_ui_fields(
                control_info['ControlTypeName'], control_info['AutomationId'],
                control_info['Name'], control_info['ClassName'],
                control_info['BaselineX'], control_info['BaselineY'],
                control_info['RevX'], control_info['RevY'],
                control_info['RelX'], control_info['RelY']
            )

            # ==========================================
            # [核心修复] 同步更新最新的窗口尺寸，防止旧尺寸污染 Baseline
            # ==========================================
            self.win_w_entry.config(state='normal')
            self.win_w_entry.delete(0, 'end')
            self.win_w_entry.insert(0, str(control_info['WinW']))
            self.win_w_entry.config(state='readonly')

            self.win_h_entry.config(state='normal')
            self.win_h_entry.delete(0, 'end')
            self.win_h_entry.insert(0, str(control_info['WinH']))
            self.win_h_entry.config(state='readonly')

            self.match_ctrl_entry.insert(0, control_info['ControlTypeName'])
            if control_info['AutomationId']:
                self.match_id_entry.insert(0, control_info['AutomationId'])

            self.status_var.set("✓ 控件信息已自动提取 | 请配置规则参数")
        else:
            self.status_var.set("⚠ 未能提取到深层 UI 控件，已降级使用窗口相对计算")

        strategy = "bottom_center"
        if rel_y < 33:
            strategy = "top_left" if rel_x < 33 else "top_right" if rel_x > 66 else "top_center"
        elif rel_y > 66:
            strategy = "bottom_left" if rel_x < 33 else "bottom_right" if rel_x > 66 else "bottom_center"
        else:
            strategy = "center"

        self.strategy_var.set(strategy)

    def _generate_rule_data(self) -> Optional[Dict]:
        try:
            locate_rule = {
                "mode": self.mode_var.get().split()[0],
                "strategy": self.strategy_var.get(),
                "baseline": {
                    "W": int(self.win_w_entry.get()),
                    "H": int(self.win_h_entry.get()),
                    "X": int(self.abs_x_entry.get()),
                    "Y": int(self.abs_y_entry.get())
                }
            }
            if locate_rule["mode"] == 'anchor':
                locate_rule["tolerance"] = int(self.tolerance_entry.get())
            else:
                locate_rule["tolerance"] = int(self.tolerance_entry.get())
                locate_rule["tolerance_pct"] = float(self.tolerance_pct_entry.get())

            match_cond = {"Process": self.proc_entry.get().strip()}
            if self.match_ctrl_entry.get().strip():
                match_cond["ControlTypeName"] = self.match_ctrl_entry.get().strip()
            if self.match_id_entry.get().strip():
                match_cond["AutomationId"] = self.match_id_entry.get().strip()

            return {
                "match": match_cond,
                "locate_rule": locate_rule,
                "intent_tag": self.intent_entry.get().strip()
            }
        except Exception:
            messagebox.showerror("错误", "参数提取失败，请确保框选正常完成。")
            return None

    def _add_to_list(self):
        rule = self._generate_rule_data()
        if not rule: return
        self.rules_list.append(rule)
        txt = f"[{len(self.rules_list)}] {rule['match']['Process']} | {rule['intent_tag']} | Mode:{rule['locate_rule']['mode']}"
        self.rules_listbox.insert('end', txt)

    # [优化 2] 独立的 JSON 预览窗口与复制功能
    def _generate_json(self):
        rule = self._generate_rule_data()
        if not rule: return
        json_str = json.dumps(rule, ensure_ascii=False, indent=2)

        preview_win = tk.Toplevel(self.root)
        preview_win.title("📋 JSON 预览")
        preview_win.geometry("600x450")
        preview_win.transient(self.root) # 保持在主窗口上方
        preview_win.grab_set()           # 模态窗口，拦截其他交互

        # 文本框及滚动条
        text_frame = ttk.Frame(preview_win, padding=10)
        text_frame.pack(fill='both', expand=True)

        text_widget = tk.Text(text_frame, font=('Consolas', 10), wrap='none')
        x_scroll = ttk.Scrollbar(text_frame, orient='horizontal', command=text_widget.xview)
        y_scroll = ttk.Scrollbar(text_frame, orient='vertical', command=text_widget.yview)
        text_widget.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)

        text_widget.grid(row=0, column=0, sticky='nsew')
        y_scroll.grid(row=0, column=1, sticky='ns')
        x_scroll.grid(row=1, column=0, sticky='ew')
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        text_widget.insert('1.0', json_str)
        text_widget.config(state='disabled') # 设置为只读

        # 底部按钮区
        btn_frame = ttk.Frame(preview_win, padding=10)
        btn_frame.pack(fill='x')

        def copy_to_clipboard():
            self.root.clipboard_clear()
            self.root.clipboard_append(json_str)
            messagebox.showinfo("成功", "JSON 数据已复制到剪贴板！", parent=preview_win)

        ttk.Button(btn_frame, text="📋 复制 JSON", command=copy_to_clipboard).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="❌ 关闭", command=preview_win.destroy).pack(side='right', padx=5)

    def _export_file(self):
        if not self.rules_list:
            messagebox.showwarning("提示", "列表为空，请先添加规则！")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON 文件", "*.json")],
            initialfile=f"behavior_rules_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.rules_list, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", f"已导出 {len(self.rules_list)} 条规则")

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    app = BehaviorLabeler()
    app.run()