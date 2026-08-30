# pages/guoxue.py
import flet as ft
import asyncio
import datetime
from collections import defaultdict


class _C:
    BG = "#F5F0EB"; CARD = "#FFFFFF"
    PRIMARY = "#D97706"; PRIMARY_DARK = "#B45309"; PRIMARY_LT = "#FCD34D"
    ACCENT = "#92400E"; TEXT = "#3D2914"; TEXT_SEC = "#92765A"; TEXT_LT = "#D4C4B0"
    TRACK = "#F0E8DD"; SEAL = "#DC2626"; SEAL_DARK = "#991B1B"
    HEAT = ["#FDF6EC", "#FDE68A", "#FBBF24", "#F59E0B", "#D97706", "#92400E"]
    WEAK_BG = "#FEF2F2"; WEAK_BORDER = "#FECACA"


class GuoxuePage:
    """国学学习数据统计（本地库，点击导航时加载）"""

    def __init__(self, page: ft.Page):
        self.page = page
        self.user_data = page._user_data if hasattr(page, '_user_data') else {}
        self.db = getattr(page, '_local_db', None)
        self.is_admin = self.user_data.get('type') == 'admin'
        self.selected_user_id = getattr(page, 'selected_user_id', None)
        if self.selected_user_id is None:
            self.selected_user_id = self.user_data.get('id')
        self._user_list = []
        self._user_name_ref = None
        today = datetime.date.today()
        self.view_year = today.year
        self._body = None
        self._chart_area = None
        self._loaded = False
        self._ydd = None
        self._year_sheet = None
        self._year_ref = None
        self._title_sub = None
        # 交互状态
        self._trend_mode = 'round'     # round(按轮次·正确率) | count(答题数)
        self._rank_mode = 'count'      # count | accuracy | duration
        self._overview_range = 'all'   # all | week | month
        self._accuracy_range = 30      # 7 | 30 | 90 | 0(全部→按月)
        self._acc_range_switch = None
        self._trend_switch = None
        self._trend_title_ref = [None]
        self._rank_switch = None
        self._weak_show_count = 20
        # 区域引用
        self._overview_area = None
        self._accuracy_area = None
        self._trend_area = None
        self._rank_area = None
        self._weak_area = None
        # 缓存数据
        self._cached_daily = []
        self._cached_daily_answers = []
        self._cached_qs = []

    # ---------- 本地查询 ----------
    def _q(self, sql, params=None):
        try:
            return self.db.fetch_all(sql, params) or []
        except Exception as e:
            print(f"[guoxue] query fail: {e}")
            return []

    def _load_users(self):
        if self.is_admin:
            try:
                rows = self.page._db.fetch_all("SELECT user_id, username FROM users ORDER BY username")
                self._user_list = [(r['user_id'], r['username']) for r in rows] if rows else []
            except Exception:
                self._user_list = []
        else:
            self._user_list = [(self.user_data.get('id'), self.user_data.get('username', '未知'))]

    def _daily(self):
        return self._q("SELECT date, total_questions, correct_count, score, time_spent, accuracy FROM user_chinese_culture_questions_history WHERE user_id=? ORDER BY date", [self.selected_user_id])

    def _daily_answers(self):
        """单题记录按天聚合（答题数/正确率/均时用这个）"""
        return self._q("""SELECT DATE(answer_time) as date,
                                 COUNT(*) as total_questions,
                                 COALESCE(SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END),0) as correct_count,
                                 COALESCE(AVG(CASE WHEN is_correct=1 THEN 1.0 ELSE 0.0 END)*100,0) as accuracy,
                                 COALESCE(SUM(points_change),0) as score,
                                 COALESCE(AVG(duration),0) as avg_duration
                          FROM user_chinese_culture_answer_history
                          WHERE user_id=?
                          GROUP BY DATE(answer_time)
                          ORDER BY date""", [self.selected_user_id])

    def _qsummary(self):
        return self._q("SELECT question_id, total_answers, correct_count, wrong_count, avg_duration, last_answer_time FROM user_chinese_culture_answer_summary WHERE user_id=? ORDER BY correct_count DESC, total_answers DESC", [self.selected_user_id])

    def _history(self, year):
        return self._q("SELECT id, question_id, is_correct, duration, answer_time, user_answer, points_change FROM user_chinese_culture_answer_history WHERE user_id=? AND answer_time BETWEEN ? AND ? ORDER BY answer_time",
                       [self.selected_user_id, f"{year}-01-01", f"{year}-12-31"])

    # ---------- 时间范围过滤 ----------
    def _filter_daily(self, daily, range_type):
        if range_type == 'all' or not daily:
            return daily
        now = datetime.date.today()
        if range_type == 'week':
            cutoff = now - datetime.timedelta(days=7)
        else:  # month
            cutoff = now - datetime.timedelta(days=30)
        result = []
        for d in daily:
            try:
                dt = datetime.datetime.strptime(str(d.get('date', ''))[:10], "%Y-%m-%d").date()
                if dt >= cutoff:
                    result.append(d)
            except Exception:
                pass
        return result

    # ---------- 颜色 ----------
    def _heat_color(self, v, mx):
        if mx == 0 or v == 0: return _C.HEAT[0]
        r = v / mx
        if r < 0.15: return _C.HEAT[1]
        if r < 0.3: return _C.HEAT[2]
        if r < 0.5: return _C.HEAT[3]
        if r < 0.75: return _C.HEAT[4]
        return _C.HEAT[5]

    def _acc_color(self, acc):
        if acc < 40: return "#DC2626"
        if acc < 60: return "#EA580C"
        if acc < 80: return "#CA8A04"
        return "#16A34A"

    def _bar_grad(self):
        return ft.LinearGradient(begin=ft.alignment.center_left, end=ft.alignment.center_right,
                                 colors=[_C.PRIMARY_LT, _C.PRIMARY])

    # ---------- 通用控件 ----------
    def _stat_card(self, icon, value, label, color):
        return ft.Container(content=ft.Column([
            ft.Container(width=30, height=30, border_radius=15,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                    colors=[ft.Colors.with_opacity(0.2, color), ft.Colors.with_opacity(0.05, color)]),
                content=ft.Icon(icon, size=15, color=color), alignment=ft.alignment.center),
            ft.Text(str(value), size=17, weight=ft.FontWeight.BOLD, color=_C.TEXT, no_wrap=True),
            ft.Text(label, size=10, color=_C.TEXT_SEC, no_wrap=True),
        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
            padding=ft.padding.symmetric(vertical=10, horizontal=4),
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_center, end=ft.alignment.bottom_center,
                colors=[_C.CARD, ft.Colors.with_opacity(0.5, _C.TRACK)]),
            border_radius=14,
            border=ft.border.all(0.5, ft.Colors.with_opacity(0.3, _C.TEXT_LT)),
            shadow=ft.BoxShadow(blur_radius=6, color="#0C000000", offset=ft.Offset(0, 2)),
            expand=True)

    def _bar_row(self, label, value, mx, tip, value_suffix="", bar_color=None):
        ratio = (value / mx) if mx > 0 else 0
        ratio = max(0.0, min(1.0, ratio))
        # 用 expand 比例实现准确宽度（基数100）
        filled = max(int(round(ratio * 100)), 1)
        empty = 100 - filled
        color = bar_color or _C.PRIMARY
        return ft.Row([
            ft.Container(width=48, content=ft.Text(label, size=10, color=_C.TEXT_SEC,
                            text_align=ft.TextAlign.RIGHT, no_wrap=True)),
            ft.Container(expand=True, height=22, bgcolor=_C.TRACK, border_radius=5,
                content=ft.Row([
                    ft.Container(expand=filled, height=22,
                                 gradient=ft.LinearGradient(begin=ft.alignment.center_left,
                                     end=ft.alignment.center_right,
                                     colors=[ft.Colors.with_opacity(0.7, color), color]),
                                 border_radius=5),
                    ft.Container(expand=empty, height=22),
                ], spacing=0),
                tooltip=tip,
                on_click=lambda e, t=tip: self.page.open(ft.SnackBar(content=ft.Text(t), duration=2000))),
            ft.Container(width=44, content=ft.Text(f"{value:.1f}{value_suffix}" if isinstance(value, float) else f"{value}{value_suffix}", size=10, color=color,
                            weight=ft.FontWeight.W_600, text_align=ft.TextAlign.RIGHT, no_wrap=True)),
        ], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _section(self, text, icon, color=_C.PRIMARY_DARK, text_ref=None):
        t = ft.Text(text, size=13, weight=ft.FontWeight.BOLD, color=color, no_wrap=True)
        if text_ref is not None:
            text_ref[0] = t
        return ft.Container(content=ft.Row([
            ft.Container(width=4, height=18, border_radius=2,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_center, end=ft.alignment.bottom_center,
                    colors=[color, ft.Colors.with_opacity(0.4, color)])),
            ft.Container(width=26, height=26, border_radius=13,
                bgcolor=ft.Colors.with_opacity(0.1, color),
                content=ft.Icon(icon, size=14, color=color), alignment=ft.alignment.center),
            t,
        ], spacing=6), padding=ft.padding.only(left=2, top=6, bottom=4))

    def _mode_switch(self, options, current, on_change):
        """小维度切换条"""
        btns = []
        for key, label in options:
            active = (key == current)
            btn = ft.Container(
                content=ft.Text(label, size=10,
                    color="white" if active else _C.TEXT_SEC,
                    weight=ft.FontWeight.W_600 if active else ft.FontWeight.NORMAL),
                padding=ft.padding.symmetric(horizontal=10, vertical=4),
                border_radius=10,
                bgcolor=_C.PRIMARY if active else _C.TRACK,
                on_click=lambda e, k=key: on_change(k),
                animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
            )
            btns.append(btn)
        return ft.Container(
            content=ft.Row(btns, spacing=3),
            padding=2, bgcolor=_C.CARD, border_radius=12,
            shadow=ft.BoxShadow(blur_radius=4, color="#08000000"),
        )

    def _empty(self, text="暂无数据"):
        return ft.Container(content=ft.Column([
            ft.Container(width=64, height=64, border_radius=32,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                    colors=[_C.TRACK, ft.Colors.with_opacity(0.3, _C.TEXT_LT)]),
                content=ft.Icon(ft.Icons.INBOX, size=28, color=_C.TEXT_LT),
                alignment=ft.alignment.center),
            ft.Text(text, size=13, color=_C.TEXT_SEC, weight=ft.FontWeight.W_500),
            ft.Container(width=40, height=2, border_radius=1, bgcolor=_C.TEXT_LT),
        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            padding=24, alignment=ft.alignment.center)

    def _loading(self):
        return ft.Container(content=ft.Column([
            ft.Container(width=56, height=56, border_radius=28,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                    colors=[_C.PRIMARY_LT, _C.PRIMARY]),
                content=ft.ProgressRing(width=28, height=28, color="white", stroke_width=3),
                alignment=ft.alignment.center),
            ft.Text("加载国学数据...", size=13, color=_C.TEXT, weight=ft.FontWeight.W_500),
            ft.Text("正在从本地读取答题记录", size=10, color=_C.TEXT_SEC),
        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            expand=True, alignment=ft.alignment.center)

    # ---------- 概览（2x2 + 时间范围） ----------
    def _overview(self, daily_answers):
        """概览统计：数据全部来自 user_chinese_culture_answer_history 按天聚合"""
        filtered = self._filter_daily(daily_answers, self._overview_range)
        tq = sum(d.get('total_questions', 0) for d in filtered)
        tc = sum(d.get('correct_count', 0) for d in filtered)
        ts = sum(d.get('score', 0) for d in filtered)
        acc = (tc / tq * 100) if tq > 0 else 0
        # 均时：按每天答题数加权平均
        total_dur = sum(d.get('avg_duration', 0) * d.get('total_questions', 0) for d in filtered)
        avg_dur = (total_dur / tq) if tq > 0 else 0
        active_days = len(set(str(d.get('date', ''))[:10] for d in filtered if d.get('date')))
        last_date = str(filtered[-1].get('date', '-'))[:10] if filtered else "-"

        range_opts = [('all', '全部'), ('week', '本周'), ('month', '本月')]
        range_bar = self._mode_switch(range_opts, self._overview_range, self._on_overview_range)

        return ft.Column([
            ft.Row([range_bar], alignment=ft.MainAxisAlignment.END),
            ft.Row([
                self._stat_card(ft.Icons.QUIZ, tq, "总答题", _C.PRIMARY),
                self._stat_card(ft.Icons.CHECK_CIRCLE, tc, "正确数", "#16A34A"),
            ], spacing=6),
            ft.Row([
                self._stat_card(ft.Icons.PERCENT, f"{acc:.0f}%", "正确率", _C.ACCENT),
                self._stat_card(ft.Icons.STAR, ts, "积分", "#CA8A04"),
            ], spacing=6),
            ft.Row([
                self._stat_card(ft.Icons.TIMER, f"{avg_dur:.1f}s", "均时", "#7C3AED"),
                self._stat_card(ft.Icons.EVENT_AVAILABLE, active_days, "活跃天", "#0EA5E9"),
            ], spacing=6),
            ft.Container(content=ft.Row([
                ft.Icon(ft.Icons.SCHEDULE, size=11, color=_C.TEXT_SEC),
                ft.Text(f"最近学习: {last_date}", size=10, color=_C.TEXT_SEC),
            ], spacing=3, alignment=ft.MainAxisAlignment.CENTER),
                padding=ft.padding.only(top=2)),
        ], spacing=5)

    # ---------- 正确率趋势图（按天/按月聚合） ----------
    def _accuracy_trend(self, daily):
        # 按天聚合：sum(correct) / sum(total) * 100
        daily_acc = defaultdict(lambda: {'total': 0, 'correct': 0})
        for d in daily:
            ds = str(d.get('date', ''))[:10]
            if not ds or ds == '':
                continue
            daily_acc[ds]['total'] += d.get('total_questions', 0)
            daily_acc[ds]['correct'] += d.get('correct_count', 0)
        if self._accuracy_range == 0:
            # 全部 → 按月聚合，避免点太多
            monthly = defaultdict(lambda: {'total': 0, 'correct': 0})
            for ds, v in daily_acc.items():
                ms = ds[:7]  # YYYY-MM
                monthly[ms]['total'] += v['total']
                monthly[ms]['correct'] += v['correct']
            keys = sorted(monthly.keys())
            points = [(k, monthly[k]['correct'] / monthly[k]['total'] * 100
                       if monthly[k]['total'] > 0 else 0) for k in keys]
        else:
            days = sorted(daily_acc.keys())[-self._accuracy_range:]
            points = [(d, daily_acc[d]['correct'] / daily_acc[d]['total'] * 100
                       if daily_acc[d]['total'] > 0 else 0) for d in days]
        if not points:
            return self._empty("暂无正确率数据")
        granularity = "按月" if self._accuracy_range == 0 else "按天"
        return self._accuracy_line_chart(points, granularity)

    def _accuracy_line_chart(self, data_points, granularity="按天"):
        """优化版棒棒糖趋势图：Y轴刻度+圆点白边+渐变竖线+平均虚线+高低标注"""
        n = len(data_points)
        avg_acc = sum(acc for _, acc in data_points) / n if n else 0
        max_acc = max((acc for _, acc in data_points), default=0)
        min_acc = min((acc for _, acc in data_points), default=0)

        page_w = getattr(self.page, 'width', 360) or 360
        W = max(260, min(int(page_w) - 56, 380))
        H = 120
        y_label_w = 26
        chart_w = W - y_label_w - 4

        # Y轴标签（100/75/50/25/0）
        y_labels = ft.Container(width=y_label_w, height=H, content=ft.Column([
            ft.Container(height=H * 0.25, content=ft.Text("100", size=7, color=_C.TEXT_LT,
                text_align=ft.TextAlign.RIGHT), alignment=ft.alignment.top_right),
            ft.Container(height=H * 0.25, content=ft.Text("75", size=7, color=_C.TEXT_LT,
                text_align=ft.TextAlign.RIGHT), alignment=ft.alignment.top_right),
            ft.Container(height=H * 0.25, content=ft.Text("50", size=7, color=_C.TEXT_LT,
                text_align=ft.TextAlign.RIGHT), alignment=ft.alignment.top_right),
            ft.Container(height=H * 0.25, content=ft.Text("25", size=7, color=_C.TEXT_LT,
                text_align=ft.TextAlign.RIGHT), alignment=ft.alignment.top_right),
            ft.Container(height=0, content=ft.Text("0", size=7, color=_C.TEXT_LT,
                text_align=ft.TextAlign.RIGHT)),
        ], spacing=0))

        # 数据点列
        day_cols = []
        for i, (ds, acc) in enumerate(data_points):
            c = self._acc_color(acc)
            tip = f"{ds}\n正确率: {acc:.1f}%"
            spacer_h = max(0, (1 - acc / 100) * H)
            stem_h = max(H - spacer_h, 1)
            is_extreme = (acc == max_acc or acc == min_acc) and n > 2
            day_cols.append(ft.Container(expand=True, content=ft.Column([
                ft.Container(height=spacer_h),
                ft.Container(width=11, height=11, border_radius=6, bgcolor=c,
                    border=ft.border.all(2, "white"),
                    shadow=ft.BoxShadow(blur_radius=3, color="#30000000", offset=ft.Offset(0, 1)),
                    tooltip=tip,
                    on_click=lambda e, t=tip: self.page.open(
                        ft.SnackBar(content=ft.Text(t), duration=2000))),
                ft.Container(width=2, height=stem_h,
                    gradient=ft.LinearGradient(
                        begin=ft.alignment.top_center, end=ft.alignment.bottom_center,
                        colors=[c, ft.Colors.with_opacity(0.15, c)]),
                    border_radius=1),
            ], spacing=0, tight=True), alignment=ft.alignment.top_center))

        # 网格背景
        grid = ft.Container(width=chart_w, height=H, content=ft.Column([
            ft.Container(height=H * 0.25, border=ft.border.only(
                bottom=ft.BorderSide(0.5, _C.TEXT_LT))),
            ft.Container(height=H * 0.25, border=ft.border.only(
                bottom=ft.BorderSide(0.5, _C.TEXT_LT))),
            ft.Container(height=H * 0.25, border=ft.border.only(
                bottom=ft.BorderSide(0.5, _C.TEXT_LT))),
            ft.Container(height=H * 0.25),
        ], spacing=0))

        # 平均虚线
        avg_top = (1 - avg_acc / 100) * H
        dash_w = 5; dash_gap = 3
        dash_count = max(1, int(chart_w / (dash_w + dash_gap)))
        avg_dashes = ft.Row([
            ft.Container(width=dash_w, height=2, bgcolor=_C.PRIMARY, border_radius=1)
            for _ in range(dash_count)
        ], spacing=dash_gap, width=chart_w)
        avg_overlay = ft.Container(padding=ft.padding.only(top=avg_top),
            content=avg_dashes, width=chart_w)

        chart_inner = ft.Stack([grid, avg_overlay,
            ft.Row(day_cols, spacing=0, width=chart_w, height=H)],
            width=chart_w, height=H)

        chart_row = ft.Row([y_labels, chart_inner], spacing=2, width=W)

        # 日期标签（对齐图表区）
        step = max(1, n // 6)
        date_row = ft.Row([
            ft.Container(width=y_label_w + 2),
            ft.Container(expand=True, content=ft.Row([
                ft.Container(expand=True,
                    content=ft.Text(ds[5:] if i % step == 0 else "", size=8,
                        color=_C.TEXT_SEC, text_align=ft.TextAlign.CENTER),
                    alignment=ft.alignment.center)
                for i, (ds, _) in enumerate(data_points)
            ], spacing=0, width=chart_w)),
        ], spacing=0, width=W)

        # 图例
        legend = ft.Row([
            ft.Container(padding=ft.padding.symmetric(horizontal=6, vertical=2),
                bgcolor=ft.Colors.with_opacity(0.12, _C.PRIMARY), border_radius=8,
                content=ft.Text(granularity, size=9, color=_C.PRIMARY, weight=ft.FontWeight.BOLD)),
            ft.Container(width=9, height=9, border_radius=5, bgcolor=_C.PRIMARY,
                border=ft.border.all(1.5, "white")),
            ft.Text("正确率", size=9, color=_C.TEXT_SEC),
            ft.Container(width=12, height=2, bgcolor=_C.PRIMARY, border_radius=1),
            ft.Text(f"均{avg_acc:.0f}%", size=9, color=_C.PRIMARY, weight=ft.FontWeight.W_600),
            ft.Container(width=8, height=8, border_radius=4, bgcolor="#16A34A"),
            ft.Text(f"高{max_acc:.0f}%", size=9, color="#16A34A"),
            ft.Container(width=8, height=8, border_radius=4, bgcolor="#DC2626"),
            ft.Text(f"低{min_acc:.0f}%", size=9, color="#DC2626"),
        ], spacing=3, alignment=ft.MainAxisAlignment.CENTER, wrap=True)

        return ft.Column([legend, chart_row, date_row], spacing=3, tight=True,
                         horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    # ---------- 每日趋势（支持维度切换） ----------
    def _trend(self, daily, daily_answers=None):
        """daily=questions_history(一轮一条), daily_answers=answer_history按天聚合"""
        # 按轮次：每轮一根柱，显示正确率，用questions_history原始记录，最近30轮
        if self._trend_mode == 'round':
            if not daily: return self._empty("暂无轮次记录")
            # 按时间正序（最早在前），同一天从1开始编号
            rounds_asc = sorted(daily, key=lambda x: str(x.get('date', '')), reverse=False)[-30:]
            day_idx = {}
            numbered = []
            for s in rounds_asc:
                ds = str(s.get('date', ''))[:10]
                day_idx[ds] = day_idx.get(ds, 0) + 1
                numbered.append((s, ds, day_idx[ds]))
            # 反转成最新在前（显示顺序）
            numbered = list(reversed(numbered))
            mx = 100
            rows = []
            for s, ds, idx in numbered:
                full_ds = str(s.get('date', ''))[:16].replace('T', ' ')
                label = f"{ds[5:]}({idx})"
                q = s.get('total_questions', 0)
                correct = s.get('correct_count', 0)
                acc = (correct / q * 100) if q > 0 else 0
                tip = f"{full_ds}\n第{idx}轮（{ds}）\n正确率:{acc:.0f}%\n答题:{q} 正确:{correct} 积分:{s.get('score',0)} 用时:{s.get('time_spent',0)}s"
                rows.append(self._bar_row(label, acc, mx, tip, value_suffix="%", bar_color=self._acc_color(acc)))
            return ft.Column(controls=rows, spacing=2, tight=True,
                             horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        # 答题数：用answer_history按天聚合，最近30天
        data = daily_answers if daily_answers else []
        if not data: return self._empty("暂无答题记录")
        recent = sorted(data, key=lambda x: str(x.get('date', '')), reverse=True)[:30]
        mx = max((d.get('total_questions', 0) for d in recent), default=1)
        rows = []
        for d in recent:
            ds = str(d.get('date', ''))[:10]
            q = d.get('total_questions', 0)
            correct = d.get('correct_count', 0)
            acc = float(d.get('accuracy', 0) or 0)
            tip = f"{ds}\n答题:{q} 正确:{correct} 正确率:{acc:.0f}% 积分:{d.get('score',0)}"
            rows.append(self._bar_row(ds[5:], q, mx, tip))
        return ft.Column(controls=rows, spacing=2, tight=True,
                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    # ---------- 排行（支持排序切换） ----------
    def _ranking(self, qs):
        if not qs: return self._empty("暂无题目统计")
        if self._rank_mode == 'count':
            top = sorted(qs, key=lambda x: x.get('total_answers', 0), reverse=True)[:20]
        elif self._rank_mode == 'accuracy':
            top = sorted(qs, key=lambda x: (x.get('correct_count',0)/x.get('total_answers',1) if x.get('total_answers',0)>0 else 0), reverse=True)[:20]
        else:  # duration
            top = sorted(qs, key=lambda x: x.get('avg_duration', 999))[:20]
        rows = []
        medal_colors = ["#F59E0B", "#94A3B8", "#CD7F32"]  # 金/银/铜
        for i, q in enumerate(top):
            total = q.get('total_answers', 0)
            correct = q.get('correct_count', 0)
            acc = (correct / total * 100) if total > 0 else 0
            avg = q.get('avg_duration', 0)
            is_weak = acc < 40
            c = self._acc_color(acc)
            weak_tag = ft.Container(
                content=ft.Text("薄弱", size=8, color="white", weight=ft.FontWeight.BOLD),
                padding=ft.padding.symmetric(horizontal=4, vertical=1),
                bgcolor="#DC2626", border_radius=4, visible=is_weak,
            ) if is_weak else ft.Container(width=0)
            # Top3 徽章
            if i < 3:
                rank_badge = ft.Container(width=24, height=24, border_radius=12,
                    gradient=ft.LinearGradient(begin=ft.alignment.top_left,
                        end=ft.alignment.bottom_right,
                        colors=[medal_colors[i], ft.Colors.with_opacity(0.6, medal_colors[i])]),
                    content=ft.Text(f"{i+1}", size=11, color="white", weight=ft.FontWeight.BOLD),
                    alignment=ft.alignment.center)
            else:
                rank_badge = ft.Container(width=24, height=24, border_radius=12,
                    bgcolor=_C.TRACK,
                    content=ft.Text(f"{i+1}", size=10, color=_C.TEXT_SEC, weight=ft.FontWeight.W_600),
                    alignment=ft.alignment.center)
            tip = f"题目ID:{q.get('question_id','?')}\n答题:{total} 正确:{correct} 正确率:{acc:.1f}% 均时:{avg:.1f}s"
            qid = q.get('question_id')
            rows.append(ft.Container(content=ft.Row([
                rank_badge,
                ft.Column([
                    ft.Row([
                        ft.Text(f"题目 {q.get('question_id','?')}", size=11,
                                weight=ft.FontWeight.W_600, color=_C.TEXT, no_wrap=True),
                        weak_tag,
                    ], spacing=3),
                    ft.Text(f"正确率{acc:.0f}% · 均时{avg:.1f}s", size=9, color=c, no_wrap=True),
                ], spacing=0, tight=True, expand=True),
                ft.Container(expand=True, height=10, bgcolor=_C.TRACK, border_radius=3,
                    content=ft.Container(width=max(int(acc), 2), height=10, bgcolor=c, border_radius=3)),
                ft.Container(width=32, alignment=ft.alignment.center_right,
                             content=ft.Text(f"{total}", size=10, weight=ft.FontWeight.W_600, color=_C.TEXT, no_wrap=True)),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=_C.TEXT_LT),
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(horizontal=8, vertical=5),
                gradient=ft.LinearGradient(begin=ft.alignment.center_left, end=ft.alignment.center_right,
                    colors=[_C.WEAK_BG if is_weak else _C.CARD,
                            ft.Colors.with_opacity(0.3, _C.WEAK_BG) if is_weak else _C.CARD]) if is_weak else None,
                bgcolor=None if is_weak else _C.CARD,
                border_radius=8,
                border=ft.border.all(1, _C.WEAK_BORDER) if is_weak else ft.border.all(0.5, ft.Colors.with_opacity(0.15, _C.TEXT_LT)),
                margin=ft.margin.only(bottom=2), tooltip=tip,
                on_click=lambda e, qid=qid: self._show_question_detail(qid)))
        return ft.Column(controls=rows, spacing=0, tight=True,
                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    # ---------- 薄弱题专区 ----------
    def _weak_section(self, qs):
        if not qs:
            return self._empty("暂无题目统计")
        weak = [q for q in qs if q.get('total_answers', 0) > 0
                and (q.get('correct_count', 0) / q.get('total_answers', 1) * 100) < 40]
        if not weak:
            return ft.Container(content=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color="#16A34A"),
                ft.Text("暂无薄弱题目，继续保持！", size=12, color="#16A34A"),
            ], spacing=6, alignment=ft.MainAxisAlignment.CENTER), padding=16)
        weak = sorted(weak, key=lambda x: x.get('correct_count',0)/x.get('total_answers',1))
        total_weak = len(weak)
        show = weak[:self._weak_show_count]
        rows = []
        for q in show:
            ans_count = q.get('total_answers', 0)
            correct = q.get('correct_count', 0)
            acc = (correct / ans_count * 100) if ans_count > 0 else 0
            rows.append(ft.Container(content=ft.Row([
                ft.Container(width=24, height=24, border_radius=12, bgcolor="#DC2626",
                    content=ft.Text("!", size=14, color="white", weight=ft.FontWeight.BOLD),
                    alignment=ft.alignment.center),
                ft.Column([
                    ft.Text(f"题目 {q.get('question_id','?')}", size=11,
                            weight=ft.FontWeight.W_600, color=_C.TEXT, no_wrap=True),
                    ft.Text(f"正确率{acc:.0f}% · 答{ans_count}次对{correct}次", size=9,
                            color="#DC2626", no_wrap=True),
                ], spacing=0, tight=True, expand=True),
                ft.Container(width=50, height=8, bgcolor="#FECACA", border_radius=4,
                    content=ft.Container(width=max(int(acc*0.5), 2), height=8, bgcolor="#DC2626", border_radius=4)),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=_C.TEXT_LT),
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(horizontal=8, vertical=5),
                bgcolor="#FEF2F2", border_radius=6, margin=ft.margin.only(bottom=2),
                on_click=lambda e, qid=q.get('question_id'): self._show_question_detail(qid)))
        # 查看更多按钮
        if self._weak_show_count < total_weak:
            remaining = total_weak - self._weak_show_count
            load_more = ft.Container(content=ft.Text(
                f"查看更多（追加{min(10, remaining)}条，共{total_weak}条）",
                size=11, color=_C.PRIMARY, weight=ft.FontWeight.W_600),
                padding=ft.padding.symmetric(vertical=10), alignment=ft.alignment.center,
                on_click=self._on_load_more_weak,
                gradient=ft.LinearGradient(begin=ft.alignment.center_left,
                    end=ft.alignment.center_right,
                    colors=[ft.Colors.with_opacity(0.12, _C.PRIMARY), ft.Colors.with_opacity(0.05, _C.PRIMARY)]),
                border_radius=8, margin=ft.margin.only(top=4),
                border=ft.border.all(1, ft.Colors.with_opacity(0.2, _C.PRIMARY)))
            rows.append(load_more)
        return ft.Column(controls=rows, spacing=0, tight=True,
                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    def _on_load_more_weak(self, e):
        self._weak_show_count += 10
        if self._weak_area is not None:
            self._weak_area.content = self._weak_section(self._cached_qs)
            self._weak_area.update()

    def _show_question_detail(self, qid):
        """点击薄弱题查看题目内容和正确答案"""
        if not qid:
            return
        # 检查本地是否有questions表
        try:
            tbl_check = self._q("SELECT name FROM sqlite_master WHERE type='table' AND name='questions'")
        except Exception:
            tbl_check = []
        if not tbl_check:
            self.page.open(ft.SnackBar(content=ft.Text("题目数据未同步，请在登录时开启数据同步"), duration=3000))
            return
        try:
            row = self._q("SELECT question, option_a, option_b, option_c, option_d, answer, explanation, category, difficulty FROM questions WHERE id=?", [qid])
        except Exception as e:
            self.page.open(ft.SnackBar(content=ft.Text(f"查询失败：{e}"), duration=3000))
            return
        if not row:
            self.page.open(ft.SnackBar(content=ft.Text(f"题目 {qid} 详情未找到"), duration=2000))
            return
        q = row[0]
        ans_map = {1: 'A', 2: 'B', 3: 'C', 4: 'D'}
        correct = ans_map.get(q.get('answer'), '?')
        diff_map = {1: '简单', 2: '普通', 3: '困难'}
        content_items = [
            ft.Text(f"题目 #{qid}", size=13, weight=ft.FontWeight.BOLD, color=_C.PRIMARY),
            ft.Container(height=4),
            ft.Text(q.get('question', '-'), size=12, color=_C.TEXT),
            ft.Container(height=8),
        ]
        for opt_key, opt_label in [('option_a', 'A'), ('option_b', 'B'), ('option_c', 'C'), ('option_d', 'D')]:
            is_correct = (opt_label == correct)
            content_items.append(ft.Container(
                content=ft.Row([
                    ft.Container(width=22, height=22, border_radius=11,
                        bgcolor="#16A34A" if is_correct else _C.TRACK,
                        content=ft.Text(opt_label, size=10, color="white" if is_correct else _C.TEXT_SEC,
                            weight=ft.FontWeight.BOLD), alignment=ft.alignment.center),
                    ft.Text(str(q.get(opt_key, '-')), size=11,
                        color="#16A34A" if is_correct else _C.TEXT,
                        weight=ft.FontWeight.W_600 if is_correct else ft.FontWeight.NORMAL,
                        no_wrap=True, expand=True),
                    ft.Icon(ft.Icons.CHECK, size=14, color="#16A34A") if is_correct else ft.Container(width=0),
                ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(vertical=3)))
        if q.get('explanation'):
            content_items.extend([
                ft.Container(height=6),
                ft.Text("解析", size=11, weight=ft.FontWeight.BOLD, color=_C.TEXT_SEC),
                ft.Text(q.get('explanation', ''), size=10, color=_C.TEXT_SEC),
            ])
        meta = []
        if q.get('category'): meta.append(f"分类: {q['category']}")
        if q.get('difficulty'): meta.append(f"难度: {diff_map.get(q['difficulty'], q['difficulty'])}")
        if meta:
            content_items.append(ft.Text(" · ".join(meta), size=9, color=_C.TEXT_LT))
        dlg = ft.AlertDialog(
            title=ft.Text("题目详情", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=ft.Column(content_items, spacing=2, scroll=ft.ScrollMode.ADAPTIVE),
                                 width=360, padding=4),
            actions=[ft.TextButton("关闭", on_click=lambda e: self.page.close(dlg))],
        )
        self.page.open(dlg)

    # ---------- 答题行为分析（参考 checek_answer.py） ----------
    def _analyze_behavior(self, hist):
        """纯Python实现答题行为分析，不依赖pandas/numpy"""
        if not hist:
            return None
        TIMEOUT = 12
        TOO_FAST = 1.5
        n = len(hist)
        absent = forced = random = normal = 0
        valid = []  # (is_correct, user_answer, duration)
        for h in hist:
            dur = h.get('duration', 0) or 0
            ans = h.get('user_answer', -1)
            if ans is None or ans == -1:
                absent += 1
            elif dur >= TIMEOUT:
                forced += 1
            elif dur <= TOO_FAST:
                random += 1
            else:
                normal += 1
                valid.append((bool(h.get('is_correct')), ans, dur))
        # 正确率 & 均时
        if valid:
            correct_rate = sum(1 for c, _, _ in valid if c) / len(valid)
            avg_dur = sum(d for _, _, d in valid) / len(valid)
        else:
            correct_rate = avg_dur = 0
        # 选项分布熵
        entropy = 0
        if valid:
            from collections import Counter
            import math
            cnt = Counter(a for _, a, _ in valid)
            total = len(valid)
            entropy = -sum((c / total) * math.log2(c / total) for c in cnt.values())
        # 连续异常
        max_anomaly = cur = 0
        for h in hist:
            dur = h.get('duration', 0) or 0
            ans = h.get('user_answer', -1)
            if ans is None or ans == -1 or dur >= TIMEOUT or dur <= TOO_FAST:
                cur += 1
                max_anomaly = max(max_anomaly, cur)
            else:
                cur = 0
        # 连续相同答案
        max_same = cur_s = 1
        prev = None
        for h in hist:
            ans = h.get('user_answer', -1)
            if ans is not None and ans != -1:
                if prev is not None and ans == prev:
                    cur_s += 1
                    max_same = max(max_same, cur_s)
                else:
                    cur_s = 1
                prev = ans
        # 濒临超时（9-12秒）
        last_moment = sum(1 for h in hist
                          if h.get('user_answer', -1) not in (None, -1)
                          and TIMEOUT - 3 <= (h.get('duration', 0) or 0) < TIMEOUT)
        lm_rate = last_moment / len(valid) if valid else 0
        # 风险评分
        risk = 0
        ar = absent / n; rr = random / n; fr = forced / n
        if ar >= 0.5: risk += 0.30
        elif ar >= 0.3: risk += 0.20
        elif ar >= 0.1: risk += 0.10
        if rr >= 0.4: risk += 0.25
        elif rr >= 0.2: risk += 0.15
        elif rr >= 0.1: risk += 0.05
        if fr >= 0.1: risk += 0.05
        if len(valid) >= 8:
            if entropy >= 0.5: risk += 0.15
            elif entropy >= 1.0: risk += 0.05
        if valid:
            wr = 1 - correct_rate
            if wr >= 0.5: risk += 0.20
            elif wr >= 0.3: risk += 0.10
            elif wr >= 0.1: risk += 0.05
        if avg_dur < 2 and correct_rate < 0.7: risk += 0.10
        elif avg_dur < 4 and correct_rate < 0.7: risk += 0.05
        if max_anomaly >= 5: risk += 0.25
        elif max_anomaly >= 3: risk += 0.12
        elif max_anomaly >= 2: risk += 0.05
        if max_same >= 4: risk += 0.20
        elif max_same >= 3: risk += 0.10
        elif max_same >= 2: risk += 0.03
        if lm_rate >= 0.2: risk += 0.15
        risk = min(risk, 1.0)
        # 综合评分（正面，0-100越高越好）= 正确率50% + 行为规范30% + 用时合理20%
        if 3 <= avg_dur <= 8:
            time_score = 1.0
        elif (1.5 <= avg_dur < 3) or (8 < avg_dur <= 12):
            time_score = 0.6
        else:
            time_score = 0.3
        quality_score = round(correct_rate * 50 + (1 - risk) * 30 + time_score * 20)
        quality_score = max(0, min(100, quality_score))
        # 最终判定
        if lm_rate >= 0.2 and rr >= 0.15 and correct_rate < 0.5:
            verdict = "疑似分心看视频"
        elif ar >= 0.4:
            verdict = "挂机离席"
        elif rr >= 0.3:
            verdict = "胡乱答题"
        elif risk >= 0.6:
            verdict = "高度异常"
        elif risk >= 0.4:
            verdict = "疑似分心/敷衍"
        else:
            verdict = "正常答题"
        return {'total': n, 'valid': len(valid), 'absent': absent, 'forced': forced,
                'random': random, 'normal': normal, 'absent_rate': ar, 'random_rate': rr,
                'forced_rate': fr, 'correct_rate': correct_rate, 'avg_dur': avg_dur,
                'entropy': entropy, 'max_anomaly': max_anomaly, 'max_same': max_same,
                'lm_rate': lm_rate, 'risk': risk, 'quality': quality_score, 'verdict': verdict}

    def _mini_metric(self, label, value, color):
        return ft.Container(content=ft.Column([
            ft.Text(str(value), size=15, weight=ft.FontWeight.BOLD, color=color, no_wrap=True),
            ft.Text(label, size=9, color=_C.TEXT_SEC, no_wrap=True),
        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
            padding=ft.padding.symmetric(vertical=8, horizontal=4),
            bgcolor=_C.TRACK, border_radius=8, expand=True)

    def _behavior_section(self, result):
        if not result:
            return self._empty("暂无答题行为数据")
        # 综合评分等级
        q = result['quality']
        if q >= 80:
            qc = "#16A34A"; ql = "优秀"
        elif q >= 60:
            qc = "#CA8A04"; ql = "良好"
        elif q >= 40:
            qc = "#EA580C"; ql = "一般"
        else:
            qc = "#DC2626"; ql = "待改进"
        # 风险等级
        if result['risk'] >= 0.6:
            rc = "#DC2626"; rl = "高风险"
        elif result['risk'] >= 0.4:
            rc = "#EA580C"; rl = "中风险"
        elif result['risk'] >= 0.2:
            rc = "#CA8A04"; rl = "低风险"
        else:
            rc = "#16A34A"; rl = "正常"
        # 综合评分大卡
        score_card = ft.Container(content=ft.Column([
            ft.Text("答题综合评分", size=12, color=_C.TEXT_SEC),
            ft.Row([
                ft.Text(f"{q}", size=44, weight=ft.FontWeight.BOLD, color=qc),
                ft.Column([
                    ft.Text("/100", size=14, color=_C.TEXT_SEC),
                    ft.Container(padding=ft.padding.symmetric(horizontal=8, vertical=2),
                        bgcolor=qc, border_radius=10,
                        content=ft.Text(ql, size=11, color="white", weight=ft.FontWeight.BOLD)),
                ], spacing=2, alignment=ft.MainAxisAlignment.CENTER),
            ], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
            # 评分进度条
            ft.Container(width=180, height=8, bgcolor=_C.TRACK, border_radius=4,
                content=ft.Container(width=int(q * 1.8), height=8,
                    gradient=ft.LinearGradient(begin=ft.alignment.center_left,
                        end=ft.alignment.center_right, colors=[qc, ft.Colors.with_opacity(0.6, qc)]),
                    border_radius=4)),
            ft.Row([
                ft.Column([
                    ft.Text(f"{result['risk']*100:.0f}", size=16, weight=ft.FontWeight.BOLD, color=rc),
                    ft.Text("风险分", size=9, color=_C.TEXT_SEC),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=1),
                ft.Container(width=1, height=24, bgcolor=_C.TEXT_LT),
                ft.Column([
                    ft.Text(rl, size=16, weight=ft.FontWeight.BOLD, color=rc),
                    ft.Text("风险等级", size=9, color=_C.TEXT_SEC),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=1),
                ft.Container(width=1, height=24, bgcolor=_C.TEXT_LT),
                ft.Column([
                    ft.Text(result['verdict'], size=12, weight=ft.FontWeight.BOLD, color=_C.TEXT),
                    ft.Text("行为判定", size=9, color=_C.TEXT_SEC),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=1),
            ], spacing=12, alignment=ft.MainAxisAlignment.CENTER),
        ], spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=14,
            gradient=ft.LinearGradient(begin=ft.alignment.top_center, end=ft.alignment.bottom_center,
                colors=[ft.Colors.with_opacity(0.08, qc), _C.CARD]),
            border_radius=14,
            border=ft.border.all(1, ft.Colors.with_opacity(0.2, qc)),
            shadow=ft.BoxShadow(blur_radius=8, color="#1000000"))
        # 行为分布堆叠条
        n = result['total']
        segs = [
            (result['absent'], "#94A3B8", "离席"),
            (result['forced'], "#F59E0B", "强答"),
            (result['random'], "#EF4444", "乱点"),
            (result['normal'], "#10B981", "正常"),
        ]
        bar_children = []
        for cnt, color, label in segs:
            if cnt > 0:
                show_text = cnt / n > 0.08
                bar_children.append(ft.Container(
                    expand=cnt, height=26, bgcolor=color,
                    tooltip=f"{label}: {cnt}条 ({cnt/n*100:.0f}%)",
                    alignment=ft.alignment.center,
                    content=ft.Text(f"{cnt}", size=10, color="white",
                                    weight=ft.FontWeight.BOLD) if show_text else None))
        legend = ft.Row([
            ft.Row([ft.Container(width=8, height=8, bgcolor=c, border_radius=2),
                    ft.Text(f"{l} {cnt}", size=9, color=_C.TEXT_SEC)], spacing=2)
            for cnt, c, l in segs
        ], spacing=6, alignment=ft.MainAxisAlignment.CENTER)
        behavior_card = ft.Container(content=ft.Column([
            ft.Text("答题行为分布", size=12, color=_C.TEXT, weight=ft.FontWeight.W_600),
            ft.Container(content=ft.Row(bar_children, spacing=0),
                border_radius=6, clip_behavior=ft.ClipBehavior.ANTI_ALIAS),
            legend,
        ], spacing=5), padding=10, bgcolor=_C.CARD, border_radius=12,
            shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))
        # 关键指标 2x3
        m = [
            ("正确率", f"{result['correct_rate']*100:.0f}%", "#16A34A"),
            ("均时", f"{result['avg_dur']:.1f}s", "#0EA5E9"),
            ("选项熵", f"{result['entropy']:.2f}", "#8B5CF6"),
            ("连续异常", f"{result['max_anomaly']}次", "#EA580C"),
            ("连续同答", f"{result['max_same']}次", "#DC2626"),
            ("濒临超时", f"{result['lm_rate']*100:.0f}%", "#CA8A04"),
        ]
        metric_rows = [ft.Row([self._mini_metric(m[i][0], m[i][1], m[i][2]),
                               self._mini_metric(m[i+1][0], m[i+1][1], m[i+1][2])], spacing=6)
                       for i in range(0, 6, 2)]
        metrics_card = ft.Container(content=ft.Column(
            [ft.Text("关键指标", size=12, color=_C.TEXT, weight=ft.FontWeight.W_600)] + metric_rows,
            spacing=4), padding=10, bgcolor=_C.CARD, border_radius=12,
            shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))
        # 说明
        note = ft.Container(content=ft.Text(
            "分析基于最近全部答题记录：离席=超时未答，强答=超时才答，乱点=1.5秒内作答，"
            "选项熵越低越可能固定选同一选项", size=9, color=_C.TEXT_SEC),
            padding=ft.padding.symmetric(horizontal=4))
        return ft.Column([score_card, behavior_card, metrics_card, note], spacing=8, tight=True)

    # ---------- 热力图（月份分隔线 + 点击弹窗） ----------
    def _heatmap(self, year):
        hist = self._history(year)
        if not hist: return self._empty("该年份暂无记录")
        dc = defaultdict(int); dcorr = defaultdict(int); dscore = defaultdict(int)
        for h in hist:
            d = str(h.get('answer_time', ''))[:10]
            try: dt = datetime.datetime.strptime(d, "%Y-%m-%d").date()
            except: continue
            dc[dt] += 1
            if h.get('is_correct'): dcorr[dt] += 1
            dscore[dt] += h.get('points_change', 0)
        if not dc: return self._empty("该年份暂无记录")
        mx = max(dc.values())
        page_w = getattr(self.page, 'width', 360) or 360
        cell = max(28, min(44, int((page_w - 60) / 7)))
        gap = 2
        wd = ["一", "二", "三", "四", "五", "六", "日"]
        rows = [ft.Row(controls=[ft.Container(width=cell, height=16,
            content=ft.Text(w, size=9, color=_C.TEXT_SEC, text_align=ft.TextAlign.CENTER), alignment=ft.alignment.center) for w in wd], spacing=gap, alignment=ft.MainAxisAlignment.CENTER)]
        for m in range(1, 13):
            md = [d for d in sorted(dc.keys()) if d.month == m]
            if not md: continue
            # 月份分隔线
            if m > 1:
                rows.append(ft.Container(height=1, bgcolor=_C.TEXT_LT,
                    margin=ft.margin.symmetric(vertical=4)))
            # 月份标签
            rows.append(ft.Container(content=ft.Row([
                ft.Container(width=4, height=12, bgcolor=_C.PRIMARY, border_radius=2),
                ft.Text(f"{m}月", size=10, color=_C.PRIMARY_DARK, weight=ft.FontWeight.BOLD),
                ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=14, color=_C.PRIMARY_DARK),
            ], spacing=3, alignment=ft.MainAxisAlignment.CENTER), padding=ft.padding.only(top=2, bottom=2)))
            lead = md[0].weekday()
            cells = [ft.Container(width=cell, height=cell) for _ in range(lead)]
            for d in md:
                cnt = dc[d]; corr = dcorr[d]; acc = (corr/cnt*100) if cnt else 0; sc = dscore[d]
                cells.append(ft.Container(width=cell, height=cell, bgcolor=self._heat_color(cnt, mx),
                    border_radius=4, content=ft.Text(str(d.day), size=9,
                        color="white" if cnt > mx*0.3 else _C.TEXT, weight=ft.FontWeight.W_600,
                        text_align=ft.TextAlign.CENTER), alignment=ft.alignment.center,
                    tooltip=f"{d}\n答题:{cnt} 正确:{corr} 正确率:{acc:.0f}% 积分:{sc}",
                    on_click=lambda e, dd=d, c=cnt, cc=corr, a=acc, s=sc: self._show_day_detail(dd, c, cc, a, s)))
            while len(cells) % 7: cells.append(ft.Container(width=cell, height=cell))
            for i in range(0, len(cells), 7): rows.append(ft.Row(controls=cells[i:i+7], spacing=gap, alignment=ft.MainAxisAlignment.CENTER))
        rows.append(ft.Container(height=6))
        rows.append(ft.Row([ft.Container(width=12, height=12, bgcolor=c, border_radius=3) for c in _C.HEAT]
            + [ft.Text("少→多", size=9, color=_C.TEXT_SEC)], alignment=ft.MainAxisAlignment.CENTER, spacing=3))
        return ft.Column(controls=rows, spacing=0, tight=True,
                         horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def _show_day_detail(self, date_str, count, correct, acc, score):
        dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Container(width=32, height=32, border_radius=16, bgcolor=_C.PRIMARY_LT,
                    content=ft.Icon(ft.Icons.CALENDAR_TODAY, size=16, color=_C.PRIMARY_DARK),
                    alignment=ft.alignment.center),
                ft.Text(f"{date_str}", size=15, weight=ft.FontWeight.BOLD, color=_C.TEXT),
            ], spacing=8),
            content=ft.Container(width=260, content=ft.Column([
                ft.Row([
                    ft.Container(expand=True, content=ft.Column([
                        ft.Text(str(count), size=20, weight=ft.FontWeight.BOLD, color=_C.PRIMARY),
                        ft.Text("答题数", size=10, color=_C.TEXT_SEC),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=6, bgcolor=_C.TRACK, border_radius=8),
                    ft.Container(expand=True, content=ft.Column([
                        ft.Text(str(correct), size=20, weight=ft.FontWeight.BOLD, color="#16A34A"),
                        ft.Text("正确数", size=10, color=_C.TEXT_SEC),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=6, bgcolor=_C.TRACK, border_radius=8),
                ], spacing=6),
                ft.Row([
                    ft.Container(expand=True, content=ft.Column([
                        ft.Text(f"{acc:.0f}%", size=20, weight=ft.FontWeight.BOLD, color=self._acc_color(acc)),
                        ft.Text("正确率", size=10, color=_C.TEXT_SEC),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=6, bgcolor=_C.TRACK, border_radius=8),
                    ft.Container(expand=True, content=ft.Column([
                        ft.Text(f"{score:+d}", size=20, weight=ft.FontWeight.BOLD,
                                color="#16A34A" if score >= 0 else "#DC2626"),
                        ft.Text("积分变化", size=10, color=_C.TEXT_SEC),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=6, bgcolor=_C.TRACK, border_radius=8),
                ], spacing=6),
            ], spacing=6, tight=True)),
            actions=[ft.TextButton("关闭", on_click=lambda e: self.page.close(dlg))],
        )
        self.page.open(dlg)

    # ---------- 构建 ----------
    def build(self):
        self._body = ft.Container(expand=True)
        if self._loaded:
            self._render()
        else:
            self._body.content = self._loading()
            # 在build内部启动异步加载(同英语_preload_all模式，Android上事件处理器中run_task不工作)
            self.page.run_task(self.load_data)
        return ft.Container(content=self._body, bgcolor=_C.BG, expand=True, padding=0)

    async def load_data(self):
        print("[guoxue] load_data 开始执行")
        self._body.content = self._loading()
        self.page.update()
        try:
            self._render()
            self._loaded = True
            print("[guoxue] _render 完成, _loaded=True")
        except Exception as e:
            print(f"[guoxue] _render 失败: {e}")
            import traceback
            traceback.print_exc()
            self._body.content = ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.ERROR_OUTLINE, size=40, color="#DC2626"),
                    ft.Text("加载失败", size=16, weight=ft.FontWeight.BOLD),
                    ft.Text(str(e), size=11, color="#92765A", text_align=ft.TextAlign.CENTER),
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=40, alignment=ft.alignment.center)
        self.page.update()
        print("[guoxue] page.update() 完成")
        # 隐藏全局加载遮罩
        if hasattr(self.page, 'loading_overlay'):
            self.page.loading_overlay.hide()

    # ---------- 交互回调 ----------
    def _select_year(self, year):
        self.view_year = int(year)
        if self._year_ref:
            self._year_ref.value = str(year)
            self._year_ref.update()
        if self._year_sheet:
            try:
                self.page.close(self._year_sheet)
            except Exception:
                pass
            self._year_sheet = None
        if self._chart_area is not None:
            self._chart_area.content = self._heatmap(self.view_year)
            self._chart_area.update()
        if self._title_sub is not None:
            self._title_sub.value = f"{self.view_year}年 · 答题数据总览"
            self._title_sub.update()

    def _open_year_sheet(self, e):
        cy = datetime.date.today().year
        yopts = [str(y) for y in range(cy - 3, cy + 1)]
        controls = [ft.ListTile(
            leading=ft.Icon(ft.Icons.CALENDAR_MONTH, color=_C.PRIMARY),
            title=ft.Text(y, size=16),
            on_click=lambda _, yy=y: self._select_year(yy),
            selected=(str(self.view_year) == y),
        ) for y in yopts]
        self._year_sheet = ft.BottomSheet(
            content=ft.Container(padding=ft.padding.all(16), content=ft.Column([
                ft.Text("选择年份", size=18, weight=ft.FontWeight.BOLD, color=_C.PRIMARY_DARK),
                ft.Divider(height=1),
                ft.ListView(controls=controls, height=300),
            ], spacing=8, tight=True)),
            is_scroll_controlled=False, enable_drag=True,
        )
        self.page.open(self._year_sheet)

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
        controls = []
        for uid, name in self._user_list:
            controls.append(ft.ListTile(
                leading=ft.Icon(ft.Icons.PERSON, color=ft.Colors.GREY_600),
                title=ft.Text(name, size=15),
                on_click=lambda _, u=uid: self._select_user(u),
                selected=(self.selected_user_id == uid),
            ))
        sheet = ft.BottomSheet(
            content=ft.Container(padding=ft.padding.all(16), content=ft.Column([
                ft.Text("选择用户", size=18, weight=ft.FontWeight.BOLD, color=_C.PRIMARY_DARK),
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
        self.page.run_task(self._reload)

    def _on_overview_range(self, mode):
        self._overview_range = mode
        if self._overview_area is not None:
            self._overview_area.content = self._overview(self._cached_daily_answers)
            self._overview_area.update()

    def _on_trend_mode(self, mode):
        self._trend_mode = mode
        if self._trend_area is not None:
            self._trend_area.content = self._trend(self._cached_daily, self._cached_daily_answers)
            self._trend_area.update()
        # 更新标题
        if self._trend_title_ref[0] is not None:
            self._trend_title_ref[0].value = "每轮正确率趋势（近30轮）" if mode == 'round' else "每日答题趋势（近30天）"
            try:
                self._trend_title_ref[0].update()
            except Exception:
                pass
        if self._trend_switch is not None:
            opts = [('round', '按轮次'), ('count', '答题数')]
            new_bar = self._mode_switch(opts, mode, self._on_trend_mode)
            self._trend_switch.content = new_bar.content
            self._trend_switch.update()

    def _on_rank_mode(self, mode):
        self._rank_mode = mode
        if self._rank_area is not None:
            self._rank_area.content = self._ranking(self._cached_qs)
            self._rank_area.update()
        if self._rank_switch is not None:
            opts = [('count', '答题数'), ('accuracy', '正确率'), ('duration', '用时')]
            new_bar = self._mode_switch(opts, mode, self._on_rank_mode)
            self._rank_switch.content = new_bar.content
            self._rank_switch.update()

    def _on_accuracy_range(self, days):
        self._accuracy_range = days
        if self._accuracy_area is not None:
            self._accuracy_area.content = self._accuracy_trend(self._cached_daily)
            self._accuracy_area.update()
        # 重建切换条以更新选中状态
        if self._acc_range_switch is not None:
            opts = [(7, '7天'), (30, '30天'), (90, '90天'), (0, '全部')]
            new_bar = self._mode_switch(opts, days, self._on_accuracy_range)
            self._acc_range_switch.content = new_bar.content
            self._acc_range_switch.update()

    async def _reload(self):
        self._body.content = self._loading()
        self.page.update()
        await asyncio.to_thread(self._render)
        self.page.update()

    def _on_refresh(self, e=None):
        """手动刷新：同步全局user_id+清缓存+重新加载"""
        global_uid = getattr(self.page, 'selected_user_id', None)
        self.selected_user_id = global_uid
        if self._user_name_ref:
            self._user_name_ref.value = self._get_selected_user_name()
        self._cached_daily = None
        self._cached_daily_answers = None
        self._cached_qs = None
        self._weak_show_count = 20
        self._loaded = False
        self.page.run_task(self.load_data)

    # ---------- 渲染 ----------
    def _render(self):
        self._load_users()
        daily = self._daily()
        daily_answers = self._daily_answers()
        qs = self._qsummary()
        self._cached_daily = daily
        self._cached_daily_answers = daily_answers
        self._cached_qs = qs
        self._weak_show_count = 20
        hist = self._history(self.view_year)
        behavior = self._analyze_behavior(hist)

        # 用户选择（胶囊按钮+底部弹出，与首页统一）
        if self.is_admin and self._user_list:
            self._user_name_ref = ft.Text(
                self._get_selected_user_name(), size=13,
                color=_C.PRIMARY_DARK, weight=ft.FontWeight.W_600, no_wrap=True)
            user_ctrl = ft.Container(
                padding=ft.padding.symmetric(horizontal=12, vertical=6),
                bgcolor=ft.Colors.WHITE, border_radius=24,
                shadow=ft.BoxShadow(blur_radius=8, color="#15000000", offset=ft.Offset(0, 1)),
                on_click=self._open_user_sheet,
                content=ft.Row([
                    ft.Container(width=24, height=24, border_radius=12,
                                 gradient=ft.LinearGradient(
                                     begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                                     colors=[_C.PRIMARY, _C.ACCENT]),
                                 content=ft.Icon(ft.Icons.PERSON, size=13, color=ft.Colors.WHITE),
                                 alignment=ft.alignment.center),
                    self._user_name_ref,
                    ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=16, color=_C.PRIMARY),
                ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
            )
        else:
            cur_name = self.user_data.get('username', '未知')
            user_ctrl = ft.Container(
                padding=ft.padding.symmetric(horizontal=12, vertical=6),
                bgcolor=ft.Colors.WHITE, border_radius=24,
                shadow=ft.BoxShadow(blur_radius=8, color="#15000000", offset=ft.Offset(0, 1)),
                content=ft.Row([
                    ft.Container(width=24, height=24, border_radius=12,
                                 gradient=ft.LinearGradient(
                                     begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                                     colors=[_C.PRIMARY, _C.ACCENT]),
                                 content=ft.Icon(ft.Icons.PERSON, size=13, color=ft.Colors.WHITE),
                                 alignment=ft.alignment.center),
                    ft.Text(cur_name, size=13, color=_C.PRIMARY_DARK, weight=ft.FontWeight.W_600, no_wrap=True),
                ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
            )

        # 年份选择(胶囊按钮+底部弹出，仅热力图使用)
        self._year_ref = ft.Text(str(self.view_year), size=13, color=_C.PRIMARY_DARK,
                                 weight=ft.FontWeight.W_700)
        self._ydd = ft.Container(
            padding=ft.padding.symmetric(horizontal=10, vertical=4),
            bgcolor=_C.CARD, border_radius=20,
            shadow=ft.BoxShadow(blur_radius=6, color="#15000000", offset=ft.Offset(0, 1)),
            on_click=self._open_year_sheet,
            content=ft.Row([
                ft.Icon(ft.Icons.CALENDAR_MONTH, size=14, color=_C.PRIMARY),
                self._year_ref,
                ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=14, color=_C.PRIMARY),
            ], spacing=4, alignment=ft.MainAxisAlignment.CENTER),
        )

        header = ft.Row([user_ctrl],
                        alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=6)

        # 维度切换条
        trend_opts = [('round', '按轮次'), ('count', '答题数')]
        trend_bar = self._mode_switch(trend_opts, self._trend_mode, self._on_trend_mode)
        self._trend_switch = trend_bar
        rank_opts = [('count', '答题数'), ('accuracy', '正确率'), ('duration', '用时')]
        rank_bar = self._mode_switch(rank_opts, self._rank_mode, self._on_rank_mode)
        self._rank_switch = rank_bar
        acc_range_opts = [(7, '7天'), (30, '30天'), (90, '90天'), (0, '全部')]
        acc_range_bar = self._mode_switch(acc_range_opts, self._accuracy_range, self._on_accuracy_range)
        self._acc_range_switch = acc_range_bar

        # 区域
        self._overview_area = ft.Container(content=self._overview(daily_answers), bgcolor=_C.CARD,
            border_radius=12, padding=8, shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))
        self._accuracy_area = ft.Container(content=self._accuracy_trend(daily), bgcolor=_C.CARD,
            border_radius=12, padding=8, shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))
        self._trend_area = ft.Container(content=self._trend(daily, daily_answers), bgcolor=_C.CARD,
            border_radius=12, padding=8, shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))
        self._rank_area = ft.Container(content=self._ranking(qs), bgcolor=_C.CARD,
            border_radius=12, padding=8, shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))
        self._weak_area = ft.Container(content=self._weak_section(qs), bgcolor=_C.CARD,
            border_radius=12, padding=8, shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))
        self._chart_area = ft.Container(content=self._heatmap(self.view_year), bgcolor=_C.CARD,
            border_radius=12, padding=8, shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))
        self._behavior_area = ft.Container(content=self._behavior_section(behavior), bgcolor=_C.CARD,
            border_radius=12, padding=8, shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))

        # 标题栏（印章主题化）
        self._title_sub = ft.Text(f"{self.view_year}年 · 答题数据总览", size=10,
            color=ft.Colors.with_opacity(0.85, ft.Colors.WHITE), no_wrap=True)
        seal = ft.Container(
            width=38, height=38, border_radius=6,
            bgcolor=_C.SEAL, border=ft.border.all(2, _C.SEAL_DARK),
            content=ft.Text("学", size=22, color="white", weight=ft.FontWeight.BOLD),
            alignment=ft.alignment.center,
        )
        title_bar = ft.Container(
            content=ft.Row([
                seal,
                ft.Column([
                    ft.Text("国学学习统计", size=18, weight=ft.FontWeight.BOLD, color="white", no_wrap=True),
                    self._title_sub,
                ], spacing=0, tight=True),
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.REFRESH, icon_size=20, icon_color=ft.Colors.WHITE,
                              on_click=self._on_refresh, tooltip="刷新"),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
            gradient=ft.LinearGradient(
                begin=ft.alignment.center_left, end=ft.alignment.center_right,
                colors=[_C.PRIMARY_LT, _C.PRIMARY, _C.PRIMARY_DARK]),
            border_radius=14,
            shadow=ft.BoxShadow(blur_radius=10, color="#20000000", offset=ft.Offset(0, 3)),
        )

        # ---------- 子标签页 ----------
        tab_overview = ft.Tab(
            text="概览", icon=ft.Icons.INSIGHTS,
            content=ft.Container(padding=ft.padding.only(top=6), content=ft.Column([
                self._section("数据概览", ft.Icons.INSIGHTS),
                self._overview_area,
                ft.Container(height=6),
                self._section("正确率趋势", ft.Icons.SHOW_CHART),
                ft.Row([acc_range_bar], alignment=ft.MainAxisAlignment.END),
                ft.Container(height=2),
                self._accuracy_area,
            ], spacing=0, scroll=ft.ScrollMode.ADAPTIVE)))
        tab_trend = ft.Tab(
            text="趋势", icon=ft.Icons.TRENDING_UP,
            content=ft.Container(padding=ft.padding.only(top=6), content=ft.Column([
                self._section("每轮正确率趋势（近30轮）" if self._trend_mode == 'round' else "每日答题趋势（近30天）", ft.Icons.TRENDING_UP, text_ref=self._trend_title_ref),
                ft.Row([trend_bar], alignment=ft.MainAxisAlignment.END),
                ft.Container(height=2),
                self._trend_area,
            ], spacing=0, scroll=ft.ScrollMode.ADAPTIVE)))
        tab_rank = ft.Tab(
            text="排行", icon=ft.Icons.EMOJI_EVENTS,
            content=ft.Container(padding=ft.padding.only(top=6), content=ft.Column([
                self._section("题目掌握排行（Top20）", ft.Icons.EMOJI_EVENTS),
                ft.Row([rank_bar], alignment=ft.MainAxisAlignment.END),
                ft.Container(height=2),
                self._rank_area,
                ft.Container(height=6),
                self._section("薄弱题目专区", ft.Icons.WARNING_AMBER),
                self._weak_area,
            ], spacing=0, scroll=ft.ScrollMode.ADAPTIVE)))
        tab_heat = ft.Tab(
            text="热力图", icon=ft.Icons.CALENDAR_MONTH,
            content=ft.Container(padding=ft.padding.only(top=6), content=ft.Column([
                ft.Row([self._section(f"{self.view_year}年 答题热力图", ft.Icons.CALENDAR_MONTH),
                        ft.Container(expand=True), self._ydd],
                       alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self._chart_area,
            ], spacing=0, scroll=ft.ScrollMode.ADAPTIVE)))
        tab_behavior = ft.Tab(
            text="行为分析", icon=ft.Icons.PSYCHOLOGY,
            content=ft.Container(padding=ft.padding.only(top=6), content=ft.Column([
                self._section("答题行为分析", ft.Icons.PSYCHOLOGY),
                self._behavior_area,
            ], spacing=0, scroll=ft.ScrollMode.ADAPTIVE)))

        sub_tabs = ft.Tabs(
            selected_index=0, animation_duration=200,
            indicator_color=_C.PRIMARY, label_color=_C.PRIMARY_DARK,
            unselected_label_color=_C.TEXT_SEC,
            tabs=[tab_overview, tab_trend, tab_rank, tab_heat, tab_behavior], expand=True,
        )

        self._body.content = ft.Container(padding=ft.padding.all(10), content=ft.Column([
                title_bar, ft.Container(height=8),
                header, ft.Container(height=4),
                sub_tabs,
            ], spacing=0, expand=True))
