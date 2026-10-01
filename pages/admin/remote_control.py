# pages/admin/remote_control.py
import flet as ft
import asyncio
import datetime
from .base import AdminBaseTab

# 命令定义：(command, 显示名, 图标, 颜色, 说明)
COMMANDS = [
    ('exit',     '远程退出', ft.Icons.LOGOUT,         '#E53935', '让客户端立即退出程序'),
    ('restart',  '重启监控', ft.Icons.REFRESH,        '#FB8C00', '重启客户端监控服务'),
    ('shutdown', '远程关机', ft.Icons.POWER_SETTINGS_NEW, '#B71C1C', '关闭客户端所在电脑'),
    ('lock',     '锁屏',     ft.Icons.LOCK,           '#1565C0', '锁定客户端电脑屏幕'),
    ('pause',    '暂停监控', ft.Icons.PAUSE_CIRCLE,   '#F9A825', '暂停使用监控'),
    ('resume',   '恢复监控', ft.Icons.PLAY_CIRCLE,    '#43A047', '恢复使用监控'),
]


class RemoteControlTab(AdminBaseTab):
    """远程控制：向 control_commands 表发送命令，客户端轮询执行"""

    def __init__(self, page):
        super().__init__(page)
        self._content = None
        self._history_list = None
        self._warning_tf = None
        self._loading_ring = None
        self._target_dd = None
        self._users = []  # [(user_id, username)]

    def build(self):
        self._content = ft.Column(spacing=10, expand=True, scroll=ft.ScrollMode.ADAPTIVE)
        return self._content

    async def load_data(self):
        await self._ensure_table()
        await self._load_users()
        await self._render()

    async def _ensure_table(self):
        """确保 control_commands 表存在，含 user_id 字段"""
        def _do():
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS control_commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    processed INTEGER DEFAULT 0,
                    processed_at DATETIME,
                    user_id INTEGER DEFAULT 0
                )
            """)
            # 兼容旧表：逐列添加（已存在则跳过）
            for col_sql in [
                "ALTER TABLE control_commands ADD COLUMN processed_at DATETIME",
                "ALTER TABLE control_commands ADD COLUMN user_id INTEGER DEFAULT 0",
            ]:
                try:
                    self.db.execute(col_sql)
                except Exception:
                    pass
        await asyncio.to_thread(_do)

    async def _load_users(self):
        """加载用户列表"""
        def _query():
            try:
                return self.db.fetch_all("SELECT user_id, username FROM users ORDER BY user_id"), None
            except Exception as e:
                return None, str(e)
        rows, err = await asyncio.to_thread(_query)
        if err:
            self._users = []
            return
        self._users = [(r['user_id'], r.get('username') or f"用户{r['user_id']}") for r in (rows or [])]

    def _target_options(self):
        opts = [ft.dropdown.Option(key="0", text="广播（所有电脑）")]
        for uid, uname in self._users:
            opts.append(ft.dropdown.Option(key=str(uid), text=f"{uid}: {uname}"))
        return opts

    def _current_target_id(self):
        val = self._target_dd.value if self._target_dd else "0"
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    def _target_label(self, uid):
        if uid == 0:
            return "广播"
        for u, n in self._users:
            if u == uid:
                return f"{u}:{n}"
        return f"用户{uid}"

    async def _render(self):
        await asyncio.sleep(0.02)

        # ---- 目标用户选择 ----
        self._target_dd = ft.Dropdown(
            options=self._target_options(), value="0",
            label="目标", border_radius=8, text_size=12, dense=True,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=0),
            expand=True)

        # ---- 命令按钮网格 ----
        btn_rows = []
        row_btns = []
        for i, (cmd, name, icon, color, desc) in enumerate(COMMANDS):
            btn = ft.Container(
                content=ft.Column([
                    ft.Icon(icon, size=22, color=ft.Colors.WHITE),
                    ft.Text(name, size=11, color=ft.Colors.WHITE, weight=ft.FontWeight.W_600),
                ], spacing=3, alignment=ft.MainAxisAlignment.CENTER,
                  horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True),
                bgcolor=color, border_radius=10,
                padding=ft.padding.symmetric(vertical=12, horizontal=4),
                expand=True, alignment=ft.alignment.center,
                on_click=lambda e, c=cmd, n=name: self._send_command(c, n),
                ink=True,
                tooltip=desc,
            )
            row_btns.append(btn)
            if len(row_btns) == 3:
                btn_rows.append(ft.Row(row_btns, spacing=8))
                row_btns = []
        if row_btns:
            btn_rows.append(ft.Row(row_btns, spacing=8))

        # ---- 调整警告次数 ----
        self._warning_tf = ft.TextField(
            hint_text="警告次数（如 5）", prefix_icon=ft.Icons.NOTIFICATIONS_ACTIVE,
            expand=True, border_radius=8, height=40, dense=True,
            keyboard_type=ft.KeyboardType.NUMBER, text_size=13,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=0))
        warning_btn = ft.ElevatedButton(
            "设置警告次数", icon=ft.Icons.SEND, icon_color=ft.Colors.WHITE,
            bgcolor='#7B1FA2', color=ft.Colors.WHITE,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            on_click=self._send_warning)

        # ---- 历史列表 ----
        self._history_list = ft.ListView(spacing=3, expand=True)
        self._loading_ring = ft.ProgressRing(width=16, height=16, visible=False)

        refresh_row = ft.Row([
            ft.Text("命令历史", size=14, weight=ft.FontWeight.W_600, color='#37474F', expand=True),
            self._loading_ring,
            ft.IconButton(ft.Icons.REFRESH, icon_size=18, tooltip="刷新历史",
                          on_click=lambda e: self.page.run_task(self._load_history)),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)

        self._content.controls = [
            ft.Text("远程控制", size=16, weight=ft.FontWeight.BOLD, color='#263238'),
            ft.Container(
                content=self._target_dd,
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                bgcolor=ft.Colors.WHITE, border_radius=10,
                shadow=ft.BoxShadow(blur_radius=4, color="#10000000", offset=ft.Offset(0, 2)),
            ),
            ft.Container(
                content=ft.Column(btn_rows, spacing=8),
                padding=10, bgcolor=ft.Colors.WHITE, border_radius=10,
                shadow=ft.BoxShadow(blur_radius=4, color="#10000000", offset=ft.Offset(0, 2)),
            ),
            ft.Container(
                content=ft.Row([self._warning_tf, warning_btn], spacing=8,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=10, bgcolor=ft.Colors.WHITE, border_radius=10,
                shadow=ft.BoxShadow(blur_radius=4, color="#10000000", offset=ft.Offset(0, 2)),
            ),
            refresh_row,
            self._history_list,
        ]
        self.page.update()
        await self._load_history()

    def _send_command(self, cmd, name):
        """发送普通命令"""
        tid = self._current_target_id()
        target = self._target_label(tid)
        self.confirm_and_run(
            f"发送{name}", f"确定向「{target}」发送「{name}」命令吗？",
            self._do_send, cmd, name, tid,
            success_msg=f"已发送{name} → {target}", loading_msg="发送中...")

    async def _do_send(self, cmd, name, target_id):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.execute(
            "INSERT INTO control_commands (command, created_at, processed, user_id) VALUES (?, ?, 0, ?)",
            (cmd, now, target_id))
        self._log_operation("remote_control", "control_commands",
                            details=f"发送命令:{cmd}({name}) 目标:{target_id}")
        await self._load_history()

    def _send_warning(self, e=None):
        """发送 set_warning 命令"""
        val = (self._warning_tf.value or "").strip()
        if not val:
            self.snack("请输入警告次数")
            return
        try:
            n = int(val)
            if n < 0:
                raise ValueError
        except ValueError:
            self.snack("请输入有效的非负整数")
            return
        tid = self._current_target_id()
        target = self._target_label(tid)
        cmd = f"set_warning:{n}"
        self.confirm_and_run(
            "设置警告次数", f"确定向「{target}」设置警告次数为 {n} 吗？",
            self._do_send, cmd, f"设置警告次数={n}", tid,
            success_msg=f"已发送设置警告次数={n} → {target}", loading_msg="发送中...")

    async def _load_history(self):
        """加载最近50条命令历史（含目标用户名）"""
        self._loading_ring.visible = True
        try:
            if self._loading_ring.page is not None:
                self._loading_ring.update()
        except Exception:
            pass

        def _query():
            try:
                return self.db.fetch_all(
                    "SELECT cc.id, cc.command, cc.created_at, cc.processed, cc.processed_at, "
                    "cc.user_id, u.username "
                    "FROM control_commands cc "
                    "LEFT JOIN users u ON cc.user_id=u.user_id "
                    "ORDER BY cc.id DESC LIMIT 50"), None
            except Exception as e:
                return None, str(e)

        rows, err = await asyncio.to_thread(_query)
        self._loading_ring.visible = False
        try:
            if self._loading_ring.page is not None:
                self._loading_ring.update()
        except Exception:
            pass

        if err:
            self.snack(f"加载失败: {err}")
            return

        cmd_name = {c: n for c, n, _, _, _ in COMMANDS}

        tiles = []
        for r in rows or []:
            cmd = r.get('command', '')
            name = cmd_name.get(cmd, cmd)
            if cmd.startswith('set_warning:'):
                name = f"设置警告次数={cmd.split(':', 1)[1]}"
            created = str(r.get('created_at', ''))[:19]
            processed = r.get('processed', 0)
            is_done = (processed == 1 or processed == '1')
            status_color = '#43A047' if is_done else '#F57C00'
            status_text = '已执行' if is_done else '等待执行'
            processed_at = r.get('processed_at')
            processed_str = f" · 执行于 {str(processed_at)[:19]}" if processed_at else ""

            # 目标用户
            uid = r.get('user_id', 0) or 0
            if uid == 0:
                target_text = "广播"
                target_color = '#6A1B9A'
            else:
                uname = r.get('username') or f"用户{uid}"
                target_text = f"{uid}:{uname}"
                target_color = '#1565C0'

            tile = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text(name, size=13, weight=ft.FontWeight.W_700, color='#263238'),
                        ft.Container(
                            content=ft.Text(target_text, size=9, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                            bgcolor=target_color, border_radius=3,
                            padding=ft.padding.symmetric(horizontal=5, vertical=1)),
                        ft.Container(expand=True),
                        ft.Container(
                            content=ft.Text(status_text, size=9, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                            bgcolor=status_color, border_radius=3,
                            padding=ft.padding.symmetric(horizontal=5, vertical=1)),
                    ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([
                        ft.Icon(ft.Icons.SCHEDULE, size=10, color=ft.Colors.GREY_400),
                        ft.Text(f"发送于 {created}{processed_str}", size=10, color=ft.Colors.GREY_500),
                        ft.Container(expand=True),
                        ft.Text(f"#{r.get('id','')}", size=9, color=ft.Colors.GREY_300),
                    ], spacing=3, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ], spacing=2, tight=True),
                padding=ft.padding.symmetric(horizontal=10, vertical=7),
                bgcolor=ft.Colors.WHITE, border_radius=8,
                margin=ft.margin.only(bottom=3),
                border=ft.border.all(0.5, ft.Colors.with_opacity(0.08, status_color)),
            )
            tiles.append(tile)

        if not tiles:
            tiles.append(self._empty("暂无命令记录"))

        self._history_list.controls = tiles
        self.page.update()
