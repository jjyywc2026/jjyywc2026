# pages/heatmap.py
import flet as ft
import datetime
import asyncio
import time


# ========== 配色系统 ==========
class _C:
    BG           = "#F0F4F8"
    CARD         = "#FFFFFF"
    PRIMARY      = "#4A90D9"
    PRIMARY_DARK = "#2E6FB5"
    PRIMARY_LT   = "#7EC0F5"
    ACCENT       = "#7C6FF0"
    ACCENT_LT    = "#A59EFF"
    TEXT         = "#2C3E50"
    TEXT_SEC     = "#8A9BB0"
    TEXT_LT      = "#C4CFDD"
    TRACK        = "#EDF1F6"
    # 蓝(冷/少) → 紫 → 橙 → 红(热/多)
    HEAT = ["#ECEFF1", "#4FC3F7", "#7E57C2", "#FF7043", "#E53935"]


class HeatmapPage:
    def __init__(self, page: ft.Page, user_data: dict, selected_user_id, is_admin):
        self.page = page
        self.user_data = user_data
        self.selected_user_id = selected_user_id
        self.is_admin = is_admin
        self.db = page._local_db   # 走本地副本查询

        today = datetime.date.today()
        self.heatmap_year = today.year
        self.view_mode = 'day'   # 'day' | 'week' | 'month'

        self.chart_container = None
        self.mode_buttons = {}
        self._daily_cache = {}   # {year: (timestamp, {date: count})}  5分钟TTL
        self._cache_ttl = 300    # 5分钟
        self._user_name_ref = None  # 用户名Text引用，切换用户时更新
        self._year_sheet = None
        self._year_ref = None
        # 预加载用户列表（admin），确保切换用户后用户名能正确显示
        self._user_list = self._load_user_list() if self.is_admin else []

    # ============================================================
    # 数据（对接数据库）
    # ============================================================
    def _query_uid(self):
        """获取实际查询用的 user_id"""
        return self.selected_user_id if self.selected_user_id is not None else self.user_data.get('id')

    def _get_daily_data(self, year):
        """从 words_answer_records 按日聚合学习次数，带年份缓存（5分钟TTL）"""
        now = time.time()
        if year in self._daily_cache:
            ts, data = self._daily_cache[year]
            if now - ts < self._cache_ttl:
                return data

        uid = self._query_uid()
        data = {}
        try:
            if uid is None:
                # 管理员查看全部用户：聚合所有用户
                rows = self.db.fetch_all(
                    "SELECT DATE(answer_time) as d, COUNT(*) as cnt "
                    "FROM words_answer_records "
                    "WHERE strftime('%Y', answer_time) = ? "
                    "GROUP BY DATE(answer_time) ORDER BY d",
                    [str(year)]
                )
            else:
                rows = self.db.fetch_all(
                    "SELECT DATE(answer_time) as d, COUNT(*) as cnt "
                    "FROM words_answer_records "
                    "WHERE user_id = ? AND strftime('%Y', answer_time) = ? "
                    "GROUP BY DATE(answer_time) ORDER BY d",
                    [uid, str(year)]
                )
            today = datetime.date.today()
            for r in rows:
                d = datetime.date.fromisoformat(r['d'])
                if d <= today:
                    data[d] = int(r['cnt'])
        except Exception as e:
            print(f"[heatmap] 日数据加载失败: {e}")

        self._daily_cache[year] = (now, data)
        return data

    def _get_weekly_data(self, year):
        daily = self._get_daily_data(year)
        if not daily:
            return []
        jan1 = datetime.date(year, 1, 1)
        first_monday = jan1 - datetime.timedelta(days=jan1.weekday())
        if first_monday.year < year:
            first_monday += datetime.timedelta(days=7)
        result = []
        cur = first_monday
        today = datetime.date.today()
        while cur.year <= year and cur <= today:
            we = cur + datetime.timedelta(days=6)
            total = sum(daily.get(cur + datetime.timedelta(days=i), 0) for i in range(7))
            result.append((cur, we, total))
            cur += datetime.timedelta(days=7)
        return result

    def _get_monthly_data(self, year):
        daily = self._get_daily_data(year)
        result = []
        for m in range(1, 13):
            dates = [d for d in daily if d.month == m]
            total = sum(daily[d] for d in dates)
            active = sum(1 for d in dates if daily[d] > 0)
            avg = total / len(dates) if dates else 0
            result.append((m, total, avg, active))
        return result

    # ============================================================
    # 颜色工具
    # ============================================================
    def _heat_color(self, value, max_val):
        if max_val == 0 or value == 0:
            return _C.HEAT[0]
        r = value / max_val
        if r < 0.25: return _C.HEAT[1]
        if r < 0.5:  return _C.HEAT[2]
        if r < 0.75: return _C.HEAT[3]
        return _C.HEAT[4]

    def _bar_gradient(self):
        return ft.LinearGradient(
            begin=ft.alignment.center_left,
            end=ft.alignment.center_right,
            colors=[_C.PRIMARY_LT, _C.PRIMARY],
        )

    # ============================================================
    # 通用控件
    # ============================================================
    def _stat_card(self, icon, value, label, color):
        return ft.Container(
            content=ft.Column([
                ft.Icon(icon, size=18, color=color),
                ft.Text(value, size=15, weight=ft.FontWeight.BOLD, color=_C.TEXT),
                ft.Text(label, size=9, color=_C.TEXT_SEC),
            ], alignment=ft.MainAxisAlignment.CENTER,
               horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=3),
            width=96, padding=ft.padding.symmetric(vertical=10),
            bgcolor=_C.CARD, border_radius=14,
            shadow=ft.BoxShadow(blur_radius=10, color="#12000000"),
        )

    def _bar_row(self, label, value, max_val, tooltip,
                 label_w=74, max_bar_w=220, bar_h=24):
        w = int((value / max_val) * max_bar_w) if max_val > 0 else 0
        bar_color = self._heat_color(value, max_val)
        return ft.Row([
            ft.Container(width=label_w,
                         content=ft.Text(label, size=11, color=_C.TEXT_SEC,
                                         text_align=ft.TextAlign.RIGHT)),
            ft.Stack([
                ft.Container(width=max_bar_w, height=bar_h,
                             bgcolor=_C.TRACK, border_radius=6),
                ft.Container(width=max(w, 3), height=bar_h,
                             bgcolor=bar_color, border_radius=6,
                             tooltip=tooltip,
                             on_click=lambda e, t=tooltip: self._snack(t)),
            ]),
            ft.Container(width=44,
                         content=ft.Text(str(value), size=11, color=_C.TEXT,
                                         weight=ft.FontWeight.W_600)),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _month_tag(self, month):
        """月份标签 + 向下箭头，提示下方数据属于该月"""
        return ft.Container(
            content=ft.Row([
                ft.Text(f"{month}月", size=11, color="white",
                        weight=ft.FontWeight.BOLD),
                ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=18, color="white"),
            ], spacing=0, alignment=ft.MainAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=12, vertical=3),
            gradient=ft.LinearGradient(
                begin=ft.alignment.center_left,
                end=ft.alignment.center_right,
                colors=[_C.PRIMARY_LT, _C.ACCENT]),
            border_radius=8,
        )

    def _month_divider(self):
        return ft.Container(
            height=2,
            gradient=ft.LinearGradient(
                begin=ft.alignment.center_left,
                end=ft.alignment.center_right,
                colors=["#FFFFFF00", _C.ACCENT_LT, _C.ACCENT, _C.ACCENT_LT, "#FFFFFF00"],
            ),
            border_radius=1,
            margin=ft.margin.symmetric(vertical=6),
        )

    # ============================================================
    # 按天：传统日历
    # ============================================================
    def _build_day_view(self):
        daily = self._get_daily_data(self.heatmap_year)
        if not daily:
            return self._empty()

        max_count = max(daily.values())
        today = datetime.date.today()
        cell = 42
        gap = 4
        wd_names = ["一", "二", "三", "四", "五", "六", "日"]

        rows = [
            ft.Row(
                controls=[ft.Container(width=cell, height=24,
                             content=ft.Text(wd, size=10, color=_C.TEXT_SEC,
                                             weight=ft.FontWeight.W_600,
                                             text_align=ft.TextAlign.CENTER),
                             alignment=ft.alignment.center) for wd in wd_names],
                spacing=gap,
            )
        ]

        for month in range(1, 13):
            mdates = [d for d in sorted(daily.keys()) if d.month == month]
            if not mdates:
                continue

            if month > 1:
                rows.append(self._month_divider())

            # 月份标签（带向下箭头）
            rows.append(ft.Container(content=self._month_tag(month),
                                     padding=ft.padding.only(bottom=6)))

            leading = mdates[0].weekday()
            cells = []
            for _ in range(leading):
                cells.append(ft.Container(width=cell, height=cell))
            for d in mdates:
                cnt = daily[d]
                is_today = (d == today)
                tc = "white" if cnt > max_count * 0.25 else _C.TEXT
                cells.append(ft.Container(
                    width=cell, height=cell,
                    bgcolor=self._heat_color(cnt, max_count),
                    border_radius=8,
                    border=ft.border.all(2, _C.ACCENT) if is_today else None,
                    content=ft.Text(str(d.day), size=11, color=tc,
                                    weight=ft.FontWeight.W_700 if is_today else ft.FontWeight.W_500,
                                    text_align=ft.TextAlign.CENTER),
                    alignment=ft.alignment.center,
                    tooltip=f"{d.strftime('%Y-%m-%d')}\n学习次数: {cnt}",
                    on_click=lambda e, dd=d, c=cnt: self._snack(
                        f"{dd.strftime('%Y-%m-%d')} 学习次数: {c}"),
                ))
            while len(cells) % 7 != 0:
                cells.append(ft.Container(width=cell, height=cell))
            for i in range(0, len(cells), 7):
                rows.append(ft.Row(controls=cells[i:i + 7], spacing=gap))

        rows.append(ft.Container(height=10))
        rows.append(self._build_legend())
        return ft.ListView(controls=rows, padding=ft.padding.all(14),
                           spacing=0, expand=True)

    # ============================================================
    # 按周：水平条形图
    # ============================================================
    def _build_week_view(self):
        weekly = self._get_weekly_data(self.heatmap_year)
        if not weekly:
            return self._empty()
        max_val = max(w[2] for w in weekly)

        rows = [
            ft.Text(f"{self.heatmap_year}年 每周学习", size=15,
                    color=_C.TEXT, weight=ft.FontWeight.BOLD),
            ft.Container(height=8),
        ]
        for idx, (ws, we, total) in enumerate(weekly):
            tip = f"第{idx+1}周 ({ws.strftime('%m/%d')}-{we.strftime('%m/%d')})\n学习次数: {total}"
            rows.append(self._bar_row(f"第{idx+1}周", total, max_val, tip))

        rows.append(ft.Container(height=10))
        rows.append(self._build_legend())
        return ft.ListView(controls=rows, padding=ft.padding.all(14),
                           spacing=6, expand=True)

    # ============================================================
    # 按月：水平条形图 + 摘要
    # ============================================================
    def _build_month_view(self):
        monthly = self._get_monthly_data(self.heatmap_year)
        if not monthly:
            return self._empty()

        max_val = max(m[1] for m in monthly)
        year_total = sum(m[1] for m in monthly)
        best = max(monthly, key=lambda x: x[1])

        summary = ft.Row([
            self._stat_card(ft.Icons.STAR, str(year_total), "全年总计", _C.PRIMARY),
            self._stat_card(ft.Icons.SHOW_CHART, f"{year_total/12:.0f}", "月均次数", _C.ACCENT),
            self._stat_card(ft.Icons.CALENDAR_TODAY, f"{best[0]}月", "最高月份", "#E67E22"),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=10)

        rows = [
            ft.Text(f"{self.heatmap_year}年 每月学习", size=15,
                    color=_C.TEXT, weight=ft.FontWeight.BOLD),
            ft.Container(height=8),
            summary,
            ft.Container(height=14),
        ]
        for m, total, avg, active in monthly:
            tip = f"{m}月\n学习次数: {total}\n日均: {avg:.1f}\n活跃天数: {active}"
            rows.append(self._bar_row(f"{m}月", total, max_val, tip))

        rows.append(ft.Container(height=10))
        rows.append(self._build_legend())
        return ft.ListView(controls=rows, padding=ft.padding.all(14),
                           spacing=6, expand=True)

    # ============================================================
    # 图例 / 空状态
    # ============================================================
    def _build_legend(self):
        items = [
            (_C.HEAT[0], "少"),
            (_C.HEAT[1], ""),
            (_C.HEAT[2], "中"),
            (_C.HEAT[3], ""),
            (_C.HEAT[4], "多"),
        ]
        children = []
        for color, label in items:
            children.append(ft.Container(width=14, height=14, bgcolor=color, border_radius=3))
            if label:
                children.append(ft.Text(label, size=9, color=_C.TEXT_SEC))
        return ft.Row(children, alignment=ft.MainAxisAlignment.CENTER, spacing=5)

    def _empty(self):
        return ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.INBOX, size=48, color=_C.TEXT_LT),
                ft.Text("暂无数据", size=14, color=_C.TEXT_SEC),
            ], alignment=ft.MainAxisAlignment.CENTER,
               horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
            expand=True, alignment=ft.alignment.center,
        )

    def _build_chart(self):
        if self.view_mode == 'day':
            return self._build_day_view()
        if self.view_mode == 'week':
            return self._build_week_view()
        return self._build_month_view()

    # ============================================================
    # 交互
    # ============================================================
    async def load_data(self):
        """预加载当前年份数据"""
        self._daily_cache.pop(self.heatmap_year, None)
        self._get_daily_data(self.heatmap_year)
        if self.chart_container is not None:
            self._refresh()

    async def reload(self, msg="加载中..."):
        """带 loading 的刷新：先在图表区显示转圈，再查数据渲染"""
        if self.chart_container is not None:
            self.chart_container.content = ft.Container(
                content=ft.Column([
                    ft.ProgressRing(width=40, height=40, stroke_width=4, color=_C.PRIMARY),
                    ft.Text(msg, size=14, color=_C.TEXT_SEC),
                ], alignment=ft.MainAxisAlignment.CENTER,
                   horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=14),
                expand=True, alignment=ft.alignment.center,
            )
            self.chart_container.update()
        await asyncio.sleep(0.12)
        try:
            self._refresh()
        finally:
            pass

    def _refresh(self):
        if self.chart_container is not None:
            self.chart_container.content = self._build_chart()
            self.chart_container.update()
        self._update_mode_buttons()

    def _update_mode_buttons(self):
        for name, btn in self.mode_buttons.items():
            active = (name == self.view_mode)
            btn.bgcolor = _C.PRIMARY if active else _C.TRACK
            btn.content.color = ft.Colors.WHITE if active else _C.TEXT
            btn.content.weight = (ft.FontWeight.W_700 if active
                                  else ft.FontWeight.NORMAL)
            btn.shadow = (ft.BoxShadow(blur_radius=6, color="#30000000",
                                       offset=ft.Offset(0, 2))
                          if active else None)
            btn.update()

    def _switch_mode(self, mode):
        def handler(e):
            self.view_mode = mode
            self.page.run_task(self.reload)
        return handler

    def _get_selected_user_name(self):
        if self.selected_user_id is None:
            return "全部"
        if hasattr(self, '_user_list'):
            for uid, name in self._user_list:
                if uid == self.selected_user_id:
                    return name
        return self.user_data.get("username", "未知")

    def _snack(self, msg):
        sb = ft.SnackBar(content=ft.Text(msg), duration=2000)
        try:
            self.page.open(sb)
        except AttributeError:
            self.page.snack_bar = sb
            sb.open = True
            self.page.update()

    def _load_user_list(self):
        if not self.is_admin:
            return [(self.user_data.get('id'), self.user_data.get('username', '未知'))]
        try:
            rows = self.db.fetch_all("SELECT user_id, username FROM users ORDER BY username")
            return [(r['user_id'], r['username']) for r in rows] if rows else []
        except Exception as e:
            print(f"[heatmap] 用户列表加载失败: {e}")
            return [(self.user_data.get('id'), self.user_data.get('username', '未知'))]

    def _open_user_sheet(self, e):
        if not self.is_admin:
            self._snack("您没有权限查看其他用户数据")
            return
        self._user_list = self._load_user_list()
        controls = [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.PEOPLE, color=ft.Colors.BLUE_500),
                title=ft.Text("全部用户", size=16),
                on_click=lambda _: self._select_user(None),
                selected=self.selected_user_id is None,
            )
        ]
        for uid, name in self._user_list:
            controls.append(ft.ListTile(
                leading=ft.Icon(ft.Icons.PERSON, color=ft.Colors.GREY_600),
                title=ft.Text(name, size=16),
                on_click=lambda _, u=uid: self._select_user(u),
                selected=self.selected_user_id == uid,
            ))
        sheet = ft.BottomSheet(
            content=ft.Container(padding=ft.padding.all(16), content=ft.Column([
                ft.Text("选择用户", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800),
                ft.Divider(height=1),
                ft.ListView(controls=controls, height=300),
            ], spacing=12)),
            is_scroll_controlled=False, enable_drag=True,
        )
        self.page.open(sheet)

    def _select_user(self, user_id):
        self.selected_user_id = user_id
        self._daily_cache.clear()
        for o in list(self.page.overlay):
            if isinstance(o, ft.BottomSheet):
                self.page.close(o)
        self.page.update()
        if getattr(self, 'on_user_change', None):
            self.on_user_change(user_id)

    # ============================================================
    # 分段模式切换（美化版，位于第二行）
    # ============================================================
    def _build_mode_switch(self):
        items = [('day', '按天'), ('week', '按周'), ('month', '按月')]
        btns = []
        for name, text in items:
            active = (self.view_mode == name)
            btn = ft.Container(
                content=ft.Text(text, size=13,
                    color="white" if active else _C.TEXT,
                    weight=ft.FontWeight.W_700 if active else ft.FontWeight.NORMAL),
                padding=ft.padding.symmetric(horizontal=16, vertical=8),
                border_radius=12,
                bgcolor=_C.PRIMARY if active else _C.TRACK,
                shadow=(ft.BoxShadow(blur_radius=6, color="#30000000",
                                     offset=ft.Offset(0, 2))
                        if active else None),
                on_click=self._switch_mode(name),
                alignment=ft.alignment.center,
                animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
            )
            self.mode_buttons[name] = btn
            btns.append(btn)
        return ft.Container(
            content=ft.Row(controls=btns, spacing=6),
            padding=ft.padding.all(2),
            bgcolor=_C.CARD,
            border_radius=16,
            shadow=ft.BoxShadow(blur_radius=10, color="#10000000"),
            alignment=ft.alignment.center,
        )

    # ============================================================
    # 页面入口
    # ============================================================
    def build(self):
        # ---------- 第一行：年份下拉（用户下拉已移至英语页顶层共享） ----------
        CTRL_H = 44

        # 年份下拉（胶囊样式）
        cur_year = datetime.date.today().year
        year_opts = [str(y) for y in range(cur_year - 5, cur_year + 2)]

        def _select_year(y):
            self.heatmap_year = int(y)
            if self._year_ref:
                self._year_ref.value = str(y)
                self._year_ref.update()
            if self._year_sheet:
                try:
                    self.page.close(self._year_sheet)
                except Exception:
                    pass
                self._year_sheet = None
            self._daily_cache.pop(self.heatmap_year, None)
            self.page.run_task(self.reload)

        def _open_year_sheet(e):
            controls = [ft.ListTile(
                leading=ft.Icon(ft.Icons.CALENDAR_MONTH, color=_C.ACCENT),
                title=ft.Text(y, size=16),
                on_click=lambda _, yy=y: _select_year(yy),
                selected=(str(self.heatmap_year) == y),
            ) for y in year_opts]
            self._year_sheet = ft.BottomSheet(
                content=ft.Container(padding=ft.padding.all(16), content=ft.Column([
                    ft.Text("选择年份", size=18, weight=ft.FontWeight.BOLD, color=_C.ACCENT),
                    ft.Divider(height=1),
                    ft.ListView(controls=controls, height=300),
                ], spacing=8, tight=True)),
                is_scroll_controlled=False, enable_drag=True,
            )
            self.page.open(self._year_sheet)

        self._year_ref = ft.Text(str(self.heatmap_year), size=15, color=_C.TEXT,
                                 weight=ft.FontWeight.W_700)
        year_dropdown = ft.Container(
            height=CTRL_H,
            padding=ft.padding.symmetric(horizontal=14, vertical=0),
            bgcolor=_C.CARD,
            border_radius=24,
            shadow=ft.BoxShadow(blur_radius=10, color="#15000000"),
            on_click=_open_year_sheet,
            content=ft.Row([
                ft.Icon(ft.Icons.CALENDAR_MONTH, size=16, color=_C.ACCENT),
                ft.Text("年份", size=13, color=_C.TEXT, weight=ft.FontWeight.W_600),
                self._year_ref,
                ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=16, color=_C.ACCENT),
            ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
        )

        # 第一行：年份下拉(左) + 模式切换(右)
        row1 = ft.Row([
            year_dropdown,
            ft.Container(expand=True),
            self._build_mode_switch(),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
           vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # ---------- 图表卡片 ----------
        self.chart_container = ft.Container(
            content=self._build_chart(),
            expand=True, bgcolor=_C.CARD, border_radius=18,
            shadow=ft.BoxShadow(blur_radius=14, color="#18000000"),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        return ft.Container(
            content=ft.Column([
                row1,
                self.chart_container,
            ], spacing=10, expand=True),
            padding=ft.padding.all(12),
            bgcolor=_C.BG, expand=True,
        )