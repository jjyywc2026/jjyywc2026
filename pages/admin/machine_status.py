# pages/admin/machine_status.py
import flet as ft
import asyncio
import datetime
from .base import AdminBaseTab

STATUS_META = {
    'active':       {'name': '使用中', 'color': '#43A047', 'icon': ft.Icons.COMPUTER},
    'idle':         {'name': '空闲',   'color': '#FB8C00', 'icon': ft.Icons.HOURGLASS_EMPTY},
    'locked':       {'name': '锁屏',   'color': '#1565C0', 'icon': ft.Icons.LOCK},
    'login_screen': {'name': '登录页', 'color': '#757575', 'icon': ft.Icons.PERSON},
    'unknown':      {'name': '未知',   'color': '#9E9E9E', 'icon': ft.Icons.HELP_OUTLINE},
}


class MachineStatusTab(AdminBaseTab):
    """机器状态：查看所有在线机器的实时状态"""

    def __init__(self, page):
        super().__init__(page)
        self._content = None
        self._list_view = None
        self._loading_ring = None

    def build(self):
        self._content = ft.Column(spacing=10, expand=True, scroll=ft.ScrollMode.ADAPTIVE)
        return self._content

    async def load_data(self):
        await self._ensure_table()
        await self._render()

    async def _ensure_table(self):
        """确保 machine_status 表存在"""
        def _do():
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS machine_status (
                    machine_id TEXT PRIMARY KEY,
                    hostname TEXT,
                    status TEXT DEFAULT 'unknown',
                    current_user_id INTEGER DEFAULT 0,
                    current_username TEXT,
                    last_heartbeat TEXT,
                    last_active TEXT,
                    ip_address TEXT,
                    battery_pct INTEGER DEFAULT 100,
                    cpu_pct REAL DEFAULT 0,
                    mem_pct REAL DEFAULT 0,
                    disk_free_gb REAL DEFAULT 0,
                    screen_on INTEGER DEFAULT 1,
                    network_type TEXT
                )
            """)
            for col_sql in [
                "ALTER TABLE machine_status ADD COLUMN current_username TEXT",
                "ALTER TABLE machine_status ADD COLUMN last_active TEXT",
                "ALTER TABLE machine_status ADD COLUMN ip_address TEXT",
                "ALTER TABLE machine_status ADD COLUMN battery_pct INTEGER DEFAULT 100",
                "ALTER TABLE machine_status ADD COLUMN cpu_pct REAL DEFAULT 0",
                "ALTER TABLE machine_status ADD COLUMN mem_pct REAL DEFAULT 0",
                "ALTER TABLE machine_status ADD COLUMN disk_free_gb REAL DEFAULT 0",
                "ALTER TABLE machine_status ADD COLUMN screen_on INTEGER DEFAULT 1",
                "ALTER TABLE machine_status ADD COLUMN network_type TEXT",
            ]:
                try:
                    self.db.execute(col_sql)
                except Exception:
                    pass
        await asyncio.to_thread(_do)

    async def _render(self):
        await asyncio.sleep(0.02)
        self._list_view = ft.ListView(spacing=6, expand=True)
        self._loading_ring = ft.ProgressRing(width=16, height=16, visible=False)

        header = ft.Row([
            ft.Text("机器状态", size=16, weight=ft.FontWeight.BOLD, color='#263238', expand=True),
            self._loading_ring,
            ft.IconButton(ft.Icons.REFRESH, icon_size=18, tooltip="刷新",
                          on_click=lambda e: self.page.run_task(self._load_status)),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)

        self._content.controls = [header, self._list_view]
        self.page.update()
        await self._load_status()

    async def _load_status(self):
        """加载所有机器状态"""
        self._loading_ring.visible = True
        try:
            if self._loading_ring.page is not None:
                self._loading_ring.update()
        except Exception:
            pass

        def _query():
            try:
                return self.db.fetch_all(
                    "SELECT * FROM machine_status ORDER BY last_heartbeat DESC"), None
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

        tiles = []
        now = datetime.datetime.now()
        for r in rows or []:
            mid = r.get('machine_id', '?')
            hostname = r.get('hostname', '?')
            status = r.get('status', 'unknown')
            smeta = STATUS_META.get(status, STATUS_META['unknown'])
            uid = r.get('current_user_id', 0) or 0
            uname = r.get('current_username') or (f"用户{uid}" if uid else "未登录")
            heartbeat = str(r.get('last_heartbeat', ''))[:19]
            ip = r.get('ip_address', '') or '未知'
            battery = r.get('battery_pct', 100)
            cpu = r.get('cpu_pct', 0)
            mem = r.get('mem_pct', 0)
            disk = r.get('disk_free_gb', 0)

            # 在线判断：心跳在5分钟内
            is_online = False
            if heartbeat:
                try:
                    hb_time = datetime.datetime.strptime(heartbeat, '%Y-%m-%d %H:%M:%S')
                    is_online = (now - hb_time).total_seconds() < 300
                except Exception:
                    pass
            online_color = '#43A047' if is_online else '#9E9E9E'
            online_text = '在线' if is_online else '离线'

            # 电量颜色
            if battery <= 20:
                bat_color = '#E53935'
            elif battery <= 50:
                bat_color = '#FB8C00'
            else:
                bat_color = '#43A047'

            tile = ft.Container(
                content=ft.Column([
                    # 第一行：主机名 + 状态 + 在线
                    ft.Row([
                        ft.Icon(ft.Icons.COMPUTER, size=16, color='#455A64'),
                        ft.Text(hostname, size=14, weight=ft.FontWeight.W_700, color='#263238'),
                        ft.Container(
                            content=ft.Text(smeta['name'], size=9, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                            bgcolor=smeta['color'], border_radius=3,
                            padding=ft.padding.symmetric(horizontal=5, vertical=1)),
                        ft.Container(expand=True),
                        ft.Container(
                            content=ft.Row([
                                ft.Container(width=6, height=6, bgcolor=online_color, border_radius=3),
                                ft.Text(online_text, size=10, color=online_color, weight=ft.FontWeight.W_600),
                            ], spacing=3),
                            padding=ft.padding.symmetric(horizontal=6, vertical=2),
                            bgcolor=ft.Colors.with_opacity(0.08, online_color),
                            border_radius=10),
                    ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    # 第二行：用户 + IP + 心跳
                    ft.Row([
                        ft.Icon(ft.Icons.PERSON, size=12, color='#78909C'),
                        ft.Text(uname, size=11, color='#455A64'),
                        ft.Container(width=1),
                        ft.Icon(ft.Icons.LOCATION_ON, size=12, color='#78909C'),
                        ft.Text(ip, size=11, color='#455A64'),
                        ft.Container(expand=True),
                        ft.Icon(ft.Icons.SCHEDULE, size=12, color='#78909C'),
                        ft.Text(heartbeat or '无', size=10, color='#90A4AE'),
                    ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    # 第三行：系统指标
                    ft.Row([
                        self._metric_bar('CPU', cpu, '#1565C0'),
                        self._metric_bar('内存', mem, '#8E24AA'),
                        ft.Container(expand=True),
                        ft.Row([
                            ft.Icon(ft.Icons.BATTERY_FULL, size=14, color=bat_color),
                            ft.Text(f"{battery}%", size=11, color=bat_color, weight=ft.FontWeight.W_600),
                        ], spacing=2),
                        ft.Container(width=8),
                        ft.Row([
                            ft.Icon(ft.Icons.STORAGE, size=14, color='#78909C'),
                            ft.Text(f"C盘 {disk}GB", size=11, color='#455A64'),
                        ], spacing=2),
                    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    # 机器ID
                    ft.Text(f"ID: {mid}", size=9, color='#B0BEC5'),
                ], spacing=4, tight=True),
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                bgcolor=ft.Colors.WHITE, border_radius=10,
                margin=ft.margin.only(bottom=4),
                shadow=ft.BoxShadow(blur_radius=3, color="#0A000000", offset=ft.Offset(0, 1)),
                border=ft.border.all(0.5, ft.Colors.with_opacity(0.06, smeta['color'])),
            )
            tiles.append(tile)

        if not tiles:
            tiles.append(self._empty("暂无机器上报数据"))

        self._list_view.controls = tiles
        self.page.update()

    def _metric_bar(self, label, pct, color):
        """小型指标条"""
        pct = max(0, min(100, float(pct or 0)))
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(label, size=9, color='#78909C'),
                    ft.Text(f"{pct:.0f}%", size=9, color='#455A64', weight=ft.FontWeight.W_600),
                ], spacing=4),
                ft.Container(
                    content=ft.Container(width=60 * pct / 100, bgcolor=color, border_radius=2),
                    width=60, height=4, bgcolor=ft.Colors.GREY_200, border_radius=2),
            ], spacing=2, tight=True),
            width=70)
