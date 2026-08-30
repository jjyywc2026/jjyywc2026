# pages/word_ranking.py
import flet as ft
import time

# 品质/状态颜色
_C = {
    'CARD': ft.Colors.WHITE,
    'BG': '#F5F7FA',
    'PRIMARY': ft.Colors.BLUE_600,
    'TEXT': ft.Colors.GREY_800,
    'SUB': ft.Colors.GREY_500,
    'GREEN': ft.Colors.GREEN_600,
    'RED': ft.Colors.RED_500,
    'ORANGE': ft.Colors.ORANGE_500,
    'BORDER': ft.Colors.GREY_200,
}

# 排序维度
SORT_MODES = [
    ('answers', '答题数', ft.Icons.FORMAT_LIST_NUMBERED),
    ('accuracy', '正确率', ft.Icons.TRACK_CHANGES),
    ('duration', '平均用时', ft.Icons.TIMER),
]

WEAK_THRESHOLD = 60  # 正确率低于60%算薄弱


class WordRankingPage:
    """英语单词掌握排行（同国学排行功能）"""

    def __init__(self, page, user_data, selected_user_id=None):
        self.page = page
        self.user_data = user_data
        self.db = page._local_db   # 走本地副本
        self.is_admin = user_data.get('type') == 'admin'
        self.selected_user_id = selected_user_id or user_data.get('id')
        self._sort_mode = 'answers'
        self._data_cache = None
        self._cache_time = 0
        self._cache_ttl = 300  # 5分钟
        self._weak_offset = 0
        self._weak_loaded = 0
        self._weak_has_more = True
        self._weak_list = None
        self._rank_list = None
        self._sort_bar = None
        self._body = None

    # ============================================================
    # 数据查询
    # ============================================================
    def _query_uid(self):
        return self.selected_user_id

    def _load_data(self, force=False):
        """加载所有单词统计数据（5分钟缓存）"""
        now = time.time()
        if not force and self._data_cache and now - self._cache_time < self._cache_ttl:
            return self._data_cache
        uid = self._query_uid()
        try:
            rows = self.db.fetch_all(
                """SELECT w.word_id, w.word, w.pronunciation, w.meaning, w.example_sentences,
                          COUNT(*) as total_answers,
                          COALESCE(SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END),0) as correct_count,
                          COALESCE(AVG(duration),0) as avg_duration,
                          MAX(answer_time) as last_answer
                   FROM words_answer_records war
                   JOIN words w ON war.word_id = w.word_id
                   WHERE war.user_id = ?
                   GROUP BY w.word_id, w.word, w.pronunciation, w.meaning, w.example_sentences""",
                [uid]
            )
            data = []
            for r in rows:
                total = int(r['total_answers'] or 0)
                correct = int(r['correct_count'] or 0)
                acc = (correct / total * 100) if total > 0 else 0
                data.append({
                    'word_id': r['word_id'],
                    'word': r['word'],
                    'phonetic': (r.get('pronunciation') or '').strip(),
                    'meaning': (r.get('meaning') or '').strip(),
                    'example': (r.get('example_sentences') or '').strip(),
                    'total': total,
                    'correct': correct,
                    'wrong': total - correct,
                    'accuracy': acc,
                    'avg_duration': float(r['avg_duration'] or 0),
                    'last_answer': r.get('last_answer') or '',
                })
            self._data_cache = data
            self._cache_time = now
            return data
        except Exception as e:
            print(f"[word_ranking] 加载失败: {e}")
            return []

    def _get_sorted(self, mode):
        data = self._load_data()
        if mode == 'answers':
            return sorted(data, key=lambda x: x['total'], reverse=True)
        elif mode == 'accuracy':
            return sorted(data, key=lambda x: (x['accuracy'], x['total']), reverse=True)
        else:  # duration
            return sorted(data, key=lambda x: x['avg_duration'], reverse=True)

    def _get_weak(self):
        data = self._load_data()
        return [w for w in data if w['accuracy'] < WEAK_THRESHOLD and w['total'] > 0]

    # ============================================================
    # UI 构建
    # ============================================================
    def build(self):
        self._body = ft.Container(
            content=ft.Column([
                ft.Container(height=40),
                ft.Row([ft.ProgressRing(width=28, height=28, color=ft.Colors.BLUE_400)],
                       alignment=ft.MainAxisAlignment.CENTER),
                ft.Row([ft.Text("加载单词排行中...", size=12, color=_C['SUB'])],
                       alignment=ft.MainAxisAlignment.CENTER),
            ], spacing=8, alignment=ft.MainAxisAlignment.CENTER, expand=True),
            expand=True, padding=ft.padding.symmetric(horizontal=12, vertical=8),
        )
        self.page.run_task(self._reload)
        return self._body

    def refresh(self):
        """同步刷新（tab切换时调用，同heatmap/barchart模式）"""
        self._weak_offset = 0
        self._weak_loaded = 0
        self._weak_has_more = True
        self._render()

    async def _reload(self):
        import asyncio
        await asyncio.sleep(0.05)
        self.refresh()

    def _render(self):
        """完整重渲染（重置分页）"""
        weak = self._get_weak()
        self._weak_loaded = min(20, len(weak))
        self._weak_has_more = len(weak) > 20
        self._rebuild()

    def _rebuild(self):
        """基于当前状态重建UI（Android兼容：Container.content交换）"""
        sorted_data = self._get_sorted(self._sort_mode)
        top20 = sorted_data[:20]
        weak = self._get_weak()

        # 排序切换条
        sort_buttons = []
        for mode, label, icon in SORT_MODES:
            active = self._sort_mode == mode
            sort_buttons.append(ft.Container(
                content=ft.Row([
                    ft.Icon(icon, size=14, color=ft.Colors.WHITE if active else _C['SUB']),
                    ft.Text(label, size=11, color=ft.Colors.WHITE if active else _C['SUB'],
                            weight=ft.FontWeight.W_600 if active else ft.FontWeight.NORMAL),
                ], spacing=3, alignment=ft.MainAxisAlignment.CENTER),
                bgcolor=_C['PRIMARY'] if active else ft.Colors.WHITE,
                border_radius=14, padding=ft.padding.symmetric(horizontal=10, vertical=5),
                on_click=lambda e, m=mode: self._on_sort_change(m),
            ))
        self._sort_bar = ft.Row(sort_buttons, spacing=6, alignment=ft.MainAxisAlignment.CENTER)

        # 排行列表
        rank_tiles = []
        for i, w in enumerate(top20):
            rank_tiles.append(self._rank_tile(i + 1, w))
        if not rank_tiles:
            rank_tiles.append(self._empty("暂无答题数据"))

        # 薄弱题列表（按当前已加载数量）
        weak_tiles = []
        weak_show = weak[:self._weak_loaded]
        for w in weak_show:
            weak_tiles.append(self._weak_tile(w))
        if not weak_tiles:
            weak_tiles.append(self._empty("没有薄弱单词，继续保持！"))

        self._rank_list = ft.Column(rank_tiles, spacing=4, tight=True)
        self._weak_list = ft.Column(weak_tiles, spacing=4, tight=True)

        children = [
            self._section_header("单词掌握排行", ft.Icons.EMOJI_EVENTS, f"共{len(sorted_data)}个单词"),
            self._sort_bar,
            ft.Container(height=4),
            self._rank_list,
            ft.Container(height=12),
            self._section_header("薄弱单词专区", ft.Icons.WARNING_AMBER,
                                 f"正确率<{WEAK_THRESHOLD}% · 共{len(weak)}个"),
            self._weak_list,
        ]
        if self._weak_has_more:
            children.append(self._load_more_btn())
        self._body.content = ft.Column(
            children, scroll=ft.ScrollMode.ADAPTIVE, spacing=10, expand=True)
        try:
            self.page.update()
        except Exception:
            pass

    def _on_sort_change(self, mode):
        self._sort_mode = mode
        self._rebuild()

    def _rank_tile(self, rank, w):
        # 排名颜色
        if rank == 1:
            rank_bg = ft.Colors.AMBER_500
            rank_icon = ft.Icons.LOOKS_ONE
        elif rank == 2:
            rank_bg = ft.Colors.GREY_500
            rank_icon = ft.Icons.LOOKS_TWO
        elif rank == 3:
            rank_bg = ft.Colors.ORANGE_700
            rank_icon = ft.Icons.LOOKS_3
        else:
            rank_bg = ft.Colors.GREY_300
            rank_icon = None

        acc_color = _C['GREEN'] if w['accuracy'] >= 80 else (_C['ORANGE'] if w['accuracy'] >= 60 else _C['RED'])
        bar_w = min(w['accuracy'], 100)

        # 小标签
        tags = []
        if w['accuracy'] >= 90:
            tags.append(ft.Container(content=ft.Text("精通", size=8, color=ft.Colors.WHITE, weight=ft.FontWeight.W_700),
                                     bgcolor=ft.Colors.GREEN_600, border_radius=6,
                                     padding=ft.padding.symmetric(horizontal=5, vertical=1)))
        elif w['accuracy'] >= 70:
            tags.append(ft.Container(content=ft.Text("熟练", size=8, color=ft.Colors.WHITE, weight=ft.FontWeight.W_700),
                                     bgcolor=ft.Colors.TEAL_500, border_radius=6,
                                     padding=ft.padding.symmetric(horizontal=5, vertical=1)))
        elif w['accuracy'] >= 50:
            tags.append(ft.Container(content=ft.Text("一般", size=8, color=ft.Colors.WHITE, weight=ft.FontWeight.W_700),
                                     bgcolor=ft.Colors.ORANGE_500, border_radius=6,
                                     padding=ft.padding.symmetric(horizontal=5, vertical=1)))
        else:
            tags.append(ft.Container(content=ft.Text("薄弱", size=8, color=ft.Colors.WHITE, weight=ft.FontWeight.W_700),
                                     bgcolor=ft.Colors.RED_500, border_radius=6,
                                     padding=ft.padding.symmetric(horizontal=5, vertical=1)))
        if w['total'] >= 50:
            tags.append(ft.Container(content=ft.Text("高频", size=8, color=ft.Colors.WHITE, weight=ft.FontWeight.W_700),
                                     bgcolor=ft.Colors.PURPLE_500, border_radius=6,
                                     padding=ft.padding.symmetric(horizontal=5, vertical=1)))
        elif w['total'] <= 3:
            tags.append(ft.Container(content=ft.Text("新词", size=8, color=ft.Colors.WHITE, weight=ft.FontWeight.W_700),
                                     bgcolor=ft.Colors.BLUE_400, border_radius=6,
                                     padding=ft.padding.symmetric(horizontal=5, vertical=1)))
        if w['avg_duration'] > 8:
            tags.append(ft.Container(content=ft.Text("耗时", size=8, color=ft.Colors.WHITE, weight=ft.FontWeight.W_700),
                                     bgcolor=ft.Colors.RED_400, border_radius=6,
                                     padding=ft.padding.symmetric(horizontal=5, vertical=1)))

        leading = ft.Container(
            content=(ft.Icon(rank_icon, size=16, color=ft.Colors.WHITE) if rank_icon
                     else ft.Text(str(rank), size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)),
            width=28, height=28, border_radius=14, bgcolor=rank_bg,
            alignment=ft.alignment.center,
        )

        return ft.Container(
            content=ft.Row([
                leading,
                ft.Container(width=8),
                ft.Column([
                    ft.Row([
                        ft.Text(w['word'], size=14, weight=ft.FontWeight.W_600, color=_C['TEXT'],
                                no_wrap=True, expand=True),
                        ft.Text(f"  {w['phonetic']}", size=10, color=_C['SUB']) if w['phonetic'] else ft.Container(),
                    ], spacing=0, tight=True),
                    ft.Container(height=2),
                    ft.Row(tags + [
                        ft.Container(
                            content=ft.Container(width=bar_w * 1.0, height=4, bgcolor=acc_color, border_radius=2),
                            width=80, height=4, bgcolor=ft.Colors.GREY_200, border_radius=2,
                        ),
                        ft.Text(f"{w['accuracy']:.0f}%", size=10, color=acc_color, weight=ft.FontWeight.W_600),
                    ], spacing=4, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ], spacing=1, tight=True, expand=True),
                ft.Column([
                    ft.Text(f"{w['total']}次", size=11, color=_C['SUB']),
                    ft.Text(f"{w['avg_duration']:.1f}s", size=10, color=_C['SUB']),
                ], spacing=1, tight=True, horizontal_alignment=ft.CrossAxisAlignment.END),
            ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=_C['CARD'], border_radius=10, padding=10,
            on_click=lambda e, word=w: self._show_word_detail(word),
        )

    def _weak_tile(self, w):
        wrong_rate = 100 - w['accuracy']
        return ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Icon(ft.Icons.ERROR_OUTLINE, size=14, color=ft.Colors.WHITE),
                    width=24, height=24, border_radius=12, bgcolor=_C['RED'],
                    alignment=ft.alignment.center,
                ),
                ft.Container(width=8),
                ft.Column([
                    ft.Row([
                        ft.Text(w['word'], size=13, weight=ft.FontWeight.W_600, color=_C['TEXT'],
                                no_wrap=True, expand=True),
                        ft.Container(content=ft.Text(f"错{w['wrong']}次", size=8, color=ft.Colors.WHITE, weight=ft.FontWeight.W_700),
                                     bgcolor=ft.Colors.RED_500, border_radius=6,
                                     padding=ft.padding.symmetric(horizontal=5, vertical=1)),
                        ft.Container(content=ft.Text(f"{wrong_rate:.0f}%错", size=8, color=ft.Colors.WHITE, weight=ft.FontWeight.W_700),
                                     bgcolor=ft.Colors.DEEP_ORANGE_500, border_radius=6,
                                     padding=ft.padding.symmetric(horizontal=5, vertical=1)),
                    ], spacing=4, tight=True),
                    ft.Text(f"答{w['total']}次 对{w['correct']}次",
                            size=10, color=_C['SUB']),
                ], spacing=1, tight=True, expand=True),
                ft.Text(f"{w['accuracy']:.0f}%", size=13, color=_C['RED'], weight=ft.FontWeight.BOLD),
            ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor='#FFF5F5', border_radius=8, padding=8,
            border=ft.border.all(0.5, '#FFCDD2'),
            on_click=lambda e, word=w: self._show_word_detail(word),
        )

    def _load_more_btn(self):
        return ft.Container(
            content=ft.TextButton("查看更多薄弱单词", on_click=lambda e: self.page.run_task(self._load_more_weak)),
            alignment=ft.alignment.center, padding=ft.padding.symmetric(vertical=8),
        )

    async def _load_more_weak(self):
        import asyncio
        await asyncio.sleep(0.05)
        weak = self._get_weak()
        start = self._weak_loaded
        more = weak[start:start + 10]
        if not more:
            self._weak_has_more = False
        else:
            self._weak_loaded += len(more)
            if len(more) < 10:
                self._weak_has_more = False
        self._rebuild()

    # ============================================================
    # 单词详情弹窗
    # ============================================================
    def _show_word_detail(self, w):
        meaning = w.get('meaning') or '暂无释义'
        example = w.get('example') or '暂无例句'
        content = ft.Column([
            ft.Row([
                ft.Text(w['word'], size=22, weight=ft.FontWeight.BOLD, color=_C['PRIMARY']),
                ft.Text(f"  {w['phonetic']}", size=14, color=_C['SUB']) if w['phonetic'] else ft.Container(),
            ], spacing=0),
            ft.Container(height=8),
            ft.Container(
                content=ft.Column([
                    ft.Text("释义", size=11, color=_C['SUB'], weight=ft.FontWeight.W_600),
                    ft.Text(meaning, size=13, color=_C['TEXT']),
                ], spacing=3, tight=True),
                bgcolor='#F8F9FA', border_radius=8, padding=10,
            ),
            ft.Container(height=6),
            ft.Container(
                content=ft.Column([
                    ft.Text("例句", size=11, color=_C['SUB'], weight=ft.FontWeight.W_600),
                    ft.Text(example, size=12, color=_C['TEXT'], italic=True),
                ], spacing=3, tight=True),
                bgcolor='#F8F9FA', border_radius=8, padding=10,
            ),
            ft.Container(height=8),
            ft.Row([
                self._stat_box("答题次数", str(w['total']), _C['PRIMARY']),
                self._stat_box("正确", str(w['correct']), _C['GREEN']),
                self._stat_box("错误", str(w['wrong']), _C['RED']),
            ], spacing=8),
            ft.Container(height=8),
            ft.Row([
                self._stat_box("正确率", f"{w['accuracy']:.1f}%",
                               _C['GREEN'] if w['accuracy'] >= 80 else (_C['ORANGE'] if w['accuracy'] >= 60 else _C['RED'])),
                self._stat_box("平均用时", f"{w['avg_duration']:.1f}秒", _C['ORANGE']),
            ], spacing=8),
            ft.Container(height=8),
            ft.Text(f"最近答题: {w['last_answer'] or '无记录'}", size=11, color=_C['SUB']),
        ], spacing=0, tight=True, scroll=ft.ScrollMode.ADAPTIVE)

        dlg = ft.AlertDialog(
            title=ft.Text("单词详情", size=16),
            content=content,
            actions=[ft.TextButton("关闭", on_click=lambda e: self.page.close(dlg))],
        )
        self.page.open(dlg)

    def _stat_box(self, label, value, color):
        return ft.Container(
            content=ft.Column([
                ft.Text(value, size=16, weight=ft.FontWeight.BOLD, color=color),
                ft.Text(label, size=10, color=_C['SUB']),
            ], spacing=2, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor='#F8F9FA', border_radius=8, padding=10, expand=True,
            alignment=ft.alignment.center,
        )

    # ============================================================
    # 通用组件
    # ============================================================
    def _section_header(self, title, icon, subtitle=""):
        return ft.Row([
            ft.Container(
                content=ft.Icon(icon, size=16, color=ft.Colors.WHITE),
                width=28, height=28, border_radius=8, bgcolor=_C['PRIMARY'],
                alignment=ft.alignment.center,
            ),
            ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=_C['TEXT']),
            ft.Text(subtitle, size=10, color=_C['SUB']) if subtitle else ft.Container(),
        ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _empty(self, text):
        return ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.INBOX, size=40, color=ft.Colors.GREY_300),
                ft.Text(text, size=12, color=ft.Colors.GREY_400),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
            padding=30, alignment=ft.alignment.center,
        )
