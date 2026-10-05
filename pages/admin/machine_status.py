# pages/admin/machine_status.py
import flet as ft
import asyncio
import datetime
from .base import AdminBaseTab

STATUS_META = {
    'active':       {'name': '使用中', 'color': '#43A047', 'icon': ft.Icons.COMPUTER, 'interval': 15},
    'idle':         {'name': '空闲',   'color': '#FB8C00', 'icon': ft.Icons.HOURGLASS_EMPTY, 'interval': 60},
    'locked':       {'name': '锁屏',   'color': '#1565C0', 'icon': ft.Icons.LOCK, 'interval': 300},
    'login_screen': {'name': '登录页', 'color': '#757575', 'icon': ft.Icons.PERSON, 'interval': 300},
    'unknown':      {'name': '未知',   'color': '#9E9E9E', 'icon': ft.Icons.HELP_OUTLINE, 'interval': 300},
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
        """确保 machine_status 表存在（兼容桌面端上报的完整字段）"""
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
                    os_version TEXT,
                    battery_pct INTEGER DEFAULT 100,
                    cpu_pct REAL DEFAULT 0,
                    mem_pct REAL DEFAULT 0,
                    disk_free_gb REAL DEFAULT 0,
                    disk_total_gb REAL DEFAULT 0,
                    uptime_seconds INTEGER DEFAULT 0,
                    screen_on INTEGER DEFAULT 1,
                    network_type TEXT,
                    version TEXT,
                    login_duration INTEGER DEFAULT 0,
                    group_name TEXT,
                    autostart_enabled INTEGER DEFAULT 0,
                    foreground_app TEXT,
                    last_shutdown TEXT
                )
            """)
            for col_sql in [
                "ALTER TABLE machine_status ADD COLUMN current_username TEXT",
                "ALTER TABLE machine_status ADD COLUMN last_active TEXT",
                "ALTER TABLE machine_status ADD COLUMN ip_address TEXT",
                "ALTER TABLE machine_status ADD COLUMN os_version TEXT",
                "ALTER TABLE machine_status ADD COLUMN battery_pct INTEGER DEFAULT 100",
                "ALTER TABLE machine_status ADD COLUMN cpu_pct REAL DEFAULT 0",
                "ALTER TABLE machine_status ADD COLUMN mem_pct REAL DEFAULT 0",
                "ALTER TABLE machine_status ADD COLUMN disk_free_gb REAL DEFAULT 0",
                "ALTER TABLE machine_status ADD COLUMN disk_total_gb REAL DEFAULT 0",
                "ALTER TABLE machine_status ADD COLUMN uptime_seconds INTEGER DEFAULT 0",
                "ALTER TABLE machine_status ADD COLUMN screen_on INTEGER DEFAULT 1",
                "ALTER TABLE machine_status ADD COLUMN network_type TEXT",
                "ALTER TABLE machine_status ADD COLUMN version TEXT",
                "ALTER TABLE machine_status ADD COLUMN login_duration INTEGER DEFAULT 0",
                "ALTER TABLE machine_status ADD COLUMN group_name TEXT",
                "ALTER TABLE machine_status ADD COLUMN autostart_enabled INTEGER DEFAULT 0",
                "ALTER TABLE machine_status ADD COLUMN foreground_app TEXT",
                "ALTER TABLE machine_status ADD COLUMN last_shutdown TEXT",
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
                rows = self.db.fetch_all(
                    "SELECT * FROM machine_status ORDER BY last_heartbeat DESC")
                # 批量查询对应用户的详细信息
                user_info = {}
                uids = [r.get('current_user_id', 0) for r in (rows or []) if r.get('current_user_id', 0) > 0]
                if uids:
                    placeholders = ','.join(['?'] * len(uids))
                    urows = self.db.fetch_all(
                        f"SELECT user_id, username, nickname, user_type, level_id, score, total_stars, total_time, last_login_date "
                        f"FROM users WHERE user_id IN ({placeholders})", uids)
                    for ur in (urows or []):
                        user_info[ur['user_id']] = ur
                    # 批量查询每个用户最新的登录会话（user_sessions）
                    try:
                        srows = self.db.fetch_all(
                            f"SELECT s.user_id, s.login_time, s.logout_time, s.is_active "
                            f"FROM user_sessions s "
                            f"INNER JOIN (SELECT user_id, MAX(login_time) as max_login FROM user_sessions WHERE user_id IN ({placeholders}) GROUP BY user_id) latest "
                            f"ON s.user_id=latest.user_id AND s.login_time=latest.max_login", uids)
                        for sr in (srows or []):
                            uid = sr['user_id']
                            if uid in user_info:
                                user_info[uid]['_session_login_time'] = sr.get('login_time')
                                user_info[uid]['_session_logout_time'] = sr.get('logout_time')
                                user_info[uid]['_session_is_active'] = sr.get('is_active', 0)
                    except Exception:
                        pass  # user_sessions 表不存在时忽略
                return rows, user_info, None
            except Exception as e:
                return None, {}, str(e)

        rows, user_info, err = await asyncio.to_thread(_query)
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
            uname = r.get('current_username') or ''
            uinfo = user_info.get(uid, {})  # 用户详细信息
            heartbeat = str(r.get('last_heartbeat', ''))[:19]
            last_active = str(r.get('last_active', ''))[:19]
            ip = r.get('ip_address', '') or '未知'
            battery = r.get('battery_pct', 100)
            cpu = r.get('cpu_pct', 0)
            mem = r.get('mem_pct', 0)
            disk_free = r.get('disk_free_gb', 0)
            disk_total = r.get('disk_total_gb', 0)
            uptime_sec = r.get('uptime_seconds', 0) or 0
            fg_app = r.get('foreground_app', '') or ''
            os_ver = r.get('os_version', '') or ''
            autostart = r.get('autostart_enabled', 0)

            # 在线判断：心跳超过2分钟视为电脑离线
            is_online = False
            hb_age = 9999
            if heartbeat:
                try:
                    hb_time = datetime.datetime.strptime(heartbeat, '%Y-%m-%d %H:%M:%S')
                    hb_age = (now - hb_time).total_seconds()
                    is_online = hb_age < 120  # 2分钟内有心跳=电脑在线
                except Exception:
                    pass
            online_color = '#43A047' if is_online else '#9E9E9E'
            online_text = '电脑在线' if is_online else f'电脑离线({int(hb_age//60)}分前)'

            # 登录状态判断：区分"电脑离线"和"登录离线（电脑在线但未登录学习程序）"
            is_logged_in = uid > 0  # 只要有user_id即认为已登录（用户名从users表取）
            # 优先用users表的用户名和昵称
            db_username = uinfo.get('username') or uname or f"用户{uid}"
            if not is_online:
                # 电脑离线：watchdog没运行，不判断登录状态
                login_label = '电脑离线'
                login_color = '#9E9E9E'
                login_icon = ft.Icons.OFFLINE_BOLT
            elif is_logged_in:
                # 电脑在线 + 已登录学习程序（显示用户名+昵称）
                nickname = uinfo.get('nickname') or ''
                display_name = f"{db_username}({nickname})" if nickname else db_username
                login_label = f"学习中: {display_name}"
                login_color = '#43A047'
                login_icon = ft.Icons.SCHOOL
            elif status in ('locked', 'login_screen'):
                # 电脑在线 + 锁屏/登录页（蓝色，区别于离线的灰色）
                login_label = '锁屏中' if status == 'locked' else '登录页'
                login_color = '#1565C0'
                login_icon = ft.Icons.LOCK if status == 'locked' else ft.Icons.PERSON
            else:
                # 电脑在线 + 未登录学习程序（登录离线）
                login_label = '电脑在线·未登录学习程序'
                login_color = '#FB8C00'
                login_icon = ft.Icons.COMPUTER

            # 电量颜色
            if battery <= 20:
                bat_color = '#E53935'
                bat_icon = ft.Icons.BATTERY_ALERT
            elif battery <= 50:
                bat_color = '#FB8C00'
                bat_icon = ft.Icons.BATTERY_FULL
            else:
                bat_color = '#43A047'
                bat_icon = ft.Icons.BATTERY_FULL

            # 开机时长格式化
            uptime_str = self._fmt_duration(uptime_sec)
            # 本次登录学习后的时长（优先用 user_sessions.login_time，回退到 users.last_login_date）
            if uid > 0:
                sess_login = uinfo.get('_session_login_time')
                sess_logout = uinfo.get('_session_logout_time')
                sess_active = uinfo.get('_session_is_active', 0)
                if sess_login:
                    try:
                        # login_time 是 DATETIME 字符串（如 "2026-08-18 18:30:21"）
                        lt = datetime.datetime.strptime(str(sess_login)[:19], '%Y-%m-%d %H:%M:%S')
                        if sess_logout and int(sess_active) == 0:
                            # 已退出：显示退出时的会话时长
                            logout_dt = datetime.datetime.strptime(str(sess_logout)[:19], '%Y-%m-%d %H:%M:%S')
                            login_sec = int((logout_dt - lt).total_seconds())
                            login_str = f"{self._fmt_duration(login_sec)}(已退出)"
                        else:
                            # 活跃中：当前时间 - 登录时间
                            login_sec = int((now - lt).total_seconds())
                            login_str = self._fmt_duration(login_sec) if login_sec > 0 else "刚登录"
                    except Exception:
                        login_str = "未知"
                else:
                    # 回退到 users.last_login_date
                    last_login = uinfo.get('last_login_date', '') or ''
                    if last_login:
                        try:
                            lt = datetime.datetime.strptime(str(last_login)[:19], '%Y-%m-%d %H:%M:%S')
                            login_sec = int((now - lt).total_seconds())
                            login_str = self._fmt_duration(login_sec) if login_sec > 0 else "刚登录"
                        except Exception:
                            login_str = "未知"
                    else:
                        login_str = "未知"
            else:
                login_str = "未登录"

            # 磁盘使用率
            disk_pct = 0
            if disk_total and disk_total > 0:
                disk_pct = round((1 - disk_free / disk_total) * 100, 1)

            # 其他字段
            screen_on = r.get('screen_on', 1)
            screen_str = '亮屏' if screen_on else '息屏'
            charging = r.get('battery_charging', 0)
            charging_str = '充电中' if charging else '未充电'
            version = r.get('version', '') or '未知'
            group_name = r.get('group_name', '') or '默认'
            created_at = str(r.get('created_at', ''))[:19] or '未知'
            last_shutdown = str(r.get('last_shutdown', ''))[:19] or '无'
            net_type = r.get('network_type', '') or '未知'

            tile = ft.Container(
                content=ft.Column([
                    # === 顶部：主机名 + 状态 + 在线 + 电量 ===
                    ft.Row([
                        ft.Container(
                            content=ft.Icon(ft.Icons.COMPUTER, size=20, color=ft.Colors.WHITE),
                            width=32, height=32, border_radius=8,
                            bgcolor=smeta['color'], alignment=ft.alignment.center),
                        ft.Column([
                            ft.Text(hostname, size=15, weight=ft.FontWeight.W_800, color='#263238'),
                            ft.Row([
                                ft.Container(
                                    content=ft.Text(smeta['name'], size=8, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                                    bgcolor=smeta['color'], border_radius=2,
                                    padding=ft.padding.symmetric(horizontal=4, vertical=0.5)),
                                ft.Container(width=4),
                                ft.Container(
                                    content=ft.Row([
                                        ft.Container(width=5, height=5, bgcolor=online_color, border_radius=3),
                                        ft.Text(online_text, size=9, color=online_color, weight=ft.FontWeight.W_600),
                                    ], spacing=3),
                                    padding=ft.padding.symmetric(horizontal=5, vertical=1),
                                    bgcolor=ft.Colors.with_opacity(0.08, online_color), border_radius=8),
                            ], spacing=0),
                        ], spacing=1, tight=True),
                        ft.Container(expand=True),
                        # 电量大图标 + 充电状态
                        ft.Column([
                            ft.Row([
                                ft.Icon(bat_icon, size=20, color=bat_color),
                                ft.Icon(ft.Icons.BOLT, size=10, color='#FFC107') if charging else ft.Container(width=10),
                            ], spacing=1),
                            ft.Text(f"{battery}%", size=10, color=bat_color, weight=ft.FontWeight.W_700),
                        ], spacing=0, alignment=ft.MainAxisAlignment.CENTER,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    # === 分隔线 ===
                    ft.Container(height=0.5, bgcolor=ft.Colors.GREY_200),
                    # === 登录状态 + IP + 最后活跃 ===
                    ft.Row([
                        ft.Icon(login_icon, size=13, color=login_color),
                        ft.Container(
                            content=ft.Text(login_label, size=10, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                            bgcolor=login_color, border_radius=3,
                            padding=ft.padding.symmetric(horizontal=6, vertical=2)),
                        ft.Container(width=6),
                        ft.Icon(ft.Icons.LOCATION_ON, size=12, color='#78909C'),
                        ft.Text(ip, size=11, color='#455A64'),
                        ft.Container(expand=True),
                        ft.Icon(ft.Icons.ACCESS_TIME, size=11, color='#90A4AE'),
                        ft.Text(f"活跃 {last_active or '无'}", size=9, color='#90A4AE'),
                    ], spacing=3, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    # === 系统指标条 ===
                    ft.Row([
                        self._metric_bar('CPU', cpu, '#1565C0', 80),
                        self._metric_bar('内存', mem, '#8E24AA', 80),
                        self._metric_bar('磁盘', disk_pct, '#00838F', 80),
                    ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    # === 详细信息网格（全部字段，3列x多行） ===
                    ft.Container(
                        content=ft.Column([
                            # 第1行：时长类
                            ft.Row([
                                self._info_item(ft.Icons.SCHEDULE, '开机', uptime_str, '#1565C0'),
                                self._info_item(ft.Icons.LOGIN, '本次登录', login_str, '#43A047'),
                                self._info_item(ft.Icons.SCREEN_LOCK_PORTRAIT, '屏幕', screen_str, '#7B1FA2'),
                            ], spacing=4),
                            # 第2行：系统类
                            ft.Row([
                                self._info_item(ft.Icons.SYSTEM_UPDATE, '系统', os_ver or '未知', '#757575'),
                                self._info_item(ft.Icons.WIFI, '网络', net_type, '#757575'),
                                self._info_item(ft.Icons.STORAGE, 'C盘', f'{disk_free}/{disk_total}GB', '#00838F'),
                            ], spacing=4),
                            # 第3行：配置类
                            ft.Row([
                                self._info_item(ft.Icons.AUTORENEW, '自启', '已启用' if autostart else '未启用', '#43A047' if autostart else '#9E9E9E'),
                                self._info_item(ft.Icons.BOLT, '充电', charging_str, '#FFC107' if charging else '#9E9E9E'),
                                self._info_item(ft.Icons.GROUP, '分组', group_name, '#5C6BC0'),
                            ], spacing=4),
                            # 第4行：版本与用户
                            ft.Row([
                                self._info_item(ft.Icons.BUILD, '版本', version, '#757575'),
                                self._info_item(ft.Icons.PERSON, '用户ID', str(uid) if uid > 0 else '未登录', '#1565C0'),
                                self._info_item(ft.Icons.PERSON_OUTLINE, '用户名', db_username if uid > 0 else '未登录', '#1565C0'),
                            ], spacing=4),
                            # 第5行：时间类
                            ft.Row([
                                self._info_item(ft.Icons.FAVORITE, '心跳', heartbeat or '无', '#EF5350'),
                                self._info_item(ft.Icons.POWER_SETTINGS_NEW, '最后关机', last_shutdown, '#757575'),
                                self._info_item(ft.Icons.CREATE, '首次上报', created_at, '#757575'),
                            ], spacing=4),
                        ], spacing=3, tight=True),
                        padding=ft.padding.symmetric(horizontal=8, vertical=6),
                        bgcolor=ft.Colors.GREY_50, border_radius=6),
                    # === 前台应用（如果有） ===
                    *([ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.OPEN_IN_NEW, size=12, color='#FF9800'),
                            ft.Text("前台:", size=10, color='#FB8C00', weight=ft.FontWeight.W_600),
                            ft.Text(fg_app[:50], size=10, color='#455A64',
                                    overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.padding.symmetric(horizontal=8, vertical=4),
                        bgcolor=ft.Colors.with_opacity(0.06, '#FF9800'), border_radius=6,
                    )] if fg_app else []),
                    # === 底部：机器ID ===
                    ft.Row([
                        ft.Icon(ft.Icons.FINGERPRINT, size=8, color='#B0BEC5'),
                        ft.Text(f"机器ID: {mid[:28]}", size=8, color='#B0BEC5'),
                    ], spacing=3, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ], spacing=6, tight=True),
                padding=ft.padding.symmetric(horizontal=14, vertical=12),
                bgcolor=ft.Colors.WHITE, border_radius=12,
                margin=ft.margin.only(bottom=6),
                shadow=ft.BoxShadow(blur_radius=6, color="#15000000", offset=ft.Offset(0, 2)),
                border=ft.border.all(1, ft.Colors.with_opacity(0.08, smeta['color'])),
            )
            tiles.append(tile)

        if not tiles:
            tiles.append(self._empty("暂无机器上报数据\n桌面端 watchdog_service 运行后自动上报"))

        self._list_view.controls = tiles
        self.page.update()

    def _metric_bar(self, label, pct, color, width=70):
        """指标进度条"""
        pct = max(0, min(100, float(pct or 0)))
        bar_w = width - 10
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(label, size=9, color='#78909C', weight=ft.FontWeight.W_500),
                    ft.Container(expand=True),
                    ft.Text(f"{pct:.0f}%", size=9, color='#263238', weight=ft.FontWeight.W_700),
                ], spacing=0),
                ft.Container(
                    content=ft.Container(width=bar_w * pct / 100, bgcolor=color, border_radius=2),
                    width=bar_w, height=5, bgcolor=ft.Colors.GREY_200, border_radius=2),
            ], spacing=2, tight=True),
            width=width)

    @staticmethod
    def _info_item(icon, label, value, color):
        """详细信息项：图标 + 标签 + 值"""
        return ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=11, color=color),
                ft.Text(f"{label}:", size=9, color='#90A4AE'),
                ft.Text(str(value)[:12], size=9, color='#455A64', weight=ft.FontWeight.W_600,
                        overflow=ft.TextOverflow.ELLIPSIS),
            ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True)

    @staticmethod
    def _fmt_duration(seconds):
        """秒数转可读时长"""
        seconds = int(seconds or 0)
        if seconds <= 0:
            return '0分'
        h = seconds // 3600
        m = (seconds % 3600) // 60
        if h > 0:
            return f"{h}时{m}分"
        return f"{m}分"
