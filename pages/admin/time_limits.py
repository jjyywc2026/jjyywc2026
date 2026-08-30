# pages/admin/time_limits.py
import flet as ft
import asyncio
from pages.admin.base import AdminBaseTab

# 三个时间段的配色
SLOT_COLORS = {
    1: {"bg": "#E3F2FD", "text": "#1565C0", "border": "#90CAF9", "name": "时段1"},
    2: {"bg": "#E8F5E9", "text": "#2E7D32", "border": "#A5D6A7", "name": "时段2"},
    3: {"bg": "#FFF3E0", "text": "#E65100", "border": "#FFCC80", "name": "时段3"},
}


class TimeLimitsTab(AdminBaseTab):
    """用户时间限制管理 (User_time_Limits) - 全部字段可编辑，支持新建"""

    def __init__(self, page):
        super().__init__(page)
        self._content = None
        self._list_view = None
        self._ensure_columns()

    def _ensure_columns(self):
        """确保 User_time_Limits 表有 use__computer_start_time / use__computer_end_time 字段"""
        for col, typ in [("use__computer_start_time", "TIME"), ("use__computer_end_time", "TIME")]:
            try:
                self.db.execute(f"ALTER TABLE User_time_Limits ADD COLUMN {col} {typ}")
                print(f"[time_limits] added column {col}")
            except Exception:
                pass

    def build(self):
        self._content = ft.Column(spacing=8, expand=True, scroll=ft.ScrollMode.ADAPTIVE)
        return self._content

    async def load_data(self):
        await self._load()

    def _safe(self, sql, params=None):
        try:
            return self.db.fetch_all(sql, params) or []
        except Exception as e:
            print(f"[time_limits] query fail: {e}")
            return []

    def _safe_one(self, sql, params=None):
        try:
            rows = self.db.fetch_all(sql, params) or []
            return rows[0] if rows else None
        except Exception as e:
            print(f"[time_limits] query one fail: {e}")
            return None

    async def _load(self):
        await asyncio.sleep(0.05)

        def _query():
            return self._safe("""
                SELECT tl.*, u.username
                FROM User_time_Limits tl
                LEFT JOIN users u ON tl.user_id = u.user_id
                ORDER BY tl.user_id
            """)

        rows = await asyncio.to_thread(_query)

        self._list_view = ft.ListView(spacing=2, expand=True)
        tiles = []
        for r in rows or []:
            uid = r.get('user_id', '?')
            uname = r.get('username') or f'用户{uid}'
            daily = f"日限 {r.get('default_daily_limit',0)}/{r.get('max_daily_limit',0)}"
            input_t = f"单次 {r.get('default_input_time',0)}"
            allow_s = r.get('use__computer_start_time', '') or ''
            allow_e = r.get('use__computer_end_time', '') or ''
            allow_txt = f"允许 {allow_s}-{allow_e}" if allow_s and allow_e else "未设允许时段"

            # 时间段用不同颜色标签显示
            slot_chips = []
            for i in range(1, 4):
                s = r.get(f'time_slot_{i}_start', '')
                e = r.get(f'time_slot_{i}_end', '')
                lim = r.get(f'time_slot_{i}_limit', 0)
                if s and e and lim:
                    c = SLOT_COLORS[i]
                    slot_chips.append(ft.Container(
                        content=ft.Text(f"{c['name']} {s}-{e} ({lim}分)",
                                         size=9, color=c["text"], weight=ft.FontWeight.W_600),
                        bgcolor=c["bg"], border=ft.border.all(1, c["border"]),
                        border_radius=4, padding=ft.padding.symmetric(horizontal=4, vertical=1),
                    ))
            if not slot_chips:
                slot_chips.append(ft.Text("无时段", size=9, color=ft.Colors.GREY_400))

            tiles.append(self._list_tile(
                ft.Icon(ft.Icons.SCHEDULE, size=20, color=ft.Colors.ORANGE_600),
                ft.Text(f"{uname} (ID:{uid})", size=12, weight=ft.FontWeight.BOLD),
                ft.Column([
                    ft.Text(f"{daily} · {input_t}", size=9, color=ft.Colors.GREY_500),
                    ft.Text(allow_txt, size=9, color=ft.Colors.PURPLE_600, weight=ft.FontWeight.W_500),
                    ft.Row(slot_chips, spacing=3, wrap=True),
                ], spacing=2),
                trailing=ft.Icon(ft.Icons.ARROW_FORWARD_IOS, size=14, color=ft.Colors.GREY_400),
                on_click=lambda e, row=r: self._edit(row),
            ))
        if not tiles:
            tiles.append(self._empty("暂无时间限制配置"))
        self._list_view.controls = tiles

        self._content.controls = [
            ft.Row([
                ft.Text("用户时间限制", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.ORANGE_800, expand=True),
                self._action_button("新建", ft.Icons.ADD, self._add_new, ft.Colors.ORANGE_600),
            ]),
            self._list_view,
        ]
        self.page.update()

    # ---------- 新建 ----------
    def _add_new(self, e=None):
        """新建时间限制：先选用户"""
        def _query_users():
            return self._safe("SELECT user_id, username FROM users ORDER BY user_id")

        async def _do():
            users = await asyncio.to_thread(_query_users)
            user_opts = [ft.dropdown.Option(key=str(u['user_id']),
                                            text=f"{u['user_id']}:{u.get('username','')}")
                         for u in users]
            user_dd = ft.Dropdown(label="选择用户", options=user_opts,
                                  border_radius=8, expand=True)

            def _on_select(e):
                uid = int(user_dd.value)
                # 检查是否已存在
                existing = self._safe("SELECT 1 FROM User_time_Limits WHERE user_id=?", [uid])
                if existing:
                    self.snack("该用户已有时间限制配置，请直接编辑")
                    self._close_dialog(dlg)
                    return
                # 插入默认空记录（含允许使用时段默认值）
                self.db.execute(
                    "INSERT INTO User_time_Limits (user_id, default_input_time, default_daily_limit, cool_time, use__computer_start_time, use__computer_end_time) VALUES (?,?,?,?,?,?)",
                    [uid, 0, 0, 0, "00:00", "23:59"])
                self._log_operation("add_time_limits", "User_time_Limits", target_id=uid)
                self._close_dialog(dlg)
                self.snack("已创建，请编辑配置")
                # 读取新记录并打开编辑
                row = self._safe("SELECT * FROM User_time_Limits WHERE user_id=?", [uid])
                if row:
                    self._edit(row[0])
                else:
                    self.page.run_task(self._load)

            dlg = ft.AlertDialog(
                title=ft.Text("新建时间限制", size=16, weight=ft.FontWeight.BOLD),
                content=ft.Container(content=ft.Column([user_dd], spacing=8), width=360, padding=4),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                    ft.ElevatedButton("创建", on_click=_on_select,
                                      style=ft.ButtonStyle(bgcolor=ft.Colors.ORANGE_600, color=ft.Colors.WHITE)),
                ],
            )
            self.page.open(dlg)

        self.page.run_task(_do)

    # ---------- 编辑 ----------
    def _edit(self, row):
        uid = row.get('user_id')

        # 字段定义：(标签, 字段名, 类型) — 命名参考桌面版
        field_defs = [
            ("默认单次时长(分)", "default_input_time", "number", "重置后恢复的基础值"),
            ("临时单次时长(分)", "temp_up_input_time", "number", "星星提升后的当前单次上限"),
            ("单次提升增量(分)", "input_time_increment", "number", "每次提升单次上限增加的分钟"),
            ("单次提升星耗", "input_time_star_cost", "number", "每次提升单次上限消耗的星星"),
            ("单次提升到期", "input_time_up_time", "text", "最后提升时间，判断是否重置"),
            ("默认每日上限(分)", "default_daily_limit", "number", "每日重置后恢复的基础值"),
            ("每日上限(分)", "max_daily_limit", "number", "每日上限能提升到的最大值"),
            ("临时每日上限(分)", "temp_up_daily_limit", "number", "星星提升后的当前每日上限"),
            ("每日提升增量(分)", "daily_limit_increment", "number", "每次提升每日上限增加的分钟"),
            ("每日提升星耗", "daily_limit_star_cost", "number", "每次提升每日上限消耗的星星"),
            ("每日提升到期", "daily_limit_up_time", "text", "最后提升时间，跨天自动重置"),
            ("冷却时间(分)", "cool_time", "number", "两次使用之间必须等待的分钟"),
        ]
        # 允许使用时段（User_time_Limits 表字段）
        allow_defs = [
            ("允许使用开始", "use__computer_start_time", "text", "全天允许使用电脑的开始时间 HH:MM"),
            ("允许使用结束", "use__computer_end_time", "text", "全天允许使用电脑的结束时间 HH:MM"),
        ]
        # 时间段字段（分组，带颜色）
        slot_field_defs = [
            (1, "时段1开始", "time_slot_1_start", "时段1结束", "time_slot_1_end", "时段1上限(分)", "time_slot_1_limit"),
            (2, "时段2开始", "time_slot_2_start", "时段2结束", "time_slot_2_end", "时段2上限(分)", "time_slot_2_limit"),
            (3, "时段3开始", "time_slot_3_start", "时段3结束", "time_slot_3_end", "时段3上限(分)", "time_slot_3_limit"),
        ]
        extra_defs = [
            ("限时赋能卡(分)", "temp_slot_boost", "number", "赋能卡临时增加的单次上限分钟"),
            ("赋能卡到期", "temp_slot_boost_expire", "text", "临时提升过期时间，过期自动清零"),
        ]

        refs = {}
        controls = [
            ft.Text(f"用户ID: {uid}  (不可修改)", size=12, color=ft.Colors.GREY_600,
                    weight=ft.FontWeight.W_600),
        ]

        def _colored_tf(label, value, ftype, border_c, label_c, hint=None):
            """生成带颜色区分的输入框"""
            return ft.TextField(
                label=label, value=str(value if value is not None else ''),
                hint_text=hint,
                keyboard_type=ft.KeyboardType.NUMBER if ftype == "number" else ft.KeyboardType.TEXT,
                border_radius=8, expand=True, height=42, text_size=12,
                border_color=border_c,
                focused_border_color=label_c,
                label_style=ft.TextStyle(color=label_c, size=11),
                text_style=ft.TextStyle(color=ft.Colors.GREY_800, size=12),
                cursor_color=label_c,
            )

        # 区域颜色定义
        BASE_C = {"border": ft.Colors.BLUE_200, "label": ft.Colors.BLUE_700}
        ALLOW_C = {"border": ft.Colors.PURPLE_200, "label": ft.Colors.PURPLE_700}
        EXTRA_C = {"border": ft.Colors.PINK_200, "label": ft.Colors.PINK_700}

        # 基础字段（蓝色系）
        controls.append(ft.Container(
            content=ft.Text("基础配置", size=11, color=BASE_C["label"], weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.BLUE_50, border=ft.border.all(1, BASE_C["border"]),
            border_radius=6, padding=ft.padding.symmetric(horizontal=8, vertical=3),
        ))
        for label, key, ftype, hint in field_defs:
            val = row.get(key, '')
            tf = _colored_tf(label, val, ftype, BASE_C["border"], BASE_C["label"], hint=hint)
            refs[key] = tf
            controls.append(tf)

        # 允许使用时段（紫色系，User_time_Limits 表字段）
        controls.append(ft.Container(
            content=ft.Text("允许使用时段", size=11, color=ALLOW_C["label"], weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.PURPLE_50, border=ft.border.all(1, ALLOW_C["border"]),
            border_radius=6, padding=ft.padding.symmetric(horizontal=8, vertical=3),
        ))
        for label, key, ftype, hint in allow_defs:
            val = row.get(key, '')
            tf = _colored_tf(label, val, ftype, ALLOW_C["border"], ALLOW_C["label"], hint=hint)
            refs[key] = tf
            controls.append(tf)

        # 时间段分组（各自颜色）
        for slot_idx, s_label, s_key, e_label, e_key, l_label, l_key in slot_field_defs:
            c = SLOT_COLORS[slot_idx]
            controls.append(ft.Container(
                content=ft.Text(c["name"], size=11, color=c["text"], weight=ft.FontWeight.BOLD),
                bgcolor=c["bg"], border=ft.border.all(1, c["border"]),
                border_radius=6, padding=ft.padding.symmetric(horizontal=8, vertical=3),
            ))
            for label, key, ftype, hint in [(s_label, s_key, "text", "HH:MM"), (e_label, e_key, "text", "HH:MM(支持跨天)"), (l_label, l_key, "number", "此时段内单次上限分钟")]:
                val = row.get(key, '')
                tf = _colored_tf(label, val, ftype, c["border"], c["text"], hint=hint)
                refs[key] = tf
                controls.append(tf)

        # 额外字段（粉色系）
        controls.append(ft.Container(
            content=ft.Text("限时赋能", size=11, color=EXTRA_C["label"], weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.PINK_50, border=ft.border.all(1, EXTRA_C["border"]),
            border_radius=6, padding=ft.padding.symmetric(horizontal=8, vertical=3),
        ))
        for label, key, ftype, hint in extra_defs:
            val = row.get(key, '')
            tf = _colored_tf(label, val, ftype, EXTRA_C["border"], EXTRA_C["label"], hint=hint)
            refs[key] = tf
            controls.append(tf)

        # User_time_Limits 表的所有字段
        tl_keys = [k for _, k, _, _ in field_defs] + [k for _, k, _, _ in extra_defs] + [k for _, k, _, _ in allow_defs]
        for _, _, s_key, _, e_key, _, l_key in slot_field_defs:
            tl_keys += [s_key, e_key, l_key]

        def do_submit(e):
            # 1. 收集 User_time_Limits 所有字段
            vals = {}
            for key in tl_keys:
                v = refs[key].value
                ftype = "number" if any(k == key and t == "number"
                                         for _, k, t, _ in field_defs + extra_defs) else "text"
                if key.endswith('_limit'):
                    ftype = "number"
                if ftype == "number":
                    vals[key] = int(v) if v and str(v).strip() else 0
                else:
                    vals[key] = v or None
            self._close_dialog(dlg)

            def do_save():
                sets = ", ".join(f"{k}=?" for k in vals)
                self.db.execute(f"UPDATE User_time_Limits SET {sets} WHERE user_id=?",
                                list(vals.values()) + [uid])
                before = {k: row.get(k) for k in tl_keys}
                after = dict(vals)
                self._log_operation("edit_time_limits", "User_time_Limits", target_id=uid,
                                    details=f"修改{len(vals)}个字段",
                                    before_state=before, after_state=after)
                # 用户消息通知
                daily = vals.get('default_daily_limit', 0)
                single = vals.get('default_input_time', 0)
                cool = vals.get('cool_time', 0)
                allow_s = vals.get('use__computer_start_time', '00:00')
                allow_e = vals.get('use__computer_end_time', '23:59')
                admin_name = getattr(self.page, '_user_data', {}).get('username', '管理员')
                detail = f"【时间限制更新】\n操作人：{admin_name}\n每日上限：{daily}分钟\n单次上限：{single}分钟\n冷却时间：{cool}分钟\n允许时段：{allow_s} ~ {allow_e}"
                self.db.add_user_message(uid, '时间限制变更', detail, 'timelimit')

            self.run_save_async(do_save, after_fn=lambda: self.page.run_task(self._load))

        dlg = ft.AlertDialog(
            title=ft.Text(f"编辑时间限制 - 用户{uid}", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(controls, spacing=5, scroll=ft.ScrollMode.ADAPTIVE),
                width=420, height=620, padding=4),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.ElevatedButton("保存", on_click=do_submit,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.ORANGE_600, color=ft.Colors.WHITE)),
            ],
        )
        self.page.open(dlg)
