# pages/overview.py
import flet as ft
import asyncio
import time
from pages.word_scoring import compute_all_scores

class OverviewPage:
    def __init__(self, page: ft.Page, user_data: dict, selected_user_id, selected_grade):
        self.page = page
        self.user_data = user_data
        self.is_admin = user_data.get('type') == "admin"
        self.db = page._local_db   # 走本地副本
        self.loading = page.loading_overlay

        self.selected_user_id = selected_user_id
        self.selected_grade = selected_grade
        self.user_list = []
        self.grade_list = ['全部']
        self.grade_sheet = None
        self._grade_name_ref = None
        self.data = {}
        self._data_cache = None   # (timestamp, uid, grade, data)  5分钟TTL
        self._cache_ttl = 300
        self.content = ft.Column(spacing=4, scroll=ft.ScrollMode.ADAPTIVE)

    def _snack(self, msg):
        sb = ft.SnackBar(content=ft.Text(msg), duration=2000)
        try:
            self.page.open(sb)
        except AttributeError:
            self.page.snack_bar = sb
            sb.open = True
            self.page.update()

    async def load_data(self):
        self.loading.show("加载概览数据...")
        await asyncio.sleep(0.12)
        await asyncio.gather(
            self._load_user_list(),
            self._load_grade_list(),
            self._load_data()
        )
        self.loading.hide()
        self._build_ui()
        self.page.update()

    async def _refresh_silent(self):
        """静默刷新：不显示loading，切换年级/用户时用（读缓存优先）"""
        await self._load_data()
        self._build_ui()
        self.page.update()

    async def _load_user_list(self):
        try:
            if self.is_admin:
                rows = self.db.fetch_all("SELECT user_id, username FROM users ORDER BY username")
                self.user_list = [(row['user_id'], row['username']) for row in rows] if rows else []
            else:
                self.user_list = [(self.user_data.get('id'), self.user_data.get('username'))]
        except Exception as e:
            print(f"加载用户列表失败: {e}")
            self.user_list = [(self.user_data.get('id'), self.user_data.get('username'))]

    async def _load_grade_list(self):
        try:
            rows = self.db.fetch_all("SELECT grade_name FROM grades ORDER BY grade_id")
            grades = [r['grade_name'] for r in rows] if rows else []
            self.grade_list = ['全部'] + grades
        except Exception as e:
            print(f"加载年级列表失败: {e}")
            self.grade_list = ['全部']

    async def _load_data(self):
        try:
            uid = self.selected_user_id if self.selected_user_id is not None else None
            grade = None if self.selected_grade == '全部' else self.selected_grade
            # 5分钟缓存：相同用户+年级直接复用
            now = time.time()
            if (self._data_cache is not None
                    and self._data_cache[1] == uid
                    and self._data_cache[2] == grade
                    and now - self._data_cache[0] < self._cache_ttl):
                self.data = self._data_cache[3]
                return
            self.data = await asyncio.to_thread(self._query_overview, uid, grade)
            self._data_cache = (now, uid, grade, self.data)
        except Exception as e:
            print(f"数据加载异常: {e}")
            if not self.data:
                self.data = self._empty_data()
            self._snack("数据刷新失败，显示缓存数据")

    def _empty_data(self):
        return {
            'word_total': 0, 'mastered': 0, 'total_attempts': 0,
            'total_hours': 0, 'total_learned': 0, 'unlearned': 0,
            'mastery_rate': 0, 'avg_duration': 0, 'clue_dependency': 0,
            'avg_mastery_score': 0, 'daily_avg': 0,
            'best_grade': '无数据', 'worst_grade': '无数据',
            'unmastered': 0,
        }

    def _query_overview(self, uid, grade):
        """从本地库查询概览数据"""
        d = self._empty_data()
        if uid is None:
            return d

        # ---- 年级过滤的 word_id 列表 ----
        if grade:
            grade_words = self.db.fetch_all(
                "SELECT w.word_id FROM words w "
                "JOIN units u ON w.unit_id=u.unit_id "
                "JOIN volumes v ON u.volume_id=v.volume_id "
                "JOIN grades g ON v.grade_id=g.grade_id "
                "WHERE g.grade_name=?",
                [grade]
            )
            grade_word_ids = set(int(r['word_id']) for r in grade_words)
        else:
            grade_word_ids = None

        # ---- 总单词数 ----
        if grade:
            d['word_total'] = len(grade_word_ids)
        else:
            row = self.db.fetch_one("SELECT COUNT(*) as cnt FROM words")
            d['word_total'] = int(row['cnt']) if row else 0

        # ---- 评分算法：只计算一次，全量单词评分 ----
        all_scores = compute_all_scores(self.db, uid)
        if grade_word_ids is not None:
            scores = {wid: s for wid, s in all_scores.items() if wid in grade_word_ids}
        else:
            scores = all_scores

        total_learned = len(scores)
        mastered = sum(1 for _, st in scores.values() if st == 'mastered')
        unmastered = total_learned - mastered
        avg_score = sum(s for s, _ in scores.values()) / total_learned if total_learned else 0

        d['total_learned'] = total_learned
        d['unlearned'] = max(0, d['word_total'] - total_learned)
        d['mastered'] = mastered
        d['unmastered'] = unmastered
        d['mastery_rate'] = (mastered / total_learned * 100) if total_learned else 0
        d['avg_mastery_score'] = avg_score

        # ---- 答题记录统计 ----
        if grade_word_ids is not None:
            if not grade_word_ids:
                # 该年级无单词，所有答题统计为0
                d['total_attempts'] = 0
                d['total_hours'] = 0
                d['avg_duration'] = 0
                d['clue_dependency'] = 0
                d['daily_avg'] = 0
            else:
                ph = ','.join(['?'] * len(grade_word_ids))
                where = f"WHERE user_id=? AND word_id IN ({ph})"
                params = [uid] + list(grade_word_ids)
                ans_row = self.db.fetch_one(
                    f"SELECT COUNT(*) as cnt, COALESCE(SUM(duration),0) as dur, "
                    f"COALESCE(SUM(used_clue),0) as clues FROM words_answer_records {where}",
                    params
                )
                if ans_row:
                    d['total_attempts'] = int(ans_row['cnt'] or 0)
                    d['total_hours'] = float(ans_row['dur'] or 0) / 3600.0
                    d['avg_duration'] = (float(ans_row['dur'] or 0) / int(ans_row['cnt'] or 1)) if ans_row['cnt'] else 0
                    d['clue_dependency'] = (float(ans_row['clues'] or 0) / int(ans_row['cnt'] or 1)) if ans_row['cnt'] else 0
                # 日均学习（最近30天）
                active_row = self.db.fetch_one(
                    f"SELECT COUNT(DISTINCT DATE(answer_time)) as days FROM words_answer_records "
                    f"{where} AND answer_time >= DATE('now','-30 days')",
                    params
                )
                active_days = int(active_row['days'] or 0) if active_row else 0
                if active_days > 0:
                    recent_row = self.db.fetch_one(
                        f"SELECT COUNT(DISTINCT word_id) as cnt FROM words_answer_records "
                        f"{where} AND answer_time >= DATE('now','-30 days')",
                        params
                    )
                    recent_cnt = int(recent_row['cnt'] or 0) if recent_row else 0
                    d['daily_avg'] = recent_cnt / active_days
                else:
                    d['daily_avg'] = 0
        else:
            where = "WHERE user_id=?"
            params = [uid]
            ans_row = self.db.fetch_one(
                f"SELECT COUNT(*) as cnt, COALESCE(SUM(duration),0) as dur, "
                f"COALESCE(SUM(used_clue),0) as clues FROM words_answer_records {where}",
                params
            )
            if ans_row:
                d['total_attempts'] = int(ans_row['cnt'] or 0)
                d['total_hours'] = float(ans_row['dur'] or 0) / 3600.0
                d['avg_duration'] = (float(ans_row['dur'] or 0) / int(ans_row['cnt'] or 1)) if ans_row['cnt'] else 0
                d['clue_dependency'] = (float(ans_row['clues'] or 0) / int(ans_row['cnt'] or 1)) if ans_row['cnt'] else 0
            # 日均学习（最近30天）
            active_row = self.db.fetch_one(
                f"SELECT COUNT(DISTINCT DATE(answer_time)) as days FROM words_answer_records "
                f"{where} AND answer_time >= DATE('now','-30 days')",
                params
            )
            active_days = int(active_row['days'] or 0) if active_row else 0
            if active_days > 0:
                recent_row = self.db.fetch_one(
                    f"SELECT COUNT(DISTINCT word_id) as cnt FROM words_answer_records "
                    f"{where} AND answer_time >= DATE('now','-30 days')",
                    params
                )
                recent_cnt = int(recent_row['cnt'] or 0) if recent_row else 0
                d['daily_avg'] = recent_cnt / active_days
            else:
                d['daily_avg'] = 0

        # ---- 各年级掌握率（复用上面已算好的 all_scores，不重复计算） ----
        all_grades = self.db.fetch_all("SELECT grade_name FROM grades ORDER BY grade_id")
        grade_rates = []
        for g in all_grades:
            gname = g['grade_name']
            gwords = self.db.fetch_all(
                "SELECT w.word_id FROM words w "
                "JOIN units u ON w.unit_id=u.unit_id "
                "JOIN volumes v ON u.volume_id=v.volume_id "
                "JOIN grades gr ON v.grade_id=gr.grade_id "
                "WHERE gr.grade_name=?",
                [gname]
            )
            gids = set(int(r['word_id']) for r in gwords)
            g_scores = {wid: s for wid, s in all_scores.items() if wid in gids}
            g_total = len(g_scores)
            g_mastered = sum(1 for _, st in g_scores.values() if st == 'mastered')
            if g_total > 0:
                grade_rates.append((gname, g_mastered / g_total))
        if grade_rates:
            grade_rates.sort(key=lambda x: x[1])
            d['worst_grade'] = grade_rates[0][0]
            d['best_grade'] = grade_rates[-1][0]

        # ---- 选中具体年级时：计算单元级最高/最低掌握 ----
        if grade and grade_word_ids:
            unit_rows = self.db.fetch_all(
                "SELECT u.unit_id, u.unit_name, v.volume_type "
                "FROM units u JOIN volumes v ON u.volume_id=v.volume_id "
                "JOIN grades g ON v.grade_id=g.grade_id "
                "WHERE g.grade_name=? ORDER BY v.volume_type, u.unit_name",
                [grade]
            )
            unit_rates = []
            for ur in (unit_rows or []):
                uw_ids = set(int(r['word_id']) for r in self.db.fetch_all(
                    "SELECT word_id FROM words WHERE unit_id=?", [ur['unit_id']]))
                u_scores = {wid: s for wid, s in all_scores.items() if wid in uw_ids}
                u_total = len(u_scores)
                if u_total > 0:
                    u_mastered = sum(1 for _, st in u_scores.values() if st == 'mastered')
                    unit_rates.append((ur['unit_name'], u_mastered / u_total))
            if unit_rates:
                unit_rates.sort(key=lambda x: x[1])
                d['worst_unit'] = unit_rates[0][0]
                d['best_unit'] = unit_rates[-1][0]
            else:
                d['worst_unit'] = '无数据'
                d['best_unit'] = '无数据'
        return d

    def _get_selected_user_name(self):
        if self.selected_user_id is None:
            return "全部"
        for uid, name in self.user_list:
            if uid == self.selected_user_id:
                return name
        return self.user_data.get("username", "未知")

    def _open_user_sheet(self, e):
        if not self.is_admin:
            self._snack("您没有权限查看其他用户数据")
            return
        controls = [ft.ListTile(leading=ft.Icon(ft.Icons.PEOPLE, color=ft.Colors.BLUE_500), title=ft.Text("全部用户", size=16), on_click=lambda _: self._select_user(None), selected=self.selected_user_id is None, selected_color=ft.Colors.BLUE_700)]
        for uid, name in self.user_list:
            controls.append(ft.ListTile(leading=ft.Icon(ft.Icons.PERSON, color=ft.Colors.GREY_600), title=ft.Text(name, size=16), on_click=lambda _, u=uid: self._select_user(u), selected=self.selected_user_id == uid, selected_color=ft.Colors.BLUE_700))
        self.user_sheet = ft.BottomSheet(content=ft.Container(padding=ft.padding.all(16), content=ft.Column([ft.Text("选择用户", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800), ft.Divider(height=1), ft.ListView(controls=controls, height=300)], spacing=12)), is_scroll_controlled=False, enable_drag=True)
        self.page.open(self.user_sheet)

    def _select_user(self, user_id):
        if not self.is_admin: return
        self.selected_user_id = user_id
        self.user_data['home_filter']['selected_user_id'] = user_id
        self._data_cache = None
        if self.user_sheet: self.page.close(self.user_sheet)
        self.page.update()
        if getattr(self, 'on_user_change', None):
            self.on_user_change(user_id)

    def _open_grade_sheet(self, e):
        controls = [ft.ListTile(leading=ft.Icon(ft.Icons.BOOK, color=ft.Colors.GREEN_500), title=ft.Text(grade, size=16), on_click=lambda _, g=grade: self._select_grade(g), selected=self.selected_grade == grade, selected_color=ft.Colors.GREEN_700) for grade in self.grade_list]
        self.grade_sheet = ft.BottomSheet(content=ft.Container(padding=ft.padding.all(16), content=ft.Column([ft.Text("选择年级", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_800), ft.Divider(height=1), ft.ListView(controls=controls, height=300)], spacing=12)), is_scroll_controlled=False, enable_drag=True)
        self.page.open(self.grade_sheet)

    def _select_grade(self, grade):
        self.selected_grade = grade
        self.user_data['home_filter']['selected_grade'] = grade
        self._data_cache = None
        if self._grade_name_ref:
            self._grade_name_ref.value = grade
            self._grade_name_ref.update()
        if self.grade_sheet:
            try:
                self.page.close(self.grade_sheet)
            except Exception:
                pass
            self.grade_sheet = None
        self.page.update()
        if getattr(self, 'on_grade_change', None):
            self.on_grade_change(grade)
        self.page.run_task(self.load_data)

    def _build_ui(self):
        # 年级选择（胶囊按钮+底部弹出，与首页统一）
        self._grade_name_ref = ft.Text(
            self.selected_grade, size=13, color=ft.Colors.GREEN_800,
            weight=ft.FontWeight.W_600, no_wrap=True)
        grade_btn = ft.Container(
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            bgcolor=ft.Colors.WHITE, border_radius=24,
            shadow=ft.BoxShadow(blur_radius=8, color="#15000000", offset=ft.Offset(0, 1)),
            on_click=self._open_grade_sheet,
            content=ft.Row([
                ft.Container(width=24, height=24, border_radius=12,
                             gradient=ft.LinearGradient(
                                 begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                                 colors=[ft.Colors.GREEN_400, ft.Colors.TEAL_600]),
                             content=ft.Icon(ft.Icons.BOOK, size=13, color=ft.Colors.WHITE),
                             alignment=ft.alignment.center),
                self._grade_name_ref,
                ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=16, color=ft.Colors.GREEN_500),
            ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
        )
        filter_row = ft.Container(
            content=ft.Row([ft.Container(expand=True), grade_btn],
                           spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=10, vertical=2),
        )

        # 全部用户视图提示
        all_user_hint = ft.Container()
        if self.selected_user_id is None:
            all_user_hint = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=ft.Colors.AMBER_700),
                    ft.Text("全部用户视图不展示个人统计，请选择具体用户查看数据",
                            size=11, color=ft.Colors.AMBER_800, weight=ft.FontWeight.W_500),
                ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
                bgcolor=ft.Colors.AMBER_50,
                border_radius=12,
                padding=ft.padding.symmetric(horizontal=12, vertical=6),
                margin=ft.margin.symmetric(horizontal=20, vertical=2),
            )

        # 总览卡片
        overview_items = [
            ("总单词数", self.data.get('word_total', 0), ft.Colors.BLUE_700, ft.Icons.BOOK),
            ("掌握率", f"{self.data.get('mastery_rate', 0):.1f}%", ft.Colors.GREEN_700, ft.Icons.PERCENT),
            ("总答题次数", self.data.get('total_attempts', 0), ft.Colors.PURPLE_700, ft.Icons.EDIT),
            ("总学习时长", f"{self.data.get('total_hours', 0):.1f}h", ft.Colors.ORANGE_700, ft.Icons.TIMER),
        ]
        overview_grid = ft.GridView(
            controls=[self._build_overview_item(*item) for item in overview_items],
            runs_count=2, spacing=10, run_spacing=10, child_aspect_ratio=1.6
        )
        overview_card = ft.Container(
            padding=ft.padding.all(16),
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                colors=[ft.Colors.BLUE_50, ft.Colors.INDIGO_50, ft.Colors.PURPLE_50, ft.Colors.PINK_50],
                stops=[0.0, 0.4, 0.7, 1.0]
            ),
            border_radius=28,
            shadow=ft.BoxShadow(blur_radius=24, color=ft.Colors.BLUE_200, spread_radius=2, offset=ft.Offset(0, 3)),
            margin=ft.margin.symmetric(horizontal=20, vertical=8),
            content=ft.Column([overview_grid], spacing=8)
        )

        # 详细指标
        metric_data = [
            ("累计学习", self.data.get('total_learned', 0), ft.Icons.SCHOOL, ft.Colors.PURPLE_600, ft.Colors.PURPLE_100),
            ("未学习", self.data.get('unlearned', 0), ft.Icons.HOURGLASS_TOP, ft.Colors.GREY_600, ft.Colors.GREY_100),
            ("已掌握", self.data.get('mastered', 0), ft.Icons.CHECK_CIRCLE, ft.Colors.GREEN_600, ft.Colors.GREEN_100),
            ("未掌握", self.data.get('unmastered', 0), ft.Icons.CANCEL, ft.Colors.RED_600, ft.Colors.RED_100),
            ("平均作答", f"{self.data.get('avg_duration', 0):.1f}s", ft.Icons.TIMER, ft.Colors.ORANGE_600, ft.Colors.ORANGE_100),
            ("透视卡依赖", f"{self.data.get('clue_dependency', 0)*100:.1f}%", ft.Icons.LIGHTBULB, ft.Colors.PURPLE_600, ft.Colors.PURPLE_100),
        ]
        metric_grid = ft.GridView(
            controls=[self._build_metric_card(*item) for item in metric_data],
            runs_count=3, spacing=10, run_spacing=10, child_aspect_ratio=1.7
        )
        metrics_grid = ft.Container(
            padding=ft.padding.symmetric(horizontal=20, vertical=8),
            content=ft.Column([metric_grid], spacing=4)
        )

        # 迷你卡片
        if self.selected_grade == '全部':
            best = self.data.get('best_grade', '无数据')
            worst = self.data.get('worst_grade', '无数据')
            best_label = "最高年级"
            worst_label = "最低年级"
        else:
            best = self.data.get('best_unit', '无数据')
            worst = self.data.get('worst_unit', '无数据')
            best_label = "最高单元"
            worst_label = "最低单元"
        avg_score = self.data.get('avg_mastery_score', 0)
        daily_avg = self.data.get('daily_avg', 0)
        mini_data = [
            (worst_label, worst, ft.Colors.PINK_200, ft.Icons.ARROW_DOWNWARD),
            (best_label, best, ft.Colors.GREEN_200, ft.Icons.ARROW_UPWARD),
            ("平均掌握评分", f"{avg_score*100:.1f}分", ft.Colors.ORANGE_200, ft.Icons.STAR),
            ("日均学习", f"{daily_avg:.1f}", ft.Colors.PURPLE_200, ft.Icons.CALENDAR_TODAY),
        ]
        mini_grid = ft.GridView(
            controls=[self._build_mini_card(label, value, bg, icon) for label, value, bg, icon in mini_data],
            runs_count=4, spacing=8, run_spacing=8, child_aspect_ratio=1.0
        )
        mini_cards = ft.Container(
            padding=ft.padding.symmetric(horizontal=20, vertical=8),
            content=ft.Column([mini_grid], spacing=4)
        )

        self.content.controls = [filter_row, all_user_hint, overview_card, metrics_grid, mini_cards]

    # ---------- 辅助卡片构建 ----------
    def _build_overview_item(self, label, value, color, icon):
        return ft.Container(
            padding=ft.padding.all(10),
            bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.WHITE),
            border_radius=20,
            shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.GREY_200, spread_radius=1, offset=ft.Offset(0, 2)),
            expand=True,
            content=ft.Column([
                ft.Row([ft.Icon(icon, size=18, color=color), ft.Text(label, size=12, color=ft.Colors.GREY_700, weight=ft.FontWeight.W_600, overflow=ft.TextOverflow.ELLIPSIS)], alignment=ft.MainAxisAlignment.START, spacing=6),
                ft.Text(str(value), size=24, weight=ft.FontWeight.BOLD, color=color, text_align=ft.TextAlign.CENTER, overflow=ft.TextOverflow.ELLIPSIS)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6)
        )

    def _build_metric_card(self, label, value, icon, color, bg_color):
        return ft.Container(
            padding=ft.padding.all(10),
            bgcolor=bg_color,
            border_radius=18,
            shadow=ft.BoxShadow(blur_radius=8, color=ft.Colors.GREY_200, spread_radius=1, offset=ft.Offset(0, 2)),
            content=ft.Column([
                ft.Row([ft.Icon(icon, size=16, color=color), ft.Text(label, size=11, color=ft.Colors.GREY_700, weight=ft.FontWeight.W_500, overflow=ft.TextOverflow.ELLIPSIS)], spacing=4, alignment=ft.MainAxisAlignment.CENTER),
                ft.Text(str(value), size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900, text_align=ft.TextAlign.CENTER, overflow=ft.TextOverflow.ELLIPSIS)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4)
        )

    def _build_mini_card(self, label, value, bg_color, icon):
        return ft.Container(
            padding=ft.padding.all(6),
            bgcolor=bg_color,
            border_radius=14,
            shadow=ft.BoxShadow(blur_radius=6, color=ft.Colors.GREY_200, spread_radius=1, offset=ft.Offset(0, 1)),
            content=ft.Column([
                ft.Icon(icon, size=12, color=ft.Colors.GREY_700),
                ft.Text(str(value), size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900, text_align=ft.TextAlign.CENTER, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(label, size=10, color=ft.Colors.GREY_600, text_align=ft.TextAlign.CENTER, overflow=ft.TextOverflow.ELLIPSIS)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2)
        )

    def build(self):
        return self.content