# pages/cihai.py
import flet as ft
import asyncio
import datetime
from collections import defaultdict


class _C:
    BG = "#EBF5F0"; CARD = "#FFFFFF"
    PRIMARY = "#0D9488"; PRIMARY_DARK = "#0F766E"; PRIMARY_LT = "#5EEAD4"
    ACCENT = "#134E4A"; TEXT = "#134E4A"; TEXT_SEC = "#5E8B82"; TEXT_LT = "#B8D4CC"
    TRACK = "#E0F0EA"; BAMBOO = "#0F766E"; BAMBOO_DARK = "#134E4A"
    HEAT = ["#F0FDFA", "#99F6E4", "#5EEAD4", "#2DD4BF", "#14B8A6", "#0F766E"]
    WEAK_BG = "#F0FDF4"; WEAK_BORDER = "#BBF7D0"


class CihaiPage:
    """辞海学习数据统计（本地库，点击导航时加载）"""

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
        self._trend_mode = 'count'     # count | accuracy | score
        self._rank_mode = 'count'      # count | accuracy | score
        self._overview_range = 'all'   # all | week | month
        self._accuracy_range = 30      # 7 | 30 | 90 | 0(全部→按月)
        self._acc_range_switch = None
        self._trend_switch = None
        self._rank_switch = None
        self._weak_show_count = 20
        # 区域引用
        self._overview_area = None
        self._accuracy_area = None
        self._trend_area = None
        self._rank_area = None
        self._weak_area = None
        # 缓存
        self._cached_hist = []
        self._cached_daily = {}  # aggregated
        self._cached_qs = {}     # aggregated by question

    # ---------- 本地查询 ----------
    def _q(self, sql, params=None):
        try:
            return self.db.fetch_all(sql, params) or []
        except Exception as e:
            print(f"[cihai] query fail: {e}")
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

    def _history(self, year=None):
        if year:
            return self._q("SELECT id, user_id, question_id, answer_duration, score, accuracy, attempt_count, answer_time FROM chinese_sentences_history WHERE user_id=? AND answer_time BETWEEN ? AND ? ORDER BY answer_time",
                           [self.selected_user_id, f"{year}-01-01", f"{year}-12-31"])
        return self._q("SELECT id, user_id, question_id, answer_duration, score, accuracy, attempt_count, answer_time FROM chinese_sentences_history WHERE user_id=? ORDER BY answer_time",
                       [self.selected_user_id])

    def _aggregate(self, hist):
        """聚合为按天和按题目统计"""
        daily = defaultdict(lambda: {'count': 0, 'score': 0, 'acc': 0, 'dur': 0})
        qs = defaultdict(lambda: {'count': 0, 'score': 0, 'acc': 0, 'dur': 0, 'att': 0})
        for h in hist:
            d = str(h.get('answer_time', ''))[:10]
            daily[d]['count'] += 1
            daily[d]['score'] += h.get('score', 0)
            daily[d]['acc'] += h.get('accuracy', 0)
            daily[d]['dur'] += h.get('answer_duration', 0)
            qid = h.get('question_id', '?')
            qs[qid]['count'] += 1
            qs[qid]['score'] += h.get('score', 0)
            qs[qid]['acc'] += h.get('accuracy', 0)
            qs[qid]['dur'] += h.get('answer_duration', 0)
            qs[qid]['att'] += h.get('attempt_count', 0)
        return daily, qs

    # ---------- 时间范围过滤 ----------
    def _filter_hist(self, hist, range_type):
        if range_type == 'all' or not hist:
            return hist
        now = datetime.date.today()
        cutoff = now - datetime.timedelta(days=7 if range_type == 'week' else 30)
        result = []
        for h in hist:
            try:
                dt = datetime.datetime.strptime(str(h.get('answer_time', ''))[:10], "%Y-%m-%d").date()
                if dt >= cutoff:
                    result.append(h)
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
        if acc < 50: return "#DC2626"
        if acc < 70: return "#EA580C"
        if acc < 90: return "#CA8A04"
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

    def _bar_row(self, label, value, mx, tip, value_suffix=""):
        ratio = (value / mx) if mx > 0 else 0
        return ft.Row([
            ft.Container(width=48, content=ft.Text(label, size=10, color=_C.TEXT_SEC,
                            text_align=ft.TextAlign.RIGHT, no_wrap=True)),
            ft.Container(expand=True, height=22, bgcolor=_C.TRACK, border_radius=5,
                content=ft.Stack([
                    ft.Container(width=max(int(ratio * 1000), 2), height=22,
                                 gradient=self._bar_grad(), border_radius=5),
                ]),
                tooltip=tip,
                on_click=lambda e, t=tip: self.page.open(ft.SnackBar(content=ft.Text(t), duration=2000))),
            ft.Container(width=44, content=ft.Text(f"{value:.1f}{value_suffix}" if isinstance(value, float) else f"{value}{value_suffix}", size=10, color=_C.TEXT,
                            weight=ft.FontWeight.W_600, text_align=ft.TextAlign.RIGHT, no_wrap=True)),
        ], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _section(self, text, icon, color=_C.PRIMARY_DARK):
        return ft.Container(content=ft.Row([
            ft.Container(width=4, height=18, border_radius=2,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_center, end=ft.alignment.bottom_center,
                    colors=[color, ft.Colors.with_opacity(0.4, color)])),
            ft.Container(width=26, height=26, border_radius=13,
                bgcolor=ft.Colors.with_opacity(0.1, color),
                content=ft.Icon(icon, size=14, color=color), alignment=ft.alignment.center),
            ft.Text(text, size=13, weight=ft.FontWeight.BOLD, color=color, no_wrap=True),
        ], spacing=6), padding=ft.padding.only(left=2, top=6, bottom=4))

    def _mode_switch(self, options, current, on_change):
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
            ft.Text("加载辞海数据...", size=13, color=_C.TEXT, weight=ft.FontWeight.W_500),
            ft.Text("正在从本地读取词句记录", size=10, color=_C.TEXT_SEC),
        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            expand=True, alignment=ft.alignment.center)

    # ---------- 概览（2x2 + 时间范围） ----------
    def _overview(self, hist):
        filtered = self._filter_hist(hist, self._overview_range)
        if not filtered:
            total = ts = acc = avg = active_days = 0
            last_date = "-"
        else:
            total = len(filtered)
            ts = sum(h.get('score', 0) for h in filtered)
            acc = sum(h.get('accuracy', 0) for h in filtered) / total * 100
            avg = sum(h.get('answer_duration', 0) for h in filtered) / total
            active_days = len(set(str(h.get('answer_time', ''))[:10] for h in filtered))
            last_date = str(filtered[-1].get('answer_time', '-'))[:10]

        range_opts = [('all', '全部'), ('week', '本周'), ('month', '本月')]
        range_bar = self._mode_switch(range_opts, self._overview_range, self._on_overview_range)

        return ft.Column([
            ft.Row([range_bar], alignment=ft.MainAxisAlignment.END),
            ft.Row([
                self._stat_card(ft.Icons.BOOK, total, "总答题", _C.PRIMARY),
                self._stat_card(ft.Icons.STAR, ts, "积分", "#CA8A04"),
            ], spacing=6),
            ft.Row([
                self._stat_card(ft.Icons.PERCENT, f"{acc:.0f}%", "正确率", _C.ACCENT),
                self._stat_card(ft.Icons.TIMER, f"{avg:.0f}s", "均时", "#7C3AED"),
            ], spacing=6),
            ft.Row([
                self._stat_card(ft.Icons.EVENT_AVAILABLE, active_days, "活跃天", "#0EA5E9"),
                self._stat_card(ft.Icons.REPEAT, sum(h.get('attempt_count',0) for h in filtered), "总尝试", "#8B5CF6"),
            ], spacing=6),
            ft.Container(content=ft.Row([
                ft.Icon(ft.Icons.SCHEDULE, size=11, color=_C.TEXT_SEC),
                ft.Text(f"最近学习: {last_date}", size=10, color=_C.TEXT_SEC),
            ], spacing=3, alignment=ft.MainAxisAlignment.CENTER),
                padding=ft.padding.only(top=2)),
        ], spacing=5)

    # ---------- 正确率趋势图（折线图，按天聚合） ----------
    def _accuracy_trend(self, daily):
        if self._accuracy_range == 0:
            # 全部 → 按月聚合
            monthly = defaultdict(lambda: {'total': 0, 'correct': 0})
            for ds, v in daily.items():
                ms = str(ds)[:7]
                monthly[ms]['total'] += v.get('count', 0)
                monthly[ms]['correct'] += v.get('acc', 0)
            keys = sorted(monthly.keys())
            points = [(k, monthly[k]['correct'] / monthly[k]['total'] * 100
                       if monthly[k]['total'] > 0 else 0) for k in keys]
        else:
            days = sorted(daily.keys())[-self._accuracy_range:]
            points = [(d, daily[d]['acc'] / daily[d]['count'] * 100
                       if daily[d]['count'] > 0 else 0) for d in days]
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

        day_cols = []
        for i, (ds, acc) in enumerate(data_points):
            c = self._acc_color(acc)
            tip = f"{ds}\n正确率: {acc:.0f}%"
            spacer_h = max(0, (1 - acc / 100) * H)
            stem_h = max(H - spacer_h, 1)
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

        grid = ft.Container(width=chart_w, height=H, content=ft.Column([
            ft.Container(height=H * 0.25, border=ft.border.only(
                bottom=ft.BorderSide(0.5, _C.TEXT_LT))),
            ft.Container(height=H * 0.25, border=ft.border.only(
                bottom=ft.BorderSide(0.5, _C.TEXT_LT))),
            ft.Container(height=H * 0.25, border=ft.border.only(
                bottom=ft.BorderSide(0.5, _C.TEXT_LT))),
            ft.Container(height=H * 0.25),
        ], spacing=0))

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

    # ---------- 每日趋势（维度切换） ----------
    def _trend(self, daily):
        if not daily: return self._empty("暂无记录")
        # 降序（最新在前），取最近30天
        days = sorted(daily.keys(), reverse=True)[:30]
        if self._trend_mode == 'count':
            mx = max((daily[d]['count'] for d in days), default=1)
            rows = []
            for d in days:
                info = daily[d]
                acc = info['acc'] / info['count'] * 100 if info['count'] else 0
                tip = f"{d}\n答题:{info['count']} 积分:{info['score']} 正确率:{acc:.0f}%"
                rows.append(self._bar_row(d[5:], info['count'], mx, tip))
        elif self._trend_mode == 'accuracy':
            mx = 100
            rows = []
            for d in days:
                info = daily[d]
                acc = info['acc'] / info['count'] * 100 if info['count'] else 0
                tip = f"{d}\n正确率:{acc:.0f}%\n答题:{info['count']} 积分:{info['score']}"
                rows.append(self._bar_row(d[5:], int(acc), mx, tip, value_suffix="%"))
        else:  # score
            mx = max((daily[d]['score'] for d in days), default=1)
            rows = []
            for d in days:
                info = daily[d]
                acc = info['acc'] / info['count'] * 100 if info['count'] else 0
                tip = f"{d}\n积分:{info['score']}\n答题:{info['count']} 正确率:{acc:.0f}%"
                rows.append(self._bar_row(d[5:], info['score'], mx, tip))
        return ft.Column(controls=rows, spacing=2, tight=True,
                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    # ---------- 排行（排序切换） ----------
    def _ranking(self, qs):
        if not qs: return self._empty("暂无记录")
        items = list(qs.items())
        if self._rank_mode == 'count':
            top = sorted(items, key=lambda x: x[1]['count'], reverse=True)[:20]
        elif self._rank_mode == 'accuracy':
            top = sorted(items, key=lambda x: x[1]['acc']/x[1]['count'] if x[1]['count'] else 0, reverse=True)[:20]
        else:  # score
            top = sorted(items, key=lambda x: x[1]['score'], reverse=True)[:20]
        rows = []
        medal_colors = ["#F59E0B", "#94A3B8", "#CD7F32"]
        for i, (qid, s) in enumerate(top):
            acc = s['acc'] / s['count'] * 100 if s['count'] else 0
            avg = s['dur'] / s['count'] if s['count'] else 0
            is_weak = acc < 50
            c = self._acc_color(acc)
            weak_tag = ft.Container(
                content=ft.Text("薄弱", size=8, color="white", weight=ft.FontWeight.BOLD),
                padding=ft.padding.symmetric(horizontal=4, vertical=1),
                bgcolor="#DC2626", border_radius=4, visible=is_weak,
            ) if is_weak else ft.Container(width=0)
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
            tip = f"词句ID:{qid}\n答题:{s['count']} 积分:{s['score']} 正确率:{acc:.0f}% 均时:{avg:.0f}s 尝试:{s['att']}次"
            rows.append(ft.Container(content=ft.Row([
                rank_badge,
                ft.Column([
                    ft.Row([
                        ft.Text(f"词句 {qid}", size=11, weight=ft.FontWeight.W_600, color=_C.TEXT, no_wrap=True),
                        weak_tag,
                    ], spacing=3),
                    ft.Text(f"正确率{acc:.0f}% · 均时{avg:.0f}s · 尝试{s['att']}次", size=9, color=c, no_wrap=True),
                ], spacing=0, tight=True, expand=True),
                ft.Container(expand=True, height=10, bgcolor=_C.TRACK, border_radius=3,
                    content=ft.Container(width=max(int(acc), 2), height=10, bgcolor=c, border_radius=3)),
                ft.Container(width=32, alignment=ft.alignment.center_right,
                             content=ft.Text(f"{s['count']}", size=10, weight=ft.FontWeight.W_600, color=_C.TEXT, no_wrap=True)),
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(horizontal=8, vertical=5),
                gradient=ft.LinearGradient(begin=ft.alignment.center_left, end=ft.alignment.center_right,
                    colors=[_C.WEAK_BG if is_weak else _C.CARD,
                            ft.Colors.with_opacity(0.3, _C.WEAK_BG) if is_weak else _C.CARD]) if is_weak else None,
                bgcolor=None if is_weak else _C.CARD,
                border_radius=8,
                border=ft.border.all(1, _C.WEAK_BORDER) if is_weak else ft.border.all(0.5, ft.Colors.with_opacity(0.15, _C.TEXT_LT)),
                margin=ft.margin.only(bottom=2), tooltip=tip))
        return ft.Column(controls=rows, spacing=0, tight=True,
                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    # ---------- 薄弱题专区 ----------
    def _weak_section(self, qs):
        if not qs:
            return self._empty("暂无记录")
        weak = [(qid, s) for qid, s in qs.items() if s['count'] > 0
                and (s['acc'] / s['count'] * 100) < 50]
        if not weak:
            return ft.Container(content=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color="#16A34A"),
                ft.Text("暂无薄弱词句，继续保持！", size=12, color="#16A34A"),
            ], spacing=6, alignment=ft.MainAxisAlignment.CENTER), padding=16)
        weak = sorted(weak, key=lambda x: x[1]['acc']/x[1]['count'])
        total_weak = len(weak)
        show = weak[:self._weak_show_count]
        rows = []
        for qid, s in show:
            acc = s['acc'] / s['count'] * 100 if s['count'] else 0
            rows.append(ft.Container(content=ft.Row([
                ft.Container(width=24, height=24, border_radius=12, bgcolor="#DC2626",
                    content=ft.Text("!", size=14, color="white", weight=ft.FontWeight.BOLD),
                    alignment=ft.alignment.center),
                ft.Column([
                    ft.Text(f"词句 {qid}", size=11, weight=ft.FontWeight.W_600, color=_C.TEXT, no_wrap=True),
                    ft.Text(f"正确率{acc:.0f}% · 答{s['count']}次", size=9, color="#DC2626", no_wrap=True),
                ], spacing=0, tight=True, expand=True),
                ft.Container(width=50, height=8, bgcolor="#FECACA", border_radius=4,
                    content=ft.Container(width=max(int(acc*0.5), 2), height=8, bgcolor="#DC2626", border_radius=4)),
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(horizontal=8, vertical=5),
                bgcolor="#FEF2F2", border_radius=6, margin=ft.margin.only(bottom=2)))
        if self._weak_show_count < total_weak:
            remaining = total_weak - self._weak_show_count
            rows.append(ft.Container(content=ft.Text(
                f"查看更多（剩余{min(10, remaining)}条，共{total_weak}条）",
                size=11, color=_C.PRIMARY, weight=ft.FontWeight.W_600),
                padding=ft.padding.symmetric(vertical=10), alignment=ft.alignment.center,
                on_click=self._on_load_more_weak,
                gradient=ft.LinearGradient(begin=ft.alignment.center_left,
                    end=ft.alignment.center_right,
                    colors=[ft.Colors.with_opacity(0.12, _C.PRIMARY), ft.Colors.with_opacity(0.05, _C.PRIMARY)]),
                border_radius=8, margin=ft.margin.only(top=4),
                border=ft.border.all(1, ft.Colors.with_opacity(0.2, _C.PRIMARY))))
        return ft.Column(controls=rows, spacing=0, tight=True,
                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    def _on_load_more_weak(self, e):
        self._weak_show_count += 10
        if self._weak_area is not None:
            self._weak_area.content = self._weak_section(self._cached_qs)
            self._weak_area.update()

    # ---------- 热力图（月份分隔线 + 点击弹窗） ----------
    def _heatmap(self, year):
        hist = self._history(year)
        if not hist: return self._empty("该年份暂无记录")
        dc = defaultdict(int); ds = defaultdict(int)
        for h in hist:
            d = str(h.get('answer_time', ''))[:10]
            try: dt = datetime.datetime.strptime(d, "%Y-%m-%d").date()
            except: continue
            dc[dt] += 1
            ds[dt] += h.get('score', 0)
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
            if m > 1:
                rows.append(ft.Container(height=1, bgcolor=_C.TEXT_LT,
                    margin=ft.margin.symmetric(vertical=4)))
            rows.append(ft.Container(content=ft.Row([
                ft.Container(width=4, height=12, bgcolor=_C.PRIMARY, border_radius=2),
                ft.Text(f"{m}月", size=10, color=_C.PRIMARY_DARK, weight=ft.FontWeight.BOLD),
                ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=14, color=_C.PRIMARY_DARK),
            ], spacing=3, alignment=ft.MainAxisAlignment.CENTER), padding=ft.padding.only(top=2, bottom=2)))
            lead = md[0].weekday()
            cells = [ft.Container(width=cell, height=cell) for _ in range(lead)]
            for d in md:
                cnt = dc[d]; sc = ds[d]
                cells.append(ft.Container(width=cell, height=cell, bgcolor=self._heat_color(cnt, mx),
                    border_radius=4, content=ft.Text(str(d.day), size=9,
                        color="white" if cnt > mx*0.3 else _C.TEXT, weight=ft.FontWeight.W_600,
                        text_align=ft.TextAlign.CENTER), alignment=ft.alignment.center,
                    tooltip=f"{d}\n答题:{cnt} 积分:{sc}",
                    on_click=lambda e, dd=d, c=cnt, s=sc: self._show_day_detail(dd, c, s)))
            while len(cells) % 7: cells.append(ft.Container(width=cell, height=cell))
            for i in range(0, len(cells), 7): rows.append(ft.Row(controls=cells[i:i+7], spacing=gap, alignment=ft.MainAxisAlignment.CENTER))
        rows.append(ft.Container(height=6))
        rows.append(ft.Row([ft.Container(width=12, height=12, bgcolor=c, border_radius=3) for c in _C.HEAT]
            + [ft.Text("少→多", size=9, color=_C.TEXT_SEC)], alignment=ft.MainAxisAlignment.CENTER, spacing=3))
        return ft.Column(controls=rows, spacing=0, tight=True,
                         horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def _show_day_detail(self, date_str, count, score):
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
                        ft.Text(str(score), size=20, weight=ft.FontWeight.BOLD, color="#CA8A04"),
                        ft.Text("积分", size=10, color=_C.TEXT_SEC),
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
        print("[cihai] load_data 开始执行")
        import asyncio
        await asyncio.sleep(0.12)  # 让出事件循环，让初始UI先渲染(同英语_preload_all)
        self._body.content = self._loading()
        self.page.update()
        try:
            await asyncio.to_thread(self._render)  # 数据库查询+UI构建放子线程，避免阻塞事件循环
            self._loaded = True
            print("[cihai] _render 完成, _loaded=True")
        except Exception as e:
            print(f"[cihai] _render 失败: {e}")
            import traceback
            traceback.print_exc()
            self._body.content = ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.ERROR_OUTLINE, size=40, color="#DC2626"),
                    ft.Text("加载失败", size=16, weight=ft.FontWeight.BOLD),
                    ft.Text(str(e), size=11, color=_C.TEXT_SEC, text_align=ft.TextAlign.CENTER),
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=40, alignment=ft.alignment.center)
        self.page.update()
        print("[cihai] page.update() 完成")
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
            self._title_sub.value = f"{self.view_year}年 · 词句数据总览"
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
            self._overview_area.content = self._overview(self._cached_hist)
            self._overview_area.update()

    def _on_trend_mode(self, mode):
        self._trend_mode = mode
        if self._trend_area is not None:
            self._trend_area.content = self._trend(self._cached_daily)
            self._trend_area.update()
        if self._trend_switch is not None:
            opts = [('count', '答题数'), ('accuracy', '正确率'), ('score', '积分')]
            new_bar = self._mode_switch(opts, mode, self._on_trend_mode)
            self._trend_switch.content = new_bar.content
            self._trend_switch.update()

    def _on_rank_mode(self, mode):
        self._rank_mode = mode
        if self._rank_area is not None:
            self._rank_area.content = self._ranking(self._cached_qs)
            self._rank_area.update()
        if self._rank_switch is not None:
            opts = [('count', '答题数'), ('accuracy', '正确率'), ('score', '积分')]
            new_bar = self._mode_switch(opts, mode, self._on_rank_mode)
            self._rank_switch.content = new_bar.content
            self._rank_switch.update()

    def _on_accuracy_range(self, days):
        self._accuracy_range = days
        if self._accuracy_area is not None:
            self._accuracy_area.content = self._accuracy_trend(self._cached_daily)
            self._accuracy_area.update()
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
        self._cached_hist = None
        self._cached_daily = None
        self._cached_qs = None
        self._weak_show_count = 20
        self._loaded = False
        self.page.run_task(self.load_data)

    # ---------- 渲染 ----------
    def _render(self):
        self._load_users()
        hist = self._history()
        daily, qs = self._aggregate(hist)
        self._cached_hist = hist
        self._cached_daily = daily
        self._cached_qs = qs
        self._weak_show_count = 20

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

        # 维度切换
        trend_opts = [('count', '答题数'), ('accuracy', '正确率'), ('score', '积分')]
        trend_bar = self._mode_switch(trend_opts, self._trend_mode, self._on_trend_mode)
        self._trend_switch = trend_bar
        rank_opts = [('count', '答题数'), ('accuracy', '正确率'), ('score', '积分')]
        rank_bar = self._mode_switch(rank_opts, self._rank_mode, self._on_rank_mode)
        self._rank_switch = rank_bar
        acc_range_opts = [(7, '7天'), (30, '30天'), (90, '90天'), (0, '全部')]
        acc_range_bar = self._mode_switch(acc_range_opts, self._accuracy_range, self._on_accuracy_range)
        self._acc_range_switch = acc_range_bar

        # 区域
        self._overview_area = ft.Container(content=self._overview(hist), bgcolor=_C.CARD,
            border_radius=12, padding=8, shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))
        self._accuracy_area = ft.Container(content=self._accuracy_trend(daily), bgcolor=_C.CARD,
            border_radius=12, padding=8, shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))
        self._trend_area = ft.Container(content=self._trend(daily), bgcolor=_C.CARD,
            border_radius=12, padding=8, shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))
        self._rank_area = ft.Container(content=self._ranking(qs), bgcolor=_C.CARD,
            border_radius=12, padding=8, shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))
        self._weak_area = ft.Container(content=self._weak_section(qs), bgcolor=_C.CARD,
            border_radius=12, padding=8, shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))
        self._chart_area = ft.Container(content=self._heatmap(self.view_year), bgcolor=_C.CARD,
            border_radius=12, padding=8, shadow=ft.BoxShadow(blur_radius=6, color="#1000000"))

        # 标题栏（竹简主题化）
        self._title_sub = ft.Text(f"{self.view_year}年 · 词句数据总览", size=10,
            color=ft.Colors.with_opacity(0.85, ft.Colors.WHITE), no_wrap=True)
        bamboo = ft.Container(
            width=38, height=38, border_radius=8,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_center, end=ft.alignment.bottom_center,
                colors=[_C.PRIMARY_LT, _C.BAMBOO, _C.BAMBOO_DARK]),
            border=ft.border.all(1.5, _C.BAMBOO_DARK),
            content=ft.Text("辞", size=20, color="white", weight=ft.FontWeight.BOLD),
            alignment=ft.alignment.center,
        )
        title_bar = ft.Container(
            content=ft.Row([
                bamboo,
                ft.Column([
                    ft.Text("辞海学习统计", size=18, weight=ft.FontWeight.BOLD, color="white", no_wrap=True),
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
                self._section("每日答题趋势（近30天）", ft.Icons.TRENDING_UP),
                ft.Row([trend_bar], alignment=ft.MainAxisAlignment.END),
                ft.Container(height=2),
                self._trend_area,
            ], spacing=0, scroll=ft.ScrollMode.ADAPTIVE)))
        tab_rank = ft.Tab(
            text="排行", icon=ft.Icons.EMOJI_EVENTS,
            content=ft.Container(padding=ft.padding.only(top=6), content=ft.Column([
                self._section("词句掌握排行（Top20）", ft.Icons.EMOJI_EVENTS),
                ft.Row([rank_bar], alignment=ft.MainAxisAlignment.END),
                ft.Container(height=2),
                self._rank_area,
                ft.Container(height=6),
                self._section("薄弱词句专区", ft.Icons.WARNING_AMBER),
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

        sub_tabs = ft.Tabs(
            selected_index=0, animation_duration=200,
            indicator_color=_C.PRIMARY, label_color=_C.PRIMARY_DARK,
            unselected_label_color=_C.TEXT_SEC,
            tabs=[tab_overview, tab_trend, tab_rank, tab_heat], expand=True,
        )

        self._body.content = ft.Container(padding=ft.padding.all(10), content=ft.Column([
                title_bar, ft.Container(height=8),
                header, ft.Container(height=4),
                sub_tabs,
            ], spacing=0, expand=True))
