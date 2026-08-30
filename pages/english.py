# pages/english.py
import flet as ft
import asyncio
from pages.overview import OverviewPage
from pages.heatmap import HeatmapPage
from pages.barchart import BarChartPage
from pages.word_ranking import WordRankingPage
from pages.word_scoring import clear_score_cache

class EnglishPage:
    def __init__(self, page: ft.Page, user_data: dict, filter_state: dict = None):
        self.page = page
        self.user_data = user_data
        self.is_admin = user_data.get('type') == "admin"
        self.loading = page.loading_overlay
        self.db = page._db

        # 过滤器状态（用于概览和用户切换）— 优先读全局page.selected_user_id
        global_uid = getattr(page, 'selected_user_id', None)
        if self.is_admin:
            if global_uid is not None:
                self.selected_user_id = global_uid
            elif filter_state:
                self.selected_user_id = filter_state.get('selected_user_id', user_data.get('id'))
            else:
                self.selected_user_id = user_data.get('id')
            self.selected_grade = (filter_state or {}).get('selected_grade', '全部')
        else:
            self.selected_user_id = user_data.get('id')
            self.selected_grade = '全部'
            if 'home_filter' not in user_data:
                user_data['home_filter'] = {}
            user_data['home_filter']['selected_user_id'] = self.selected_user_id
            user_data['home_filter']['selected_grade'] = self.selected_grade

        # 初始化子页面（传入共享数据）
        self.overview = OverviewPage(page, user_data, self.selected_user_id, self.selected_grade)
        self.heatmap = HeatmapPage(page, user_data, self.selected_user_id, self.is_admin)
        self.barchart = BarChartPage(page, user_data, self.selected_user_id, self.selected_grade)
        self.ranking = WordRankingPage(page, user_data, self.selected_user_id)

        # 用户切换同步：一个标签页切用户，其他页面一起更新
        self.heatmap.on_user_change = self._on_user_changed
        self.barchart.on_user_change = self._on_user_changed
        self.overview.on_user_change = self._on_user_changed
        # 年级切换同步：概览页选年级 → 条形图切到对应年级
        self.overview.on_grade_change = self._on_grade_changed

        # 不在登录时加载，等用户点击英语导航时再查
        self._data_loaded = False
        self._user_list = []
        self._user_name_ref = None

    def _load_users(self):
        if self.is_admin:
            try:
                rows = self.db.fetch_all("SELECT user_id, username FROM users ORDER BY username")
                self._user_list = [(r['user_id'], r['username']) for r in rows] if rows else []
            except Exception:
                self._user_list = []
        else:
            self._user_list = [(self.user_data.get('id'), self.user_data.get('username', '未知'))]

    def _get_selected_user_name(self):
        if self.selected_user_id is None:
            return "全部"
        for uid, name in self._user_list:
            if uid == self.selected_user_id:
                return name
        return self.user_data.get('username', '未知')

    def _open_user_sheet(self, e):
        if not self.is_admin:
            return
        controls = [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.PEOPLE, color=ft.Colors.BLUE_600),
                title=ft.Text("全部", size=15),
                on_click=lambda _: self._select_user(None),
                selected=(self.selected_user_id is None),
            ),
        ]
        for uid, name in self._user_list:
            controls.append(ft.ListTile(
                leading=ft.Icon(ft.Icons.PERSON, color=ft.Colors.GREY_600),
                title=ft.Text(name, size=15),
                on_click=lambda _, u=uid: self._select_user(u),
                selected=(self.selected_user_id == uid),
            ))
        sheet = ft.BottomSheet(
            content=ft.Container(padding=ft.padding.all(16), content=ft.Column([
                ft.Text("选择用户", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800),
                ft.Divider(height=1),
                ft.ListView(controls=controls, height=300),
            ], spacing=8, tight=True)),
            is_scroll_controlled=False, enable_drag=True,
        )
        self.page.open(sheet)

    def _select_user(self, user_id):
        self.selected_user_id = user_id
        self.page.selected_user_id = user_id  # 全局联动
        for o in list(self.page.overlay):
            if isinstance(o, ft.BottomSheet):
                self.page.close(o)
        if self._user_name_ref:
            self._user_name_ref.value = self._get_selected_user_name()
            self._user_name_ref.update()
        self._on_user_changed(user_id)

    def _safe_refresh(self, subpage):
        """安全刷新：控件不在页面上则跳过，防止AssertionError"""
        try:
            # 检查子页面主控件是否已挂载到页面（覆盖所有可能的属性名）
            main_ctrl = None
            for attr in ('_main_container', '_container', '_content', '_body',
                         'chart_container', '_chart_container', 'content'):
                main_ctrl = getattr(subpage, attr, None)
                if main_ctrl is not None:
                    break
            if main_ctrl is not None and getattr(main_ctrl, 'page', None) is None:
                return
            if hasattr(subpage, '_refresh'):
                subpage._refresh()
            elif hasattr(subpage, 'refresh'):
                subpage.refresh()
            elif hasattr(subpage, '_render'):
                subpage._render()
        except Exception as e:
            print(f"[english] safe_refresh跳过: {e}")

    async def _preload_all(self):
        """一次性预加载三个页面所有数据，之后切换秒开"""
        try:
            self.page.loading_overlay.show("加载英语数据...")
        except Exception:
            pass
        await asyncio.sleep(0.12)
        try:
            # 1. 概览
            await self.overview.load_data()

            # 2. 数据查询放到线程池（本地SQLite，快但避免阻塞UI）
            def _preload_data():
                self.heatmap._daily_cache.pop(self.heatmap.heatmap_year, None)
                self.heatmap._get_daily_data(self.heatmap.heatmap_year)
                self.heatmap._get_daily_data(self.heatmap.heatmap_year - 1)
                self.barchart._grade_cache = None
                self.barchart._unit_cache.clear()
                self.barchart._word_cache.clear()
                self.barchart._load_grades()
                for grade in getattr(self.barchart, 'sorted_grades', []):
                    self.barchart._load_units(grade)

            await asyncio.to_thread(_preload_data)

            # 3. UI 构建在主线程（Flet控件非线程安全），控件不在页面则跳过
            self._safe_refresh(self.heatmap)
            self._safe_refresh(self.barchart)
            # 4. 排行页也需要刷新
            self._safe_refresh(self.ranking)
        except Exception as e:
            print(f"[english] 预加载失败: {e}")
        finally:
            try:
                self.page.loading_overlay.hide()
            except Exception:
                pass
            try:
                self.page.update()
            except Exception:
                pass

    def _on_refresh(self, e=None):
        """手动刷新：同步全局user_id+清缓存+重新加载"""
        # 重新从全局读取，确保最新
        global_uid = getattr(self.page, 'selected_user_id', None)
        self.selected_user_id = global_uid
        self.overview.selected_user_id = global_uid
        self.heatmap.selected_user_id = global_uid
        self.barchart.selected_user_id = global_uid
        self.ranking.selected_user_id = global_uid
        if self._user_name_ref:
            self._user_name_ref.value = self._get_selected_user_name()
        self.overview._data_cache = None
        self.heatmap._daily_cache.clear()
        self.barchart._grade_cache = None
        self.barchart._unit_cache.clear()
        self.barchart._word_cache.clear()
        self.ranking._data_cache = None
        self.ranking._cache_time = 0
        self.page.run_task(self._preload_all)

    def _on_tab_change(self, e):
        """切换标签页：数据已预加载，直接刷新（无loading）"""
        idx = e.control.selected_index
        if idx == 1:
            self._safe_refresh(self.heatmap)
        elif idx == 2:
            self._safe_refresh(self.barchart)
        elif idx == 3:
            self._safe_refresh(self.ranking)

    def _on_user_changed(self, user_id):
        """用户切换：清缓存+更新子页面user_id+直接run_task（与国学_on_refresh同款模式）"""
        self.selected_user_id = user_id
        clear_score_cache(user_id)
        self.overview.selected_user_id = user_id
        self.overview._data_cache = None
        self.heatmap.selected_user_id = user_id
        self.heatmap._daily_cache.clear()
        self.barchart.selected_user_id = user_id
        self.barchart._grade_cache = None
        self.barchart._unit_cache.clear()
        self.barchart._word_cache.clear()
        self.barchart._score_cache.clear()
        self.barchart._view = 'grade'
        self.barchart.selected_unit = None
        self.ranking.selected_user_id = user_id
        self.ranking._data_cache = None
        self.ranking._cache_time = 0
        # 更新用户名显示
        if self._user_name_ref:
            self._user_name_ref.value = self._get_selected_user_name()
            try:
                self._user_name_ref.update()
            except Exception:
                pass
        # 直接run_task（国学_on_refresh同款，on_nav_change中调用有效）
        self.page.run_task(self._preload_all)

    def _on_grade_changed(self, grade):
        """年级切换：更新概览和条形图"""
        self.selected_grade = grade
        self.overview.selected_grade = grade
        self.overview._data_cache = None
        self.barchart.selected_grade = grade
        self.barchart._view = 'unit' if grade != '全部' else 'grade'
        self.barchart.selected_unit = None
        self.barchart._word_cache.clear()
        self.barchart._refresh()
        self.page.run_task(self.overview.load_data)

    def build(self):
        # 同步当前user_id到所有子页面（__init__时可能还是旧值）
        self.overview.selected_user_id = self.selected_user_id
        self.heatmap.selected_user_id = self.selected_user_id
        self.barchart.selected_user_id = self.selected_user_id
        self.ranking.selected_user_id = self.selected_user_id
        # 首次点击英语导航时才加载数据，之后读缓存
        if not self._data_loaded:
            self._data_loaded = True
            self._load_users()
            self.page.run_task(self._preload_all)

        tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            indicator_color=ft.Colors.BLUE_600,
            label_color=ft.Colors.BLUE_600,
            unselected_label_color=ft.Colors.GREY_600,
            on_change=self._on_tab_change,
            tabs=[
                ft.Tab(text="概览", icon=ft.Icons.DASHBOARD,
                       content=ft.Container(content=self.overview.build(), padding=ft.padding.only(top=8), expand=True)),
                ft.Tab(text="热力图", icon=ft.Icons.GRID_VIEW,
                       content=ft.Container(content=self.heatmap.build(), padding=ft.padding.only(top=8), expand=True)),
                ft.Tab(text="条形图", icon=ft.Icons.ASSESSMENT,
                       content=ft.Container(content=self.barchart.build(), padding=ft.padding.only(top=8), expand=True)),
                ft.Tab(text="排行", icon=ft.Icons.EMOJI_EVENTS,
                       content=ft.Container(content=self.ranking.build(), padding=ft.padding.only(top=8), expand=True)),
            ],
            expand=True
        )

        # 标题栏（蓝色渐变主题）
        title_icon = ft.Container(
            width=36, height=36, border_radius=10,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                colors=[ft.Colors.BLUE_400, ft.Colors.INDIGO_600]),
            content=ft.Icon(ft.Icons.MENU_BOOK, size=20, color=ft.Colors.WHITE),
            alignment=ft.alignment.center,
        )
        title_bar = ft.Container(
            content=ft.Row([
                title_icon,
                ft.Column([
                    ft.Text("英语学习统计", size=17, weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE, no_wrap=True),
                    ft.Text("单词掌握 · 答题热力 · 排行分析", size=10,
                            color=ft.Colors.with_opacity(0.8, ft.Colors.WHITE), no_wrap=True),
                ], spacing=0, tight=True),
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.REFRESH, icon_size=20, icon_color=ft.Colors.WHITE,
                              on_click=self._on_refresh, tooltip="刷新"),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
            gradient=ft.LinearGradient(
                begin=ft.alignment.center_left, end=ft.alignment.center_right,
                colors=[ft.Colors.BLUE_500, ft.Colors.INDIGO_600, ft.Colors.PURPLE_600]),
            border_radius=12,
            margin=ft.margin.only(bottom=6),
        )

        # 筛选行：用户下拉(左) — 卡片式美化
        filter_controls = []

        # 用户选择（admin：胶囊按钮+底部弹出；普通用户：显示用户名）
        if self.is_admin and self._user_list:
            self._user_name_ref = ft.Text(
                self._get_selected_user_name(), size=13,
                color=ft.Colors.BLUE_800, weight=ft.FontWeight.W_600, no_wrap=True)
            user_btn = ft.Container(
                padding=ft.padding.symmetric(horizontal=12, vertical=6),
                bgcolor=ft.Colors.WHITE, border_radius=24,
                shadow=ft.BoxShadow(blur_radius=8, color="#15000000", offset=ft.Offset(0, 1)),
                on_click=self._open_user_sheet,
                content=ft.Row([
                    ft.Container(width=24, height=24, border_radius=12,
                                 gradient=ft.LinearGradient(
                                     begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                                     colors=[ft.Colors.BLUE_400, ft.Colors.INDIGO_500]),
                                 content=ft.Icon(ft.Icons.PERSON, size=13, color=ft.Colors.WHITE),
                                 alignment=ft.alignment.center),
                    self._user_name_ref,
                    ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=16, color=ft.Colors.BLUE_400),
                ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
            )
            filter_controls.append(user_btn)
        else:
            uname = self.user_data.get('username', '未知')
            filter_controls.append(ft.Container(
                padding=ft.padding.symmetric(horizontal=12, vertical=6),
                bgcolor=ft.Colors.WHITE, border_radius=24,
                shadow=ft.BoxShadow(blur_radius=8, color="#15000000", offset=ft.Offset(0, 1)),
                content=ft.Row([
                    ft.Container(width=24, height=24, border_radius=12,
                                 gradient=ft.LinearGradient(
                                     begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                                     colors=[ft.Colors.BLUE_400, ft.Colors.INDIGO_500]),
                                 content=ft.Icon(ft.Icons.PERSON, size=13, color=ft.Colors.WHITE),
                                 alignment=ft.alignment.center),
                    ft.Text(uname, size=13, color=ft.Colors.BLUE_800, weight=ft.FontWeight.W_600, no_wrap=True),
                ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
            ))

        filter_controls.append(ft.Container(expand=True))

        filter_row = ft.Container(
            content=ft.Row(filter_controls, spacing=6,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER,
                           alignment=ft.MainAxisAlignment.START),
            padding=ft.padding.symmetric(horizontal=10, vertical=4),
        )

        body = ft.Column([title_bar, filter_row, ft.Container(content=tabs, expand=True)],
                         expand=True, spacing=0)

        self._built = ft.Container(
            content=body,
            expand=True,
            padding=ft.padding.all(8),
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                colors=[ft.Colors.BLUE_50, ft.Colors.INDIGO_50, ft.Colors.PURPLE_50, ft.Colors.PINK_50]
            )
        )
        return self._built