import flet as ft
import asyncio
import datetime
from pages.admin.base import AdminBaseTab


class CardSettingsTab(AdminBaseTab):
    """赋能卡使用设置：按用户隔离 - app_config(宽表) + 允许使用日期(可折叠)"""

    # 字段定义：(字段名, 标签, 类型, 默认值, 提示)
    CONFIG_FIELDS = [
        ("time_slot_card_item_id", "赋能卡物品ID", "number", 1001, "背包中识别哪张卡是赋能卡"),
        ("time_slot_card_increment_minutes", "每张提升分钟", "number", 10, "用1张卡，时段上限+N分钟"),
        ("time_slot_card_max_limit", "提升后上限(分)", "number", 120, "时段限制+赋能提升不能超过此值"),
        ("time_slot_card_expire_time", "提升每日过期时间", "text", "23:59:59", "到该时间临时提升清零"),
        ("max_use_until_time", "最长可用到次日", "text", "00:30", "当天最多用到次日几点"),
    ]
    WINDOW_FIELDS = [
        ("time_window_start", "窗口开始时间", "text", "00:00", "HH:MM"),
        ("time_window_end", "窗口结束时间", "text", "23:59", "HH:MM"),
        ("time_window_enabled", "窗口是否启用", "select", 0, "0=禁用 1=启用"),
    ]

    def __init__(self, page):
        super().__init__(page)
        self._dates_list = None
        self._config_card = None
        self._window_card = None
        self._config_data = None
        self._dates_expanded = True
        self._dates_header = None
        self._dates_container = None
        self._user_dd = None
        self._current_uid = None
        self._users = []
        self._ensure_table()

    def _ensure_table(self):
        """确保 app_config 宽表存在"""
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS app_config (
                    user_id INTEGER PRIMARY KEY,
                    time_slot_card_item_id INTEGER DEFAULT 1001,
                    time_slot_card_increment_minutes INTEGER DEFAULT 10,
                    time_slot_card_max_limit INTEGER DEFAULT 120,
                    time_slot_card_expire_time TEXT DEFAULT '23:59:59',
                    max_use_until_time TEXT DEFAULT '00:30',
                    time_window_start TEXT DEFAULT '00:00',
                    time_window_end TEXT DEFAULT '23:59',
                    time_window_enabled INTEGER DEFAULT 0,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # card_allowed_dates 表（每个用户可独立设置同一日期）
            try:
                self.db.execute("""
                    CREATE TABLE IF NOT EXISTS card_allowed_dates (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        allowed_date TEXT NOT NULL,
                        description TEXT,
                        user_id INTEGER NOT NULL DEFAULT 0
                    )
                """)
            except Exception:
                pass
            # card_allowed_dates 加 user_id（兼容旧表）
            try:
                self.db.execute("ALTER TABLE card_allowed_dates ADD COLUMN user_id INTEGER DEFAULT 0")
            except Exception:
                pass
            # 唯一索引：每个用户每个日期只能有一条（不同用户可同一天）
            try:
                self.db.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_card_dates_user_date ON card_allowed_dates(user_id, allowed_date)")
            except Exception:
                pass
        except Exception as e:
            print(f"[card_settings] ensure_table fail: {e}")

    def _ensure_user_row(self, user_id):
        """确保用户有配置行，不存在则插入默认值"""
        try:
            row = self.db.fetch_one("SELECT user_id FROM app_config WHERE user_id=?", [user_id])
            if not row:
                self.db.execute(
                    """INSERT INTO app_config (user_id) VALUES (?)""", [user_id])
        except Exception as e:
            print(f"[card_settings] ensure_user_row fail: {e}")

    def build(self):
        self._dates_list = ft.Column(spacing=2, tight=True)
        self._config_card = ft.Container()
        self._window_card = ft.Container()
        self._user_dd = ft.Dropdown(
            label="选择用户", border_radius=8, expand=True,
            on_change=self._on_user_change,
        )

        self._dates_header = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CALENDAR_MONTH, size=16, color=ft.Colors.PURPLE_600),
                ft.Text("允许使用日期", size=13, weight=ft.FontWeight.W_600,
                        color=ft.Colors.GREY_700, expand=True),
                self._action_button("添加日期", ft.Icons.ADD, self._add_date,
                                    ft.Colors.PURPLE_600),
                ft.IconButton(
                    icon=ft.Icons.EXPAND_MORE, icon_size=20,
                    icon_color=ft.Colors.GREY_500, on_click=self._toggle_dates,
                ),
            ], spacing=4),
            padding=ft.padding.symmetric(horizontal=4, vertical=4),
            on_click=self._toggle_dates,
        )
        self._dates_container = ft.Container(content=self._dates_list)

        self._scroll_col = ft.Column([
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.CONFIRMATION_NUMBER, size=20, color=ft.Colors.PURPLE_600),
                        ft.Text("赋能卡使用设置", size=15, weight=ft.FontWeight.W_700,
                                color=ft.Colors.PURPLE_800),
                        ft.Container(expand=True),
                    ], spacing=6),
                    self._user_dd,
                ], spacing=6, tight=True),
                padding=ft.padding.symmetric(horizontal=4, vertical=4),
            ),
            self._config_card,
            ft.Container(height=1),
            self._window_card,
            ft.Container(height=1),
            self._dates_header,
            self._dates_container,
        ], spacing=4, scroll=ft.ScrollMode.ADAPTIVE, expand=True)

        return self._scroll_col

    def _on_user_change(self, e):
        if self._user_dd.value:
            self._current_uid = int(self._user_dd.value)
            self.page.run_task(self._reload)

    def _toggle_dates(self, e=None):
        self._dates_expanded = not self._dates_expanded
        self._dates_container.visible = self._dates_expanded
        for c in self._dates_header.content.controls:
            if isinstance(c, ft.IconButton):
                c.icon = ft.Icons.EXPAND_MORE if self._dates_expanded else ft.Icons.CHEVRON_RIGHT
                break
        self.page.update()

    async def load_data(self):
        def _load_users():
            try:
                return self.db.fetch_all("SELECT user_id, username FROM users ORDER BY user_id") or []
            except Exception:
                return []
        self._users = await asyncio.to_thread(_load_users)
        self._user_dd.options = [
            ft.dropdown.Option(key=str(u['user_id']),
                               text=f"{u['user_id']}: {u.get('username','')}")
            for u in self._users
        ]
        if self._users and self._current_uid is None:
            self._current_uid = int(self._users[0]['user_id'])
            self._user_dd.value = str(self._current_uid)
        await self._reload()

    async def _reload(self):
        if self._current_uid is None:
            return
        await asyncio.sleep(0.05)
        uid = self._current_uid
        self._ensure_user_row(uid)

        def _query():
            try:
                cfg = self.db.fetch_one("SELECT * FROM app_config WHERE user_id=?", [uid])
                dates = self.db.fetch_all(
                    "SELECT * FROM card_allowed_dates WHERE user_id=? ORDER BY allowed_date DESC", [uid])
                return cfg, dates, None
            except Exception as e:
                return None, None, str(e)

        cfg, dates, err = await asyncio.to_thread(_query)
        if err:
            self.snack(f"加载失败: {err}")
            return
        self._config_data = cfg or {}
        self._render_config()
        self._render_window()
        self._render_dates(dates)
        self.page.update()

    # ---------- 赋能卡配置 ----------
    def _render_config(self):
        cfg = self._config_data
        items = []
        for key, label, ftype, default, hint in self.CONFIG_FIELDS:
            val = cfg.get(key, default) if cfg else default
            items.append(ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(label, size=11, color=ft.Colors.GREY_700, weight=ft.FontWeight.W_500),
                        ft.Text(hint, size=8, color=ft.Colors.GREY_400),
                    ], spacing=0, expand=True),
                    ft.Container(
                        content=ft.Text(str(val), size=13, color=ft.Colors.PURPLE_800,
                                        weight=ft.FontWeight.W_700),
                        bgcolor='#F3E8FF', border_radius=6,
                        padding=ft.padding.symmetric(horizontal=10, vertical=4),
                    ),
                ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
            ))

        self._config_card.content = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.SETTINGS, size=16, color=ft.Colors.PURPLE_500),
                    ft.Text("赋能卡配置", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_800),
                    ft.Container(expand=True),
                    ft.IconButton(ft.Icons.EDIT, icon_size=16, icon_color=ft.Colors.PURPLE_500,
                                  on_click=lambda e: self._edit_config()),
                ], spacing=4),
                ft.Column(items, spacing=2, tight=True),
            ], spacing=6, tight=True),
            padding=10, bgcolor=ft.Colors.WHITE, border_radius=10,
            border=ft.border.all(1, ft.Colors.PURPLE_100),
            shadow=ft.BoxShadow(blur_radius=6, color="#10000000", offset=ft.Offset(0, 1)),
        )

    def _edit_config(self):
        cfg = self._config_data or {}
        refs = {}
        controls = []
        for key, label, ftype, default, hint in self.CONFIG_FIELDS:
            val = cfg.get(key, default)
            tf = ft.TextField(
                label=label, value=str(val if val is not None else default),
                hint_text=hint, border_radius=8,
                keyboard_type=ft.KeyboardType.NUMBER if ftype == "number" else ft.KeyboardType.TEXT,
            )
            refs[key] = tf
            controls.append(tf)

        def do_save(e):
            vals = {}
            for key, label, ftype, default, hint in self.CONFIG_FIELDS:
                v = refs[key].value
                if ftype == "number":
                    vals[key] = int(v) if v and str(v).strip() else default
                else:
                    vals[key] = (v or '').strip() or str(default)
            try:
                cols = ", ".join(vals.keys())
                placeholders = ", ".join(["?"] * len(vals))
                update_set = ", ".join(f"{k}=excluded.{k}" for k in vals)
                self.db.execute(
                    f"INSERT INTO app_config (user_id, {cols}, updated_at) VALUES (?, {placeholders}, CURRENT_TIMESTAMP) "
                    f"ON CONFLICT(user_id) DO UPDATE SET {update_set}, updated_at=CURRENT_TIMESTAMP",
                    [self._current_uid] + list(vals.values()))
                self._log_operation("edit_app_config", "app_config",
                                    target_id=self._current_uid,
                                    details=f"修改{len(vals)}个配置项",
                                    before_state={k: cfg.get(k) for k in vals},
                                    after_state=dict(vals))
                # 用户消息通知
                inc = vals.get('time_slot_card_increment_minutes', 0)
                mx = vals.get('time_slot_card_max_limit', 0)
                expire = vals.get('time_slot_card_expire_time', '23:59:59')
                max_use = vals.get('max_use_until_time', '00:30')
                admin_name = getattr(self.page, '_user_data', {}).get('username', '管理员')
                detail = f"【赋能卡配置更新】\n操作人：{admin_name}\n每张提升：{inc}分钟\n提升上限：{mx}分钟\n每日过期：{expire}\n最长可用到次日：{max_use}"
                self.db.add_user_message(self._current_uid, '赋能卡配置变更', detail, 'card')
                self.snack("保存成功")
                self._close_dialog(dlg)
                self.page.run_task(self._reload)
            except Exception as ex:
                self.snack(f"保存失败: {ex}")

        dlg = ft.AlertDialog(
            title=ft.Text("编辑赋能卡配置", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(controls, spacing=8, scroll=ft.ScrollMode.ADAPTIVE),
                width=360, height=420, padding=4),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.ElevatedButton("保存", on_click=do_save,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.PURPLE_600, color=ft.Colors.WHITE)),
            ],
        )
        self.page.open(dlg)

    # ---------- 时间窗口 ----------
    def _render_window(self):
        cfg = self._config_data or {}
        enabled = bool(cfg.get('time_window_enabled', 0))
        start = cfg.get('time_window_start', '00:00')
        end = cfg.get('time_window_end', '23:59')
        status_color = ft.Colors.GREEN_600 if enabled else ft.Colors.GREY_400
        status_text = "已启用" if enabled else "已禁用"

        self._window_card.content = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.SCHEDULE, size=18, color=ft.Colors.PURPLE_500),
                    ft.Text("每日使用时间窗口", size=13, weight=ft.FontWeight.W_600,
                            color=ft.Colors.GREY_800),
                    ft.Container(expand=True),
                    ft.Container(
                        content=ft.Text(status_text, size=10, color=ft.Colors.WHITE,
                                        weight=ft.FontWeight.W_600),
                        bgcolor=status_color, border_radius=10,
                        padding=ft.padding.symmetric(horizontal=8, vertical=2),
                    ),
                    ft.IconButton(ft.Icons.EDIT, icon_size=18, icon_color=ft.Colors.PURPLE_500,
                                  on_click=lambda e: self._edit_window()),
                ], spacing=6),
                ft.Row([
                    ft.Container(
                        content=ft.Column([
                            ft.Text("开始时间", size=9, color=ft.Colors.GREY_500),
                            ft.Text(str(start), size=18, weight=ft.FontWeight.W_700,
                                    color=ft.Colors.PURPLE_700),
                        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        expand=True, alignment=ft.alignment.center,
                        padding=8, bgcolor='#F3E8FF', border_radius=8,
                    ),
                    ft.Icon(ft.Icons.ARROW_FORWARD, size=16, color=ft.Colors.GREY_400),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("结束时间", size=9, color=ft.Colors.GREY_500),
                            ft.Text(str(end), size=18, weight=ft.FontWeight.W_700,
                                    color=ft.Colors.PURPLE_700),
                        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        expand=True, alignment=ft.alignment.center,
                        padding=8, bgcolor='#F3E8FF', border_radius=8,
                    ),
                ], spacing=8),
            ], spacing=8),
            padding=12, bgcolor=ft.Colors.WHITE, border_radius=10,
            border=ft.border.all(1, ft.Colors.PURPLE_100),
            shadow=ft.BoxShadow(blur_radius=6, color="#10000000", offset=ft.Offset(0, 1)),
        )

    def _edit_window(self):
        cfg = self._config_data or {}
        start_tf = ft.TextField(label="开始时间", value=str(cfg.get('time_window_start', '00:00')),
                                border_radius=8, hint_text="HH:MM")
        end_tf = ft.TextField(label="结束时间", value=str(cfg.get('time_window_end', '23:59')),
                              border_radius=8, hint_text="HH:MM")
        enabled_dd = ft.Dropdown(
            label="是否启用", border_radius=8,
            options=[ft.dropdown.Option("0", "禁用（不限制时间段）"),
                     ft.dropdown.Option("1", "启用（只能在窗口内用）")],
            value=str(cfg.get('time_window_enabled', 0)),
        )

        def do_save(e):
            start = (start_tf.value or '').strip()
            end = (end_tf.value or '').strip()
            en = int(enabled_dd.value or 0)
            if not start or not end:
                self.snack("请填写开始和结束时间")
                return
            try:
                self.db.execute(
                    """UPDATE app_config SET time_window_start=?, time_window_end=?,
                       time_window_enabled=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?""",
                    [start, end, en, self._current_uid])
                self._log_operation("edit_time_window", "app_config",
                                    target_id=self._current_uid,
                                    details=f"{start}~{end} 启用:{en}",
                                    before_state={k: cfg.get(k) for k in
                                                  ['time_window_start', 'time_window_end', 'time_window_enabled']},
                                    after_state={'time_window_start': start, 'time_window_end': end,
                                                 'time_window_enabled': en})
                # 用户消息通知
                status = '已启用' if en == 1 else '已禁用'
                admin_name = getattr(self.page, '_user_data', {}).get('username', '管理员')
                detail = f"【使用时间窗口】{status}\n操作人：{admin_name}\n时段：{start} ~ {end}"
                self.db.add_user_message(self._current_uid, '时间窗口变更', detail, 'timelimit')
                self.snack("保存成功")
                self._close_dialog(dlg)
                self.page.run_task(self._reload)
            except Exception as ex:
                self.snack(f"保存失败: {ex}")

        dlg = ft.AlertDialog(
            title=ft.Text("时间窗口设置", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([start_tf, end_tf, enabled_dd], spacing=8),
                width=340, padding=4),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.ElevatedButton("保存", on_click=do_save,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.PURPLE_600, color=ft.Colors.WHITE)),
            ],
        )
        self.page.open(dlg)

    # ---------- 允许日期 ----------
    def _render_dates(self, dates):
        tiles = []
        for d in dates or []:
            date_str = d.get('allowed_date', '')
            desc = d.get('description', '') or ''
            tiles.append(self._list_tile(
                ft.Icon(ft.Icons.CALENDAR_TODAY, size=18, color=ft.Colors.PURPLE_500),
                ft.Text(date_str, size=13, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_800),
                ft.Text(desc if desc else '（无描述）', size=10, color=ft.Colors.GREY_500),
                trailing=ft.IconButton(ft.Icons.DELETE, icon_size=16, icon_color=ft.Colors.RED_400,
                                       on_click=lambda e, item=d: self._delete_date(item)),
                on_click=lambda e, item=d: self._edit_date(item),
            ))
        if not tiles:
            tiles.append(self._empty("暂无允许日期，点击右上角添加"))
        self._dates_list.controls = tiles

    def _add_date(self, e=None):
        if self._current_uid is None:
            self.snack("请先选择用户")
            return
        self._open_date_form(None)

    def _edit_date(self, item):
        self._open_date_form(item)

    def _open_date_form(self, item):
        is_edit = item is not None
        today = datetime.date.today().strftime("%Y-%m-%d")
        date_tf = ft.TextField(
            label="日期", value=item.get('allowed_date', today) if is_edit else today,
            hint_text="格式 YYYY-MM-DD", border_radius=8)
        desc_tf = ft.TextField(
            label="描述（可选）", value=item.get('description', '') if is_edit else '',
            border_radius=8)

        def do_save(e):
            d = (date_tf.value or '').strip()
            desc = (desc_tf.value or '').strip()
            if not d:
                self.snack("请填写日期")
                return
            try:
                datetime.datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                self.snack("日期格式错误，请用 YYYY-MM-DD")
                return
            try:
                if is_edit:
                    self.db.execute(
                        "UPDATE card_allowed_dates SET allowed_date=?, description=? WHERE id=?",
                        [d, desc, item['id']])
                    self._log_operation("edit_card_date", "card_allowed_dates",
                                        target_id=item['id'], target_name=d, details=desc,
                                        before_state=dict(item),
                                        after_state={'allowed_date': d, 'description': desc})
                else:
                    exist = self.db.fetch_one(
                        "SELECT id FROM card_allowed_dates WHERE user_id=? AND allowed_date=?",
                        [self._current_uid, d])
                    if exist:
                        self.snack(f"该日期已存在（ID:{exist['id']}）")
                        return
                    self.db.execute(
                        "INSERT INTO card_allowed_dates (user_id, allowed_date, description) VALUES (?, ?, ?)",
                        [self._current_uid, d, desc])
                    self._log_operation("add_card_date", "card_allowed_dates",
                                        target_id=self._current_uid, target_name=d, details=desc,
                                        after_state={'allowed_date': d, 'description': desc})
                self.snack("保存成功")
                self._close_dialog(dlg)
                self.page.run_task(self._reload)
            except Exception as ex:
                self.snack(f"保存失败: {ex}")

        dlg = ft.AlertDialog(
            title=ft.Text("编辑允许日期" if is_edit else "添加允许日期", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=ft.Column([date_tf, desc_tf], spacing=10), width=340, padding=4),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.ElevatedButton("保存", on_click=do_save,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.PURPLE_600, color=ft.Colors.WHITE)),
            ],
        )
        self.page.open(dlg)

    def _delete_date(self, item):
        msg = f"确定删除日期 {item.get('allowed_date', '')} 吗？"
        def _confirm():
            async def _do():
                self.db.execute("DELETE FROM card_allowed_dates WHERE id=?", [item['id']])
                self._log_operation("delete_card_date", "card_allowed_dates",
                                    target_id=item['id'], target_name=item.get('allowed_date', ''),
                                    before_state=dict(item))
                await self._reload()
            self.page.run_task(_do)

        self.confirm_dialog("删除确认", msg, _confirm)
