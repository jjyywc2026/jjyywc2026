# pages/admin/monitor_events.py
import flet as ft
import asyncio
import datetime
from .base import AdminBaseTab

# 事件类型元数据：颜色、图标、中文名
EVENT_META = {
    'service_start': {'name': '服务启动', 'color': '#43A047', 'icon': ft.Icons.PLAY_ARROW},
    'service_stop':  {'name': '服务停止', 'color': '#757575', 'icon': ft.Icons.STOP},
    'start':         {'name': '启动',   'color': '#43A047', 'icon': ft.Icons.PLAY_ARROW},
    'stop':          {'name': '停止',   'color': '#757575', 'icon': ft.Icons.STOP},
    'restart':       {'name': '重启',   'color': '#1565C0', 'icon': ft.Icons.RESTART_ALT},
    'crash':         {'name': '崩溃',   'color': '#E53935', 'icon': ft.Icons.ERROR},
    'warning':       {'name': '警告',   'color': '#FB8C00', 'icon': ft.Icons.WARNING},
    'exit':          {'name': '退出',   'color': '#6D4C41', 'icon': ft.Icons.EXIT_TO_APP},
    'exit_timed':    {'name': '定时退出', 'color': '#E65100', 'icon': ft.Icons.TIMER_OFF},
    'pause':         {'name': '暂停',   'color': '#78909C', 'icon': ft.Icons.PAUSE},
    'resume':        {'name': '恢复',   'color': '#00897B', 'icon': ft.Icons.PLAY_CIRCLE},
    'shutdown':      {'name': '关机',   'color': '#455A64', 'icon': ft.Icons.POWER_SETTINGS_NEW},
    'lock':          {'name': '锁屏',   'color': '#5C6BC0', 'icon': ft.Icons.LOCK},
    'idle':          {'name': '空闲',   'color': '#78909C', 'icon': ft.Icons.HOURGLASS_EMPTY},
    'active':        {'name': '活跃',   'color': '#00897B', 'icon': ft.Icons.DIRECTIONS_RUN},
    'login':         {'name': '登录',   'color': '#8E24AA', 'icon': ft.Icons.LOGIN},
    'logout':        {'name': '登出',   'color': '#AD1457', 'icon': ft.Icons.LOGOUT},
    'unknown':       {'name': '未知',   'color': '#9E9E9E', 'icon': ft.Icons.HELP_OUTLINE},
}


class MonitorEventsTab(AdminBaseTab):
    """监控事件：查看桌面端 watchdog 上报的所有事件记录"""

    def __init__(self, page):
        super().__init__(page)
        self._content = None
        self._list_view = None
        self._loading_ring = None
        self._all_events = []
        self._filter_type = 'all'

    def build(self):
        self._list_view = ft.ListView(spacing=4, expand=True)
        self._loading_ring = ft.ProgressRing(width=16, height=16, visible=False)
        self._content = ft.Column(spacing=8, expand=True, scroll=ft.ScrollMode.ADAPTIVE)
        return self._content

    async def load_data(self):
        await self._render()

    async def _render(self):
        await asyncio.sleep(0.02)

        # 事件类型筛选下拉
        type_opts = [ft.dropdown.Option(key="all", text="全部类型")]
        for et, meta in EVENT_META.items():
            type_opts.append(ft.dropdown.Option(key=et, text=f"{meta['name']}({et})"))
        self._type_dropdown = ft.Dropdown(
            value=self._filter_type,
            options=type_opts,
            dense=True, border_radius=8,
            text_size=11, content_padding=ft.padding.symmetric(horizontal=8, vertical=0),
            on_change=self._on_filter_change,
            expand=True,
        )

        filter_row = ft.Row([
            ft.Icon(ft.Icons.FILTER_LIST, size=16, color='#78909C'),
            self._type_dropdown,
            self._loading_ring,
        ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        self._content.controls = [filter_row, self._list_view]
        self.page.update()
        await self._load_events()

    def _on_filter_change(self, e):
        self._filter_type = self._type_dropdown.value
        self._render_list()

    async def _load_events(self):
        self._loading_ring.visible = True
        try:
            if self._loading_ring.page is not None:
                self._loading_ring.update()
        except Exception:
            pass

        def _query():
            try:
                rows = self.db.fetch_all(
                    "SELECT * FROM monitor_events ORDER BY id DESC LIMIT 200")
                return rows, None
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

        self._all_events = rows or []
        self._render_list()

    def _render_list(self):
        tiles = []
        filtered = self._all_events
        if self._filter_type != 'all':
            filtered = [e for e in filtered if e.get('event_type', '') == self._filter_type]

        for e in filtered:
            tiles.append(self._event_card(e))

        if not tiles:
            tiles.append(self._empty("暂无监控事件记录\n桌面端 watchdog 运行后自动上报"))

        self._list_view.controls = tiles
        try:
            self.page.update()
        except Exception:
            pass

    def _event_card(self, e):
        """单条事件卡片：优美展示全部14个字段"""
        eid = e.get('id', '?')
        machine_id = e.get('machine_id', '') or ''
        event_type = e.get('event_type', 'unknown') or 'unknown'
        meta = EVENT_META.get(event_type, EVENT_META['unknown'])
        message = e.get('message', '') or ''
        exit_code = e.get('exit_code')
        created_at = str(e.get('created_at', ''))[:19] or '未知'
        hostname = e.get('hostname', '') or '未知'
        uid = e.get('current_user_id', 0) or 0
        uptime_sec = e.get('uptime_seconds', 0) or 0
        restart_count = e.get('restart_count', 0) or 0
        duration_sec = e.get('duration_seconds', 0) or 0
        warning_count = e.get('warning_count', 0) or 0
        ip = e.get('ip_address', '') or '未知'
        version = e.get('version', '') or '未知'

        # 时长格式化
        uptime_str = self._fmt_duration(uptime_sec)
        duration_str = self._fmt_duration(duration_sec)

        # 退出码显示
        exit_str = str(exit_code) if exit_code is not None else '-'
        exit_color = '#43A047' if (exit_code == 0 or exit_code is None) else '#E53935'

        card = ft.Container(
            content=ft.Column([
                # === 顶部：事件类型标签 + 消息 + 时间 ===
                ft.Row([
                    ft.Container(
                        content=ft.Icon(meta['icon'], size=16, color=ft.Colors.WHITE),
                        width=28, height=28, border_radius=6,
                        bgcolor=meta['color'], alignment=ft.alignment.center),
                    ft.Column([
                        ft.Row([
                            ft.Container(
                                content=ft.Text(meta['name'], size=9, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                                bgcolor=meta['color'], border_radius=2,
                                padding=ft.padding.symmetric(horizontal=4, vertical=0.5)),
                            ft.Container(width=4),
                            ft.Text(f"#{eid}", size=9, color='#B0BEC5'),
                            ft.Container(expand=True),
                            ft.Icon(ft.Icons.ACCESS_TIME, size=10, color='#90A4AE'),
                            ft.Text(created_at, size=9, color='#90A4AE'),
                        ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Text(message or '(无消息)', size=12, color='#263238',
                                weight=ft.FontWeight.W_600, overflow=ft.TextOverflow.ELLIPSIS),
                    ], spacing=2, tight=True, expand=True),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START),
                # === 分隔线 ===
                ft.Container(height=0.5, bgcolor=ft.Colors.GREY_200),
                # === 机器信息行 ===
                ft.Row([
                    self._mini_item(ft.Icons.COMPUTER, '主机', hostname, '#1565C0'),
                    self._mini_item(ft.Icons.PERSON, '用户', f"ID:{uid}" if uid > 0 else '未登录', '#7B1FA2'),
                    self._mini_item(ft.Icons.LOCATION_ON, 'IP', ip, '#00838F'),
                ], spacing=4),
                # === 运行指标行 ===
                ft.Row([
                    self._mini_item(ft.Icons.SCHEDULE, '开机', uptime_str, '#5C6BC0'),
                    self._mini_item(ft.Icons.TIMER, '监控运行', duration_str, '#8E24AA'),
                    self._mini_item(ft.Icons.RESTART_ALT, '重启', f"{restart_count}次", '#FB8C00'),
                ], spacing=4),
                # === 其他信息行 ===
                ft.Row([
                    self._mini_item(ft.Icons.CODE, '退出码', exit_str, exit_color),
                    self._mini_item(ft.Icons.WARNING, '警告', f"{warning_count}次", '#E65100' if warning_count > 0 else '#9E9E9E'),
                    self._mini_item(ft.Icons.BUILD, '版本', version, '#757575'),
                ], spacing=4),
                # === 底部：机器ID ===
                ft.Row([
                    ft.Icon(ft.Icons.FINGERPRINT, size=8, color='#B0BEC5'),
                    ft.Text(f"机器ID: {machine_id[:32]}", size=8, color='#B0BEC5',
                            overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                ], spacing=3, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=5, tight=True),
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            bgcolor=ft.Colors.WHITE, border_radius=10,
            margin=ft.margin.only(bottom=4),
            shadow=ft.BoxShadow(blur_radius=4, color="#10000000", offset=ft.Offset(0, 1)),
            border=ft.border.all(1, ft.Colors.with_opacity(0.1, meta['color'])),
            on_click=lambda e, ev=e: self._show_detail(ev),
            ink=True,
        )
        return card

    def _mini_item(self, icon, label, value, color):
        """迷你信息项：图标+标签+值（三列布局用）"""
        return ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=10, color=color),
                ft.Text(f"{label}:", size=8, color='#90A4AE'),
                ft.Text(str(value)[:14], size=9, color='#455A64', weight=ft.FontWeight.W_600,
                        overflow=ft.TextOverflow.ELLIPSIS),
            ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True)

    def _show_detail(self, e):
        """点击卡片弹出完整详情"""
        eid = e.get('id', '?')
        event_type = e.get('event_type', 'unknown') or 'unknown'
        meta = EVENT_META.get(event_type, EVENT_META['unknown'])

        rows = [
            ('事件ID', str(eid)),
            ('事件类型', f"{meta['name']} ({event_type})"),
            ('消息内容', e.get('message', '') or '(无)'),
            ('退出码', str(e.get('exit_code')) if e.get('exit_code') is not None else '-'),
            ('发生时间', str(e.get('created_at', ''))[:19] or '未知'),
            ('主机名', e.get('hostname', '') or '未知'),
            ('当前用户ID', str(e.get('current_user_id', 0) or 0)),
            ('开机时长', self._fmt_duration(e.get('uptime_seconds', 0) or 0)),
            ('重启次数', f"{e.get('restart_count', 0) or 0}次"),
            ('持续时长', self._fmt_duration(e.get('duration_seconds', 0) or 0)),
            ('警告次数', f"{e.get('warning_count', 0) or 0}次"),
            ('IP地址', e.get('ip_address', '') or '未知'),
            ('版本', e.get('version', '') or '未知'),
            ('机器ID', e.get('machine_id', '') or '未知'),
        ]

        content = ft.Column([
            ft.Row([
                ft.Container(
                    content=ft.Icon(meta['icon'], size=20, color=ft.Colors.WHITE),
                    width=36, height=36, border_radius=8,
                    bgcolor=meta['color'], alignment=ft.alignment.center),
                ft.Column([
                    ft.Text(f"{meta['name']}事件 #{eid}", size=15, weight=ft.FontWeight.W_800, color='#263238'),
                    ft.Text(str(e.get('created_at', ''))[:19] or '未知', size=11, color='#90A4AE'),
                ], spacing=2, tight=True),
            ], spacing=10),
            ft.Container(height=0.5, bgcolor=ft.Colors.GREY_200),
            ft.Column([
                ft.Row([
                    ft.Text(label, size=11, color='#78909C', width=80),
                    ft.Text(str(value), size=11, color='#263238', weight=ft.FontWeight.W_500,
                            overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.START)
                for label, value in rows
            ], spacing=4, tight=True, scroll=ft.ScrollMode.ADAPTIVE),
        ], spacing=8, tight=True, width=340)

        dlg = ft.AlertDialog(
            title=ft.Text("事件详情", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=content, padding=4, width=360),
            actions=[ft.TextButton("关闭", on_click=lambda e: self._close_dialog(dlg))],
        )
        self.page.open(dlg)

    @staticmethod
    def _fmt_duration(seconds):
        """秒数转可读时长"""
        seconds = int(seconds or 0)
        if seconds <= 0:
            return '0秒'
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h}时{m}分"
        if m > 0:
            return f"{m}分{s}秒"
        return f"{s}秒"
