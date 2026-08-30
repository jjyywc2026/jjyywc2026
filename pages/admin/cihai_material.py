# pages/admin/cihai_material.py
import flet as ft
import asyncio
import datetime
from pages.admin.base import AdminBaseTab

# type 英文 → 中文映射
TYPE_MAP = {"word": "好词", "sentence": "好句", "opening": "好开头", "ending": "好结尾"}
TYPE_REVERSE = {v: k for k, v in TYPE_MAP.items()}
TYPE_ORDER = ["word", "sentence", "opening", "ending"]

# difficulty_id 数字 → 中文映射
DIFF_MAP = {1: "简单", 2: "中等", 3: "困难"}
DIFF_REVERSE = {v: k for k, v in DIFF_MAP.items()}
DIFFICULTY_OPTIONS = ["简单", "中等", "困难"]
DIFF_COLORS = {"简单": "#22C55E", "中等": "#F59E0B", "困难": "#EF4444"}

# 类型主题色
TYPE_THEME = {
    "word":     {"primary": "#16A34A", "bg": "#F0FDF4", "border": "#BBF7D0", "light": "#DCFCE7", "text": "#166534", "icon": ft.Icons.AUTO_FIX_HIGH},
    "sentence": {"primary": "#2563EB", "bg": "#EFF6FF", "border": "#BFDBFE", "light": "#DBEAFE", "text": "#1E40AF", "icon": ft.Icons.FORMAT_QUOTE},
    "opening":  {"primary": "#D97706", "bg": "#FFFBEB", "border": "#FDE68A", "light": "#FEF3C7", "text": "#92400E", "icon": ft.Icons.FLAG},
    "ending":   {"primary": "#DB2777", "bg": "#FDF2F8", "border": "#F9A8D4", "light": "#FCE7F3", "text": "#9D174D", "icon": ft.Icons.FLAG_CIRCLE},
}


class CihaiMaterialTab(AdminBaseTab):
    """辞海题库管理（按类型分组+可折叠+搜索+交互拉满）"""

    def __init__(self, page):
        super().__init__(page)
        self._list_view = None
        self._search_tf = None
        self._collapsed = set()  # 折叠的类型
        self._filter_type = "all"  # all | word | sentence | opening | ending
        self._filter_diff = "all"  # all | 1 | 2 | 3
        self._sort_mode = "type"   # type | date_desc | date_asc
        self._all_materials = []

    def build(self):
        self._search_tf = ft.TextField(
            hint_text="搜索题目内容...",
            prefix_icon=ft.Icons.SEARCH,
            border_radius=20,
            expand=True,
            text_size=13,
            content_padding=ft.padding.symmetric(horizontal=14, vertical=8),
            bgcolor="#F9FAFB",
            on_change=self._on_search,
        )
        self._list_view = ft.ListView(spacing=2, expand=True)

        # 类型筛选胶囊
        type_chips = [self._filter_chip("全部", "all", self._filter_type, self._on_type_filter, "#6B7280")]
        for t in TYPE_ORDER:
            th = TYPE_THEME[t]
            type_chips.append(self._filter_chip(TYPE_MAP[t], t, self._filter_type, self._on_type_filter, th["primary"]))

        # 难度筛选
        diff_chips = [self._filter_chip("全部难度", "all", self._filter_diff, self._on_diff_filter, "#6B7280")]
        for d_id, d_name in DIFF_MAP.items():
            diff_chips.append(self._filter_chip(d_name, str(d_id), self._filter_diff, self._on_diff_filter, DIFF_COLORS[d_name]))

        # 排序切换
        sort_chips = [
            self._filter_chip("按类型", "type", self._sort_mode, self._on_sort, "#6B7280"),
            self._filter_chip("最新优先", "date_desc", self._sort_mode, self._on_sort, "#0D9488"),
            self._filter_chip("最早优先", "date_asc", self._sort_mode, self._on_sort, "#0D9488"),
        ]

        return ft.Column([
            # 搜索栏
            ft.Container(
                content=ft.Row([
                    self._search_tf,
                    ft.Container(
                        content=ft.Icon(ft.Icons.ADD, size=18, color=ft.Colors.WHITE),
                        bgcolor="#4F46E5", border_radius=20, width=36, height=36,
                        on_click=self._add_material, ink=True,
                        tooltip="添加题目",
                    ),
                ], spacing=8),
                padding=ft.padding.only(bottom=6),
            ),
            # 筛选栏
            ft.Container(
                content=ft.Column([
                    ft.Row(type_chips, spacing=4, wrap=True, scroll=ft.ScrollMode.ADAPTIVE),
                    ft.Row(diff_chips, spacing=4, wrap=True, scroll=ft.ScrollMode.ADAPTIVE),
                    ft.Row([
                        ft.Icon(ft.Icons.SORT, size=13, color="#9CA3AF"),
                        ft.Text("排序:", size=10, color="#9CA3AF"),
                        *sort_chips,
                    ], spacing=4, wrap=True, scroll=ft.ScrollMode.ADAPTIVE),
                ], spacing=4),
                padding=ft.padding.only(bottom=4),
            ),
            self._list_view,
        ], spacing=0, expand=True)

    def _filter_chip(self, label, value, current, on_click, color):
        active = (str(current) == str(value))
        return ft.Container(
            content=ft.Text(label, size=10, color="white" if active else color,
                            weight=ft.FontWeight.W_600 if active else ft.FontWeight.NORMAL),
            padding=ft.padding.symmetric(horizontal=10, vertical=4),
            border_radius=12,
            bgcolor=color if active else "#F3F4F6",
            border=ft.border.all(0.5, color) if not active else None,
            on_click=lambda e, v=value: on_click(v),
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
            ink=True,
        )

    def _on_type_filter(self, value):
        self._filter_type = value
        self.page.run_task(self._render_list)

    def _on_diff_filter(self, value):
        self._filter_diff = value
        self.page.run_task(self._render_list)

    def _on_sort(self, value):
        self._sort_mode = value
        self.page.run_task(self._render_list)

    def _on_search(self, e):
        self.page.run_task(self._render_list)

    async def load_data(self):
        await self._reload()

    async def _reload(self):
        await asyncio.sleep(0.05)

        def _query():
            try:
                rows = self.db.fetch_all("SELECT * FROM materials ORDER BY type, id DESC")
                return rows, None
            except Exception as e:
                return [], str(e)

        materials, err = await asyncio.to_thread(_query)
        if err:
            self.snack(f"加载失败: {err}")
            return
        self._all_materials = materials or []
        await self._render_list()

    async def _render_list(self):
        keyword = (self._search_tf.value or "").strip().lower() if self._search_tf else ""
        filtered = []
        for m in self._all_materials:
            t_en = m.get('type', 'sentence')
            diff_id = str(m.get('difficulty_id', 1) or 1)
            content = (m.get('content', '') or '')
            if self._filter_type != "all" and t_en != self._filter_type:
                continue
            if self._filter_diff != "all" and diff_id != self._filter_diff:
                continue
            if keyword and keyword not in content.lower():
                continue
            filtered.append(m)

        tiles = []
        total_count = len(filtered)
        # 统计栏
        sort_label = {"type": "按类型", "date_desc": "最新优先", "date_asc": "最早优先"}.get(self._sort_mode, "")
        tiles.append(ft.Container(
            content=ft.Row([
                ft.Text(f"共 {total_count} 题", size=11, color="#6B7280", weight=ft.FontWeight.W_600),
                ft.Container(expand=True),
                ft.Text(f"排序: {sort_label}", size=10, color="#9CA3AF"),
            ]),
            padding=ft.padding.symmetric(horizontal=4, vertical=4),
        ))

        # 日期排序：扁平列表，不分组
        if self._sort_mode in ("date_desc", "date_asc"):
            reverse = (self._sort_mode == "date_desc")
            sorted_items = sorted(filtered, key=lambda x: str(x.get('created_at', '')), reverse=reverse)
            for m in sorted_items:
                t_en = m.get('type', 'sentence')
                th = TYPE_THEME.get(t_en, TYPE_THEME["sentence"])
                tiles.append(self._material_card(m, th))
            if total_count == 0:
                tiles.append(self._empty("暂无匹配的题目，点击右上角添加"))
            self._list_view.controls = tiles
            try:
                self.page.update()
            except Exception:
                pass
            return

        # 按类型分组
        groups = {}
        for t in TYPE_ORDER:
            groups[t] = []
        for m in filtered:
            t_en = m.get('type', 'sentence')
            if t_en in groups:
                groups[t_en].append(m)
            else:
                groups.setdefault(t_en, []).append(m)

        for t_en in TYPE_ORDER:
            items = groups.get(t_en, [])
            if not items:
                continue
            th = TYPE_THEME[t_en]
            is_collapsed = t_en in self._collapsed

            group_col = ft.Column(spacing=3, tight=True, visible=not is_collapsed)
            for m in items:
                group_col.controls.append(self._material_card(m, th))

            def _toggle(e, te=t_en, gc=group_col):
                if te in self._collapsed:
                    self._collapsed.discard(te)
                    gc.visible = True
                    e.control.icon = ft.Icons.EXPAND_LESS
                else:
                    self._collapsed.add(te)
                    gc.visible = False
                    e.control.icon = ft.Icons.EXPAND_MORE
                self.page.update()

            header = ft.Container(
                content=ft.Row([
                    ft.Container(width=4, height=20, border_radius=2, bgcolor=th["primary"]),
                    ft.Icon(th["icon"], size=16, color=th["primary"]),
                    ft.Text(f"{TYPE_MAP[t_en]}", size=13, weight=ft.FontWeight.BOLD, color=th["text"]),
                    ft.Container(
                        content=ft.Text(f"{len(items)}", size=10, color="white", weight=ft.FontWeight.BOLD),
                        bgcolor=th["primary"], border_radius=8,
                        padding=ft.padding.symmetric(horizontal=6, vertical=1),
                    ),
                    ft.Container(expand=True),
                    ft.IconButton(
                        ft.Icons.EXPAND_LESS if not is_collapsed else ft.Icons.EXPAND_MORE,
                        icon_size=18, icon_color=th["primary"],
                        on_click=lambda e, te=t_en, gc=group_col: _toggle(e, te, gc),
                    ),
                ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=th["bg"],
                border_radius=8,
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                margin=ft.margin.only(top=6, bottom=2),
                border=ft.border.all(0.5, th["border"]),
                on_click=lambda e, te=t_en, gc=group_col: _toggle(e, te, gc),
                ink=True,
            )
            tiles.append(header)
            tiles.append(group_col)

        if total_count == 0:
            tiles.append(self._empty("暂无匹配的题目，点击右上角添加"))

        self._list_view.controls = tiles
        try:
            self.page.update()
        except Exception:
            pass

    def _material_card(self, m, th):
        content = m.get('content', '') or ''
        diff_id = int(m.get('difficulty_id', 1) or 1)
        diff_cn = DIFF_MAP.get(diff_id, str(diff_id))
        diff_color = DIFF_COLORS.get(diff_cn, "#9CA3AF")
        char_len = len(content)
        preview = content if len(content) <= 80 else content[:77] + "..."
        created = str(m.get('created_at', ''))[:10]

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    # 难度圆点
                    ft.Container(width=8, height=8, bgcolor=diff_color, border_radius=4),
                    ft.Text(diff_cn, size=9, color=diff_color, weight=ft.FontWeight.W_600),
                    ft.Container(width=6),
                    ft.Text(f"{char_len}字", size=9, color="#9CA3AF"),
                    ft.Container(expand=True),
                    ft.Text(created, size=9, color="#D1D5DB"),
                    ft.IconButton(ft.Icons.EDIT_SQUARE, icon_size=15, icon_color="#3B82F6",
                                  on_click=lambda e, mat=m: self._edit_material(mat)),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=15, icon_color="#EF4444",
                                  on_click=lambda e, mat=m: self._delete_material(mat)),
                ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Text(preview, size=12, color="#374151", no_wrap=False, max_lines=3,
                        height=48, selectable=True),
            ], spacing=3, tight=True),
            bgcolor="#FFFFFF",
            border_radius=8,
            padding=ft.padding.symmetric(horizontal=10, vertical=7),
            margin=ft.margin.only(bottom=3),
            border=ft.border.all(0.5, th["border"]),
            shadow=ft.BoxShadow(blur_radius=2, color="#0A000000", offset=ft.Offset(0, 1)),
            on_click=lambda e, mat=m: self._edit_material(mat),
            ink=True,
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        )

    # ---------- 题库 CRUD ----------
    def _add_material(self, e=None):
        self._open_material_form(None)

    def _edit_material(self, mat):
        self._open_material_form(mat)

    def _open_material_form(self, mat):
        is_edit = mat is not None
        t_en = mat.get('type', 'sentence') if is_edit else 'sentence'
        t_cn = TYPE_MAP.get(t_en, '好句')
        diff_id = int(mat.get('difficulty_id', 1) or 1) if is_edit else 1
        diff_cn = DIFF_MAP.get(diff_id, '中等')

        content_tf = ft.TextField(
            label="题目内容", value=mat.get('content', '') if is_edit else '',
            multiline=True, min_lines=4, max_lines=10, border_radius=12, expand=True, text_size=15,
            content_padding=ft.padding.all(14),
            hint_text="请输入好词、好句、好开头或好结尾...",
            hint_style=ft.TextStyle(color="#9CA3AF", size=13),
            border_color="#E5E7EB",
            focused_border_color="#4F46E5",
        )
        type_dd = ft.Dropdown(
            label="类型", value=t_cn,
            options=[ft.dropdown.Option(t) for t in TYPE_MAP.values()],
            border_radius=10, expand=True, text_size=13,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
        )
        diff_dd = ft.Dropdown(
            label="难度", value=diff_cn,
            options=[ft.dropdown.Option(d) for d in DIFFICULTY_OPTIONS],
            border_radius=10, expand=True, text_size=13,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
        )
        char_count_ref = ft.Text("0字", size=12, color="#6B7280", weight=ft.FontWeight.W_600)
        th = TYPE_THEME.get(t_en, TYPE_THEME["sentence"])
        type_preview = ft.Container(
            content=ft.Row([
                ft.Icon(th["icon"], size=12, color=th["primary"]),
                ft.Text(t_cn, size=11, weight=ft.FontWeight.W_700, color=th["text"]),
            ], spacing=4),
            bgcolor=th["light"], border_radius=8, padding=ft.padding.symmetric(horizontal=10, vertical=5),
            border=ft.border.all(0.5, th["border"]),
        )

        def _on_content_change(e):
            char_count_ref.value = f"{len(content_tf.value or '')}字"
            try: char_count_ref.update()
            except Exception: pass

        def _on_type_change(e):
            cn = type_dd.value or '好句'
            en = TYPE_REVERSE.get(cn, 'sentence')
            c = TYPE_THEME.get(en, TYPE_THEME["sentence"])
            type_preview.content = ft.Row([
                ft.Icon(c["icon"], size=12, color=c["primary"]),
                ft.Text(cn, size=11, weight=ft.FontWeight.W_700, color=c["text"]),
            ], spacing=4)
            type_preview.bgcolor = c["light"]
            type_preview.border = ft.border.all(0.5, c["border"])
            try: type_preview.update()
            except Exception: pass

        content_tf.on_change = _on_content_change
        type_dd.on_change = _on_type_change
        char_count_ref.value = f"{len(content_tf.value or '')}字"

        def on_submit():
            content = (content_tf.value or '').strip()
            if not content:
                self.snack("请输入题目内容"); return
            cn = type_dd.value or '好句'
            en = TYPE_REVERSE.get(cn, 'sentence')
            diff_cn_val = diff_dd.value or '中等'
            diff_id_val = DIFF_REVERSE.get(diff_cn_val, 1)
            now = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
            try:
                if is_edit:
                    before = {k: mat.get(k) for k in ['content', 'type', 'difficulty_id']}
                    self.db.execute(
                        "UPDATE materials SET content=?, type=?, difficulty_id=? WHERE id=?",
                        [content, en, diff_id_val, mat['id']])
                    after = {'content': content, 'type': en, 'difficulty_id': diff_id_val}
                    self._log_operation("edit_cihai_material", "materials", target_id=mat['id'],
                                        target_name=content[:30],
                                        details=f"类型:{cn},难度:{diff_cn_val}",
                                        before_state=before, after_state=after)
                else:
                    self.db.execute(
                        "INSERT INTO materials (content, type, difficulty_id, created_at) VALUES (?,?,?,?)",
                        [content, en, diff_id_val, now])
                    after = {'content': content, 'type': en, 'difficulty_id': diff_id_val}
                    self._log_operation("add_cihai_material", "materials", target_name=content[:30],
                                        details=f"类型:{cn},难度:{diff_cn_val}", after_state=after)
                self.snack("已保存")
                self.page.run_task(self._reload)
            except Exception as ex:
                self.snack(f"保存失败: {ex}")

        body = ft.Column([
            content_tf,
            ft.Row([type_dd, diff_dd], spacing=8),
            ft.Row([
                type_preview, ft.Container(expand=True),
                ft.Icon(ft.Icons.TEXT_FIELDS, size=13, color="#9CA3AF"), char_count_ref,
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=10, tight=True, width=380)

        dlg = self._beauty_dialog("编辑题目" if is_edit else "添加题目",
                                  ft.Icons.LIBRARY_BOOKS, "#4F46E5", body, on_submit, "#4F46E5")
        self.page.open(dlg)

    def _delete_material(self, mat):
        preview = (mat.get('content', '') or '')[:20]
        self.confirm_and_run("删除题目", f"确定删除「{preview}...」吗？",
                             self._do_delete_material, mat['id'],
                             success_msg="已删除", loading_msg="删除中...")

    async def _do_delete_material(self, mat_id):
        self.db.execute("DELETE FROM materials WHERE id=?", [mat_id])
        self._log_operation("delete_cihai_material", "materials", target_id=mat_id)
        await self._reload()

    # ---------- 美化弹窗 ----------
    def _beauty_dialog(self, title, icon, icon_color, body, on_save, save_color):
        dlg = ft.AlertDialog(
            title=ft.Container(
                content=ft.Row([
                    ft.Container(content=ft.Icon(icon, size=18, color=ft.Colors.WHITE),
                                 bgcolor=icon_color, border_radius=8, padding=6),
                    ft.Text(title, size=16, weight=ft.FontWeight.W_700, color="#1F2937"),
                ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.only(bottom=4),
            ),
            content=ft.Container(content=body, padding=ft.padding.only(top=4), width=380),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg),
                              style=ft.ButtonStyle(color="#6B7280")),
                ft.ElevatedButton("保存", on_click=lambda e: (self._close_dialog(dlg), on_save()),
                    style=ft.ButtonStyle(bgcolor=save_color, color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=8),
                        padding=ft.padding.symmetric(horizontal=20, vertical=8), elevation=2)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=14),
            inset_padding=ft.padding.symmetric(horizontal=20),
        )
        return dlg
