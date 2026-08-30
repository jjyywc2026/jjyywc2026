# pages/barchart.py
import flet as ft
import time
import asyncio
from colorsys import hsv_to_rgb
from pages.word_scoring import compute_all_scores


# ========== 配色 ==========
class _C:
    BG           = "#F0F4F8"
    CARD         = "#FFFFFF"
    PRIMARY      = "#4A90D9"
    PRIMARY_LT   = "#7EC0F5"
    ACCENT       = "#7C6FF0"
    TEXT         = "#2C3E50"
    TEXT_SEC     = "#8A9BB0"
    TRACK        = "#E8EDF3"
    # 单词四类颜色
    CAT_MASTERED  = "#2ECC71"   # 已掌握 绿
    CAT_LEARNING  = "#5B8DEF"   # 待巩固 蓝
    CAT_REVIEW    = "#F5A623"   # 初识期 橙
    CAT_UNMASTER  = "#E74C3C"   # 陌生词 红


# 四类定义（顺序、key、中文名、颜色）
CATEGORIES = [
    ('mastered',  '已掌握', _C.CAT_MASTERED),
    ('learning',  '待巩固', _C.CAT_LEARNING),
    ('review',    '初识期', _C.CAT_REVIEW),
    ('unmastered','陌生词', _C.CAT_UNMASTER),
]

class BarChartPage:
    """单词掌握率条形图 + 四类单词列表（移动端）"""

    def __init__(self, page: ft.Page, user_data: dict, selected_user_id, selected_grade):
        self.page = page
        self.user_data = user_data
        self.selected_user_id = selected_user_id
        self.is_admin = user_data.get('type') == "admin"
        self.db = page._local_db   # 走本地副本查询

        # 从 user_data 提取用户信息
        self.user_id = user_data.get('id', 1)
        self.username = user_data.get('username', '测试用户')

        # 初始状态
        self.selected_grade = selected_grade if selected_grade != '全部' else '全部'
        self.selected_unit = None
        # 若预选了年级则直接进入单元视图
        self._view = 'unit' if self.selected_grade != '全部' else 'grade'
        self._selected_cat = 'mastered'

        # 控件引用
        self._chart_container = None
        self._title_ref = None
        self._back_btn = None
        self._legend_ref = None
        self._user_name_ref = None

        # 用户列表（admin切换用户时用）
        self._user_list = self._load_user_list() if self.is_admin else []

        # 数据缓存（值为 (timestamp, data)，5分钟TTL）
        self.sorted_grades = []
        self._grade_cache = None       # (ts, [{'name','total','mastered'}]) or None
        self._unit_cache = {}          # {grade: (ts, {'上册':[...], '下册':[...]})}
        self._word_cache = {}          # {(grade,unit,vol): (ts, {cat:[...]})}
        self._score_cache = {}         # {cache_key: (ts, {wid:(score,status)})}
        self._cache_ttl = 300          # 5分钟

    # ================================================================
    # 数据库查询
    # ================================================================
    def _query_uid(self):
        return self.selected_user_id if self.selected_user_id is not None else self.user_id

    # ================================================================
    # 评分算法（从 Pygame 版 _calculate_word_mastery 移植）
    # ================================================================
    # 评分算法（调用共享模块 word_scoring）
    # ================================================================
    def _compute_all_scores(self, user_id):
        """批量计算该用户所有单词的掌握度评分，带5分钟缓存"""
        if user_id is None:
            return {}
        cache_key = f"scores_{user_id}"
        now = time.time()
        if cache_key in self._score_cache:
            ts, val = self._score_cache[cache_key]
            if now - ts < self._cache_ttl:
                return val
        self._score_cache[cache_key] = (now, compute_all_scores(self.db, user_id))
        return self._score_cache[cache_key][1]

    # ================================================================
    # 用户切换（标签页内 BottomSheet）
    # ================================================================
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
            return [(self.user_id, self.username)]
        try:
            rows = self.db.fetch_all("SELECT user_id, username FROM users ORDER BY username")
            return [(r['user_id'], r['username']) for r in rows] if rows else []
        except Exception as e:
            print(f"[barchart] 用户列表加载失败: {e}")
            return [(self.user_id, self.username)]

    def _get_selected_user_name(self):
        if self.selected_user_id is None:
            return "全部"
        for uid, name in self._user_list:
            if uid == self.selected_user_id:
                return name
        return self.username

    def _open_user_sheet(self, e):
        if not self.is_admin:
            self._snack("您没有权限查看其他用户数据")
            return
        users = self._load_user_list()
        controls = [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.PEOPLE, color=ft.Colors.BLUE_500),
                title=ft.Text("全部用户", size=16),
                on_click=lambda _: self._select_user(None),
                selected=self.selected_user_id is None,
            )
        ]
        for uid, name in users:
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
        # 清缓存
        self._grade_cache = None
        self._unit_cache.clear()
        self._word_cache.clear()
        if hasattr(self, '_score_cache'):
            self._score_cache.clear()
        # 关闭底部弹窗
        for o in list(self.page.overlay):
            if isinstance(o, ft.BottomSheet):
                self.page.close(o)
        self._view = 'grade'
        self.selected_unit = None
        self.page.update()
        if getattr(self, 'on_user_change', None):
            self.on_user_change(user_id)

    def _load_grades(self):
        """从 grades 表加载年级列表 + 各年级总单词数/已掌握数（用评分算法），5分钟缓存"""
        now = time.time()
        if self._grade_cache is not None:
            ts, items = self._grade_cache
            if now - ts < self._cache_ttl:
                return items
        uid = self._query_uid()
        try:
            total_rows = self.db.fetch_all(
                "SELECT g.grade_name, COUNT(w.word_id) as total "
                "FROM grades g "
                "LEFT JOIN volumes v ON g.grade_id = v.grade_id "
                "LEFT JOIN units u ON v.volume_id = u.volume_id "
                "LEFT JOIN words w ON u.unit_id = w.unit_id "
                "GROUP BY g.grade_id, g.grade_name "
                "ORDER BY g.grade_id"
            )
            # 用评分算法计算已掌握数
            scores = self._compute_all_scores(uid) if uid else {}
            mastered_ids = [wid for wid, (_, st) in scores.items() if st == 'mastered']
            mastered_map = {}
            if mastered_ids:
                ph = ','.join(['?'] * len(mastered_ids))
                mrows = self.db.fetch_all(
                    f"SELECT g.grade_name, COUNT(*) as mastered FROM words w "
                    f"JOIN units u ON w.unit_id=u.unit_id JOIN volumes v ON u.volume_id=v.volume_id "
                    f"JOIN grades g ON v.grade_id=g.grade_id "
                    f"WHERE w.word_id IN ({ph}) GROUP BY g.grade_name",
                    mastered_ids
                )
                mastered_map = {r['grade_name']: int(r['mastered']) for r in mrows}

            items = []
            for r in total_rows:
                gname = r['grade_name']
                total = int(r['total'] or 0)
                mastered = mastered_map.get(gname, 0)
                if total > 0:
                    items.append({'name': gname, 'total': total, 'mastered': mastered})
            self.sorted_grades = [it['name'] for it in items]
            self._grade_cache = (now, items)
        except Exception as e:
            print(f"[barchart] 年级数据加载失败: {e}")
            self._grade_cache = (now, [])
        return self._grade_cache[1]

    def _load_units(self, grade):
        """加载某年级各单元（上册/下册）的总单词数/已掌握数，5分钟缓存"""
        now = time.time()
        if grade in self._unit_cache:
            ts, val = self._unit_cache[grade]
            if now - ts < self._cache_ttl:
                return val
        uid = self._query_uid()
        volumes = {"上册": [], "下册": []}
        try:
            rows = self.db.fetch_all(
                "SELECT u.unit_name, v.volume_type, u.unit_id, "
                "COUNT(DISTINCT w.word_id) as total "
                "FROM words w "
                "JOIN units u ON w.unit_id = u.unit_id "
                "JOIN volumes v ON u.volume_id = v.volume_id "
                "JOIN grades g ON v.grade_id = g.grade_id "
                "WHERE g.grade_name = ? "
                "GROUP BY u.unit_id, u.unit_name, v.volume_type "
                "ORDER BY v.volume_type, u.unit_name",
                [grade]
            )
            # 评分算法计算每个 unit 的 mastered
            scores = self._compute_all_scores(uid) if uid else {}
            mastered_ids = set(wid for wid, (_, st) in scores.items() if st == 'mastered')

            for r in rows:
                vol_raw = str(r['volume_type'] or '')
                vol = '上册' if '上' in vol_raw else '下册'
                # 查该单元的 word_id 列表，统计 mastered
                unit_words = self.db.fetch_all(
                    "SELECT word_id FROM words WHERE unit_id = ?",
                    [r['unit_id']]
                )
                mastered = sum(1 for uw in unit_words if int(uw['word_id']) in mastered_ids)
                volumes[vol].append({
                    'unit': r['unit_name'],
                    'total': int(r['total'] or 0),
                    'mastered': mastered,
                })
        except Exception as e:
            print(f"[barchart] 单元数据加载失败: {e}")
        self._unit_cache[grade] = (now, volumes)
        return volumes

    def _load_words(self, grade, unit_name, volume_type):
        """加载某单元的四类单词详情（用评分算法，包含未学过的单词），5分钟缓存"""
        key = (grade, unit_name, volume_type)
        now = time.time()
        if key in self._word_cache:
            ts, val = self._word_cache[key]
            if now - ts < self._cache_ttl:
                return val
        uid = self._query_uid()
        grouped = {k: [] for k, _, _ in CATEGORIES}
        try:
            # 查该单元所有单词（含未学过的）
            rows = self.db.fetch_all(
                "SELECT w.word_id, w.word, w.meaning "
                "FROM words w "
                "JOIN units u ON w.unit_id = u.unit_id "
                "JOIN volumes v ON u.volume_id = v.volume_id "
                "JOIN grades g ON v.grade_id = g.grade_id "
                "WHERE g.grade_name = ? AND u.unit_name = ? AND v.volume_type = ? "
                "ORDER BY w.word_id",
                [grade, unit_name, volume_type]
            )
            scores = self._compute_all_scores(uid) if uid else {}
            for r in rows:
                wid = int(r['word_id'])
                score, status = scores.get(wid, (0.0, 'unmastered'))
                grouped[status].append((
                    r['word'] or '',
                    r['meaning'] or '',
                    score,
                ))
        except Exception as e:
            print(f"[barchart] 单词数据加载失败: {e}")
        self._word_cache[key] = (now, grouped)
        return grouped

    async def load_data(self):
        """预加载年级数据，刷新视图"""
        self._grade_cache = None
        self._unit_cache.clear()
        self._word_cache.clear()
        self._load_grades()
        if self._chart_container is not None:
            self._refresh()

    async def reload(self, msg="加载中..."):
        """带 loading 的刷新：先在图表区显示转圈，再查数据渲染"""
        if self._chart_container is not None:
            self._chart_container.content = ft.Container(
                content=ft.Column([
                    ft.ProgressRing(width=40, height=40, stroke_width=4, color=_C.PRIMARY),
                    ft.Text(msg, size=14, color=_C.TEXT_SEC),
                ], alignment=ft.MainAxisAlignment.CENTER,
                   horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=14),
                expand=True, alignment=ft.alignment.center,
            )
            self._chart_container.update()
        await asyncio.sleep(0.12)
        try:
            self._refresh()
        finally:
            pass

    # ================================================================
    # 颜色：HSL 红→黄→绿
    # ================================================================
    @staticmethod
    def _color_by_rate(rate):
        if rate <= 0:
            return "#C83232"
        if rate >= 1:
            return "#32C832"
        hue = 0.0 + rate * 0.35
        r, g, b = hsv_to_rgb(hue, 0.9, 0.85)
        return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"

    # ================================================================
    # 数据获取
    # ================================================================
    def _get_bar_chart_data(self):
        # 用 _view 判断，避免 _view=='grade' 但 selected_grade!='全部' 时返回单元字典
        if self._view == 'grade':
            items = self._load_grades()
            return items, 'grade'
        vols = self._load_units(self.selected_grade)
        return vols, 'unit_volume'

    def _get_words_for_selection(self):
        """返回当前选中单元的四类单词 {cat: [(word, meaning, score)]}"""
        if self.selected_grade == '全部' or self.selected_unit is None:
            return {k: [] for k, _, _ in CATEGORIES}
        uname, vol = self.selected_unit
        return self._load_words(self.selected_grade, uname, vol)

    # ================================================================
    # 通用：单根水平条形
    # ================================================================
    def _bar_row(self, label, total, mastered, on_click=None,
                 label_w=56, max_bar_w=170, bar_h=36, selected=False,
                 show_arrow=True):
        rate = mastered / total if total > 0 else 0
        color = self._color_by_rate(rate)
        fill_w = max(2, int(max_bar_w * rate))

        bar = ft.Stack([
            ft.Container(width=max_bar_w, height=bar_h,
                         bgcolor=_C.TRACK, border_radius=8),
            ft.Container(width=fill_w, height=bar_h,
                         bgcolor=color, border_radius=8),
            ft.Container(width=max_bar_w, height=bar_h,
                         content=ft.Text(f"{mastered}/{total}", size=11,
                                         color="white" if rate > 0.35 else _C.TEXT,
                                         weight=ft.FontWeight.BOLD),
                         alignment=ft.alignment.center),
        ])

        trailing = ft.Row([
            ft.Text(f"{rate * 100:.1f}%", size=12, color=color,
                    weight=ft.FontWeight.BOLD),
            ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=_C.TEXT_SEC)
            if show_arrow else ft.Container(),
        ], spacing=2)

        return ft.Container(
            content=ft.Row([
                ft.Container(width=label_w,
                             content=ft.Text(label, size=12, color=_C.TEXT,
                                             weight=ft.FontWeight.W_600,
                                             overflow=ft.TextOverflow.ELLIPSIS)),
                bar,
                ft.Container(width=44, content=trailing,
                             alignment=ft.alignment.center_right),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(vertical=5, horizontal=4),
            border_radius=8,
            bgcolor=_C.CARD if selected else ft.Colors.TRANSPARENT,
            border=ft.border.all(2, _C.ACCENT) if selected else None,
            on_click=on_click,
            shadow=ft.BoxShadow(blur_radius=6, color="#15000000") if selected else None,
            tooltip=f"{label}\n掌握: {mastered}/{total}  ({rate * 100:.1f}%)",
        )

    # ================================================================
    # 统计小卡片
    # ================================================================
    @staticmethod
    def _stat_card(label, value, color):
        return ft.Container(
            content=ft.Column([
                ft.Text(value, size=16, weight=ft.FontWeight.BOLD, color=color),
                ft.Text(label, size=10, color=_C.TEXT_SEC),
            ], alignment=ft.MainAxisAlignment.CENTER,
               horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
            width=96, padding=ft.padding.symmetric(vertical=10),
            bgcolor=_C.CARD, border_radius=14,
            shadow=ft.BoxShadow(blur_radius=10, color="#12000000"),
        )

    # ================================================================
    # 空状态
    # ================================================================
    def _empty(self, text):
        return ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.INBOX, size=48, color="#C4CFDD"),
                ft.Text(text, size=14, color=_C.TEXT_SEC),
            ], alignment=ft.MainAxisAlignment.CENTER,
               horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
            expand=True, alignment=ft.alignment.center,
        )

    # ================================================================
    # 视图一：年级总览
    # ================================================================
    def _build_grade_view(self):
        items, _ = self._get_bar_chart_data()
        if not items:
            return self._empty("暂无年级数据")

        rows = []
        for item in items:
            name = item['name']
            total = item['total']
            mastered = item['mastered']

            def _click(e, n=name):
                self.selected_grade = n
                self.selected_unit = None
                self._view = 'unit'
                self._refresh()

            rows.append(self._bar_row(name, total, mastered, on_click=_click))

        total_all = sum(i['total'] for i in items)
        mastered_all = sum(i['mastered'] for i in items)
        rate_all = mastered_all / total_all if total_all else 0
        summary = ft.Row([
            self._stat_card("年级数", str(len(items)), _C.PRIMARY),
            self._stat_card("总单词", f"{total_all}", _C.ACCENT),
            self._stat_card("掌握率", f"{rate_all * 100:.1f}%",
                            self._color_by_rate(rate_all)),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=10)

        hint = ft.Text("点击年级查看单元详情 →", size=11,
                       color=_C.TEXT_SEC, text_align=ft.TextAlign.CENTER)

        return ft.ListView(
            controls=[summary, ft.Container(height=6), hint,
                      ft.Container(height=6)] + rows,
            padding=ft.padding.all(14), spacing=2, expand=True,
        )

    # ================================================================
    # 视图二：单元列表（上册/下册分组）
    # ================================================================
    def _build_unit_view(self):
        vols, _ = self._get_bar_chart_data()
        if not vols or (not vols.get('上册') and not vols.get('下册')):
            return self._empty("该年级暂无单元数据")

        rows = []
        for vol_name in ['上册', '下册']:
            units = vols.get(vol_name, [])
            if not units:
                continue
            rows.append(ft.Container(
                content=ft.Row([
                    ft.Container(width=4, height=18, bgcolor=_C.ACCENT, border_radius=2),
                    ft.Text(f"{vol_name}", size=13, color=_C.TEXT,
                            weight=ft.FontWeight.BOLD),
                    ft.Text(f"({len(units)} 单元)", size=11, color=_C.TEXT_SEC),
                ], spacing=6),
                padding=ft.padding.only(top=10, bottom=4),
            ))
            for u in units:
                uname = u['unit']
                total = u['total']
                mastered = u['mastered']
                key = (uname, vol_name)

                def _click(e, k=key):
                    self.selected_unit = k
                    self._selected_cat = 'mastered'
                    self._view = 'word'
                    self.page.run_task(self.reload)

                rows.append(self._bar_row(uname, total, mastered, on_click=_click))

        hint = ft.Text("点击单元查看四类单词详情 →", size=11,
                       color=_C.TEXT_SEC, text_align=ft.TextAlign.CENTER,
                       italic=True)
        rows.insert(0, ft.Container(height=4))
        rows.append(ft.Container(height=8))
        rows.append(hint)

        return ft.ListView(controls=rows, padding=ft.padding.all(14),
                           spacing=0, expand=True)

    # ================================================================
    # 视图三：四类单词列表
    # ================================================================
    def _build_word_view(self):
        if self.selected_unit is None:
            return self._empty("未选中单元")

        uname, vol = self.selected_unit
        all_words = self._get_words_for_selection()

        # ---- 四类 Tab（带数量徽章） ----
        tab_buttons = []
        for cat_key, cat_label, cat_color in CATEGORIES:
            count = len(all_words.get(cat_key, []))
            active = (self._selected_cat == cat_key)
            btn = ft.Container(
                content=ft.Column([
                    ft.Text(cat_label, size=12,
                            color=cat_color if active else _C.TEXT_SEC,
                            weight=ft.FontWeight.BOLD if active else ft.FontWeight.NORMAL),
                    ft.Container(
                        content=ft.Text(str(count), size=10, color="white",
                                        weight=ft.FontWeight.BOLD),
                        width=22, height=18, border_radius=9,
                        bgcolor=cat_color,
                        alignment=ft.alignment.center,
                    ) if count > 0 else ft.Container(width=22, height=18),
                ], alignment=ft.MainAxisAlignment.CENTER,
                   horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
                padding=ft.padding.symmetric(horizontal=8, vertical=6),
                border_radius=10,
                bgcolor=_C.CARD if active else ft.Colors.TRANSPARENT,
                border=ft.border.all(1.5, cat_color) if active else ft.border.all(1, _C.TRACK),
                on_click=lambda e, k=cat_key: self._switch_category(k),
                expand=True,
            )
            tab_buttons.append(btn)

        tab_row = ft.Container(
            content=ft.Row(controls=tab_buttons, spacing=6),
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
            bgcolor=_C.BG,
        )

        # ---- 当前分类单词列表 ----
        cat_key = self._selected_cat
        cat_label = next((l for k, l, _ in CATEGORIES if k == cat_key), "")
        cat_color = next((c for k, _, c in CATEGORIES if k == cat_key), _C.PRIMARY)
        words = all_words.get(cat_key, [])

        if not words:
            body = self._empty(f"暂无{cat_label}单词")
        else:
            word_rows = []
            for idx, (word, meaning, score) in enumerate(words):
                word_rows.append(ft.Container(
                    content=ft.Row([
                        ft.Container(width=24,
                                     content=ft.Text(f"{idx+1}", size=11,
                                                     color=_C.TEXT_SEC,
                                                     text_align=ft.TextAlign.CENTER)),
                        ft.Column([
                            ft.Text(word, size=14, color=_C.TEXT,
                                    weight=ft.FontWeight.W_600),
                            ft.Text(meaning, size=11, color=_C.TEXT_SEC),
                        ], tight=True, spacing=1, expand=True),
                        ft.Column([
                            ft.Container(
                                content=ft.ProgressBar(value=score, color=cat_color,
                                                       bgcolor=_C.TRACK),
                                width=90, border_radius=3),
                            ft.Text(f"{score * 100:.1f}%", size=10,
                                    color=cat_color,
                                    text_align=ft.TextAlign.RIGHT,
                                    width=90),
                        ], tight=True, spacing=2,
                            horizontal_alignment=ft.CrossAxisAlignment.END),
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                    padding=ft.padding.symmetric(vertical=8, horizontal=10),
                    border_radius=8,
                    bgcolor=_C.CARD,
                    margin=ft.margin.only(bottom=4),
                    shadow=ft.BoxShadow(blur_radius=4, color="#0A000000"),
                ))
            body = ft.ListView(controls=word_rows, padding=ft.padding.all(10),
                               spacing=0, expand=True)

        # 单元信息头
        header = ft.Container(
            content=ft.Row([
                ft.Container(width=4, height=36, border_radius=2,
                             gradient=ft.LinearGradient(
                                 begin=ft.alignment.top_center,
                                 end=ft.alignment.bottom_center,
                                 colors=[_C.PRIMARY, _C.ACCENT])),
                ft.Column([
                    ft.Text(f"{self.selected_grade} · {vol} · {uname}", size=14,
                            color=_C.PRIMARY, weight=ft.FontWeight.BOLD),
                    ft.Text(f"共 {sum(len(v) for v in all_words.values())} 个单词",
                            size=12, color=_C.ACCENT, weight=ft.FontWeight.W_600),
                ], spacing=2, expand=True),
            ], spacing=10),
            padding=ft.padding.symmetric(horizontal=14, vertical=8),
            bgcolor=_C.CARD,
        )

        return ft.Column([
            header, tab_row, body,
        ], spacing=0, expand=True)

    def _switch_category(self, cat_key):
        self._selected_cat = cat_key
        self._refresh()

    # ================================================================
    # 图表内容分发
    # ================================================================
    def _build_chart(self):
        if self._view == 'word':
            return self._build_word_view()
        if self._view == 'unit':
            return self._build_unit_view()
        return self._build_grade_view()

    def _refresh(self):
        if self._chart_container is not None:
            self._chart_container.content = self._build_chart()
            self._chart_container.update()
        if self._title_ref:
            self._title_ref.value = self._title_text()
            self._title_ref.update()
        if self._back_btn:
            self._back_btn.visible = (self._view != 'grade')
            self._back_btn.update()
        if getattr(self, '_legend_ref', None):
            self._legend_ref.visible = (self._view != 'word')
            self._legend_ref.update()

    def _title_text(self):
        if self._view == 'word':
            uname, vol = self.selected_unit if self.selected_unit else ("", "")
            return f"{uname} · 单词详情"
        if self._view == 'unit':
            return f"{self.selected_grade} · 单元掌握率"
        return "各年级单词掌握率"

    # ================================================================
    # 返回上一级
    # ================================================================
    def _back(self, e):
        if self._view == 'word':
            self._view = 'unit'
            self.selected_unit = None
        elif self._view == 'unit':
            self._view = 'grade'
            self.selected_grade = '全部'
            self.selected_unit = None
        self._refresh()

    # ================================================================
    # 页面入口
    # ================================================================
    def build(self):
        self._back_btn = ft.IconButton(
            icon=ft.Icons.ARROW_BACK, icon_color=_C.PRIMARY,
            visible=False, on_click=self._back, tooltip="返回",
        )
        self._title_ref = ft.Text(self._title_text(), size=16,
                                  color=_C.TEXT, weight=ft.FontWeight.BOLD,
                                  expand=True)

        # 用户下拉已移至英语页顶层共享
        header = ft.Row([
            self._back_btn,
            self._title_ref,
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4)

        # 渐变色图例（仅年级/单元视图显示）
        def _legend():
            self._legend_ref = ft.Container(
                content=ft.Column([
                    ft.Container(expand=True, height=8, border_radius=4,
                                 gradient=ft.LinearGradient(
                                     begin=ft.alignment.center_left,
                                     end=ft.alignment.center_right,
                                     colors=["#C83232", "#F0C040", "#32C832"])),
                    ft.Row([
                        ft.Text("0%", size=9, color=_C.TEXT_SEC),
                        ft.Container(expand=True),
                        ft.Text("50%", size=9, color=_C.TEXT_SEC),
                        ft.Container(expand=True),
                        ft.Text("100%", size=9, color=_C.TEXT_SEC),
                    ], spacing=0),
                ], spacing=2),
                padding=ft.padding.symmetric(horizontal=14, vertical=6),
                visible=(self._view != 'word'),
            )
            return self._legend_ref

        self._chart_container = ft.Container(
            content=self._build_chart(),
            expand=True, bgcolor=_C.CARD, border_radius=18,
            shadow=ft.BoxShadow(blur_radius=14, color="#18000000"),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            margin=ft.margin.symmetric(horizontal=12),
        )

        return ft.Container(
            content=ft.Column([
                header, _legend(), self._chart_container,
            ], spacing=8, expand=True),
            padding=ft.padding.only(top=12, bottom=12),
            bgcolor=_C.BG, expand=True,
        )