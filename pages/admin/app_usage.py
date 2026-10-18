# pages/admin/app_usage.py
import flet as ft
import asyncio
import datetime
from .base import AdminBaseTab


class AppUsageTab(AdminBaseTab):
    """应用使用统计：查看今天每个程序用了多久、最活跃的是哪个"""

    def __init__(self, page):
        super().__init__(page)
        self._content = None
        self._list_view = None
        self._loading_ring = None
        self._summary_view = None
        self._machine_dropdown = None
        self._all_machines = []
        self._selected_machine = 'all'
        self._selected_range = 'today'  # today/yesterday/3days/7days/30days/all

    DATE_RANGES = [
        ('today', '今天'),
        ('yesterday', '昨天'),
        ('3days', '近3天'),
        ('7days', '近7天'),
        ('30days', '近30天'),
        ('90days', '近90天'),
        ('all', '全部'),
    ]

    def build(self):
        self._list_view = ft.ListView(spacing=4, expand=True)
        self._loading_ring = ft.ProgressRing(width=16, height=16, visible=False)
        self._summary_view = ft.Container()
        self._content = ft.Column(spacing=8, expand=True, scroll=ft.ScrollMode.ADAPTIVE)
        return self._content

    async def load_data(self):
        await self._render()

    async def _render(self):
        await asyncio.sleep(0.02)

        # 机器选择下拉
        machine_opts = [ft.dropdown.Option(key="all", text="全部机器")]
        for m in self._all_machines:
            machine_opts.append(ft.dropdown.Option(key=m, text=m[:24]))
        self._machine_dropdown = ft.Dropdown(
            value=self._selected_machine,
            options=machine_opts,
            dense=True, border_radius=8,
            text_size=11, content_padding=ft.padding.symmetric(horizontal=8, vertical=0),
            on_change=self._on_machine_change,
            expand=True,
        )

        # 日期范围下拉
        range_opts = [ft.dropdown.Option(key=k, text=v) for k, v in self.DATE_RANGES]
        self._range_dropdown = ft.Dropdown(
            value=self._selected_range,
            options=range_opts,
            dense=True, border_radius=8,
            text_size=11, content_padding=ft.padding.symmetric(horizontal=8, vertical=0),
            on_change=self._on_range_change,
            width=90,
        )

        # 刷新按钮
        refresh_btn = ft.IconButton(
            icon=ft.Icons.REFRESH, icon_size=18,
            on_click=lambda e: self.page.run_task(self._load_usage),
            tooltip="刷新",
        )

        filter_row = ft.Row([
            ft.Icon(ft.Icons.COMPUTER, size=16, color='#78909C'),
            self._machine_dropdown,
            self._range_dropdown,
            self._loading_ring,
            refresh_btn,
        ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        self._content.controls = [filter_row, self._summary_view, self._list_view]
        self.page.update()
        await self._load_usage()

    def _on_machine_change(self, e):
        self._selected_machine = self._machine_dropdown.value
        self.page.run_task(self._load_usage)

    def _on_range_change(self, e):
        self._selected_range = self._range_dropdown.value
        self.page.run_task(self._load_usage)

    async def _load_usage(self):
        self._loading_ring.visible = True
        try:
            if self._loading_ring.page is not None:
                self._loading_ring.update()
        except Exception:
            pass

        def _query():
            try:
                today = datetime.date.today()
                # 构建日期筛选条件
                date_cond = ""
                date_params = []
                rng = self._selected_range
                if rng == 'today':
                    date_cond = "date = ?"
                    date_params = [today.strftime('%Y-%m-%d')]
                elif rng == 'yesterday':
                    date_cond = "date = ?"
                    date_params = [(today - datetime.timedelta(days=1)).strftime('%Y-%m-%d')]
                elif rng == '3days':
                    date_cond = "date >= ?"
                    date_params = [(today - datetime.timedelta(days=2)).strftime('%Y-%m-%d')]
                elif rng == '7days':
                    date_cond = "date >= ?"
                    date_params = [(today - datetime.timedelta(days=6)).strftime('%Y-%m-%d')]
                elif rng == '30days':
                    date_cond = "date >= ?"
                    date_params = [(today - datetime.timedelta(days=29)).strftime('%Y-%m-%d')]
                elif rng == '90days':
                    date_cond = "date >= ?"
                    date_params = [(today - datetime.timedelta(days=89)).strftime('%Y-%m-%d')]
                # all: 不筛选日期

                # 获取机器列表
                machines = self.db.fetch_all(
                    "SELECT DISTINCT machine_id FROM app_usage ORDER BY machine_id")
                machine_list = [r['machine_id'] for r in (machines or []) if r.get('machine_id')]

                # 使用统计（按应用聚合，跨天累加）
                base_sql = ("SELECT machine_id, app_name, process_name, "
                            "SUM(total_seconds) as total_seconds, MAX(last_active) as last_active "
                            "FROM app_usage")
                where_parts = []
                params = []
                if date_cond:
                    where_parts.append(date_cond)
                    params.extend(date_params)
                if self._selected_machine != 'all':
                    where_parts.append("machine_id = ?")
                    params.append(self._selected_machine)
                where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
                sql = base_sql + where_sql + " GROUP BY machine_id, app_name ORDER BY total_seconds DESC"
                rows = self.db.fetch_all(sql, params)
                return machine_list, rows or [], None
            except Exception as e:
                return [], [], str(e)

        machines, rows, err = await asyncio.to_thread(_query)
        self._all_machines = machines

        # 更新机器下拉（如果选项变了）
        if self._machine_dropdown:
            current = self._selected_machine
            opts = [ft.dropdown.Option(key="all", text="全部机器")]
            for m in machines:
                opts.append(ft.dropdown.Option(key=m, text=m[:24]))
            self._machine_dropdown.options = opts
            if current not in ['all'] + machines:
                self._selected_machine = 'all'
                self._machine_dropdown.value = 'all'

        self._loading_ring.visible = False
        try:
            if self._loading_ring.page is not None:
                self._loading_ring.update()
        except Exception:
            pass

        if err:
            self.snack(f"加载失败: {err}")
            return

        self._render_summary(rows)
        self._render_list(rows)
        try:
            self.page.update()
        except Exception:
            pass

    def _render_summary(self, rows):
        """汇总统计：总时长、应用数、最活跃应用"""
        if not rows:
            self._summary_view.content = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.INFO_OUTLINE, size=14, color='#90A4AE'),
                    ft.Text("今天暂无应用使用数据", size=11, color='#90A4AE'),
                ], spacing=4),
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                bgcolor=ft.Colors.GREY_50, border_radius=8)
            return

        total_sec = sum(r.get('total_seconds', 0) or 0 for r in rows)
        app_count = len(set(r.get('app_name', '') for r in rows if r.get('app_name')))
        top_app = rows[0] if rows else None
        top_name = top_app.get('app_name', '未知') if top_app else '无'
        top_sec = top_app.get('total_seconds', 0) or 0 if top_app else 0

        total_str = self._fmt_duration(total_sec)
        top_str = self._fmt_duration(top_sec)

        self._summary_view.content = ft.Container(
            content=ft.Row([
                self._summary_item("总使用", total_str, '#1565C0', ft.Icons.SCHEDULE),
                ft.Container(width=1, height=32, bgcolor=ft.Colors.GREY_300),
                self._summary_item("应用数", f"{app_count}个", '#8E24AA', ft.Icons.APPS),
                ft.Container(width=1, height=32, bgcolor=ft.Colors.GREY_300),
                self._summary_item("最活跃", top_name, '#E65100', ft.Icons.WHATSHOT),
            ], spacing=8, alignment=ft.MainAxisAlignment.SPACE_AROUND,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            bgcolor=ft.Colors.with_opacity(0.04, '#1565C0'),
            border_radius=10,
            margin=ft.margin.only(bottom=2))

    @staticmethod
    def _summary_item(label, value, color, icon):
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(icon, size=12, color=color),
                    ft.Text(label, size=9, color='#90A4AE'),
                ], spacing=2),
                ft.Text(value, size=13, color='#263238', weight=ft.FontWeight.W_800,
                        overflow=ft.TextOverflow.ELLIPSIS),
            ], spacing=1, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=1)

    def _render_list(self, rows):
        """应用使用时长排行列表"""
        tiles = []
        for idx, r in enumerate(rows):
            tiles.append(self._usage_card(r, idx))

        if not tiles:
            tiles.append(self._empty("今天暂无应用使用记录\n桌面端上报后自动显示"))

        self._list_view.controls = tiles

    def _usage_card(self, r, rank):
        """单个应用使用卡片"""
        app_name = r.get('app_name', '未知') or '未知'
        process_name = r.get('process_name', '') or ''
        total_sec = r.get('total_seconds', 0) or 0
        last_active = str(r.get('last_active', ''))[:19] or '未知'
        machine_id = r.get('machine_id', '') or ''

        duration_str = self._fmt_duration(total_sec)

        # 排名颜色
        rank_colors = ['#E65100', '#1565C0', '#2E7D32', '#5C6BC0', '#78909C']
        rank_color = rank_colors[min(rank, len(rank_colors) - 1)]
        is_top = rank == 0

        # 进度条（相对于最活跃的应用）
        max_sec = total_sec if is_top else None
        # 进度条在渲染时计算比例

        card = ft.Container(
            content=ft.Column([
                # 顶部：排名 + 应用名 + 时长
                ft.Row([
                    ft.Container(
                        content=ft.Text(f"#{rank + 1}", size=11, color=ft.Colors.WHITE,
                                        weight=ft.FontWeight.W_800),
                        width=26, height=26, border_radius=13,
                        bgcolor=rank_color, alignment=ft.alignment.center),
                    ft.Column([
                        ft.Row([
                            ft.Text(app_name, size=13, color='#263238',
                                    weight=ft.FontWeight.W_700,
                                    overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                            ft.Container(
                                content=ft.Text(duration_str, size=12, color=rank_color,
                                                weight=ft.FontWeight.W_800),
                                bgcolor=ft.Colors.with_opacity(0.08, rank_color),
                                border_radius=4,
                                padding=ft.padding.symmetric(horizontal=6, vertical=2)),
                        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Row([
                            ft.Text(process_name, size=9, color='#90A4AE',
                                    overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                            ft.Icon(ft.Icons.ACCESS_TIME, size=9, color='#B0BEC5'),
                            ft.Text(last_active[11:] if len(last_active) > 11 else last_active,
                                    size=9, color='#B0BEC5'),
                        ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ], spacing=2, tight=True, expand=True),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                # 最活跃标签
                *([ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.WHATSHOT, size=10, color='#E65100'),
                        ft.Text("今日最活跃", size=9, color='#E65100', weight=ft.FontWeight.W_700),
                    ], spacing=2),
                    padding=ft.padding.symmetric(horizontal=6, vertical=1),
                    bgcolor=ft.Colors.with_opacity(0.06, '#E65100'),
                    border_radius=3,
                  )] if is_top else []),
            ], spacing=4, tight=True),
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            bgcolor=ft.Colors.WHITE, border_radius=10,
            margin=ft.margin.only(bottom=4),
            shadow=ft.BoxShadow(blur_radius=4, color="#10000000", offset=ft.Offset(0, 1)),
            border=ft.border.all(1.5, ft.Colors.with_opacity(0.15, rank_color)) if is_top
                   else ft.border.all(1, ft.Colors.with_opacity(0.06, '#000000')),
        )
        return card

    @staticmethod
    def _fmt_duration(seconds):
        """秒数格式化为 时分秒"""
        seconds = int(seconds or 0)
        if seconds <= 0:
            return "0分"
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h}时{m}分"
        elif m > 0:
            return f"{m}分{s}秒" if s > 0 else f"{m}分"
        else:
            return f"{s}秒"

    def _empty(self, text):
        return ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.INBOX, size=40, color='#E0E0E0'),
                ft.Text(text, size=12, color='#9E9E9E', text_align=ft.TextAlign.CENTER),
            ], spacing=8, alignment=ft.MainAxisAlignment.CENTER,
               horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=40, alignment=ft.alignment.center)
