# pages/admin/guoxue.py
import flet as ft
import asyncio
import datetime
from pages.admin.base import AdminBaseTab

LEVEL_OPTIONS = ["小学", "初中", "高中"]
DIFFICULTY_NAMES = {1: "简单", 2: "普通", 3: "困难"}
CATEGORY_OPTIONS = ["中国地理", "传统文化", "历史典故", "名著与常识",
                    "诗词曲赋", "经典蒙学", "文言文基础", "文学常识"]


class GuoxueManagementTab(AdminBaseTab):
    """国学管理：题目管理 + 测试配置管理"""

    def __init__(self, page):
        super().__init__(page)
        self._content = None
        self._q_list_view = None
        self._cat_filter = None

    def build(self):
        self._content = ft.Column(spacing=8, expand=True, scroll=ft.ScrollMode.ADAPTIVE)
        return self._content

    async def load_data(self):
        await self._load()

    async def _load(self):
        await asyncio.sleep(0.05)

        def _query_all():
            statements = [
                ("SELECT COUNT(*) as cnt FROM questions", []),
                ("SELECT category, COUNT(*) as cnt FROM questions GROUP BY category ORDER BY cnt DESC", []),
            ]
            try:
                results = self.db.fetch_many(statements)
            except Exception as e:
                print(f"[guoxue] batch query fail: {e}")
                return None, []
            def _safe(idx):
                r = results[idx] if idx < len(results) else []
                return r if r is not None else []
            total_rows = _safe(0)
            total = total_rows[0] if total_rows else None
            return total, _safe(1)

        total, cats = await asyncio.to_thread(_query_all)
        self._cat_opts = sorted([c['category'] for c in (cats or []) if c.get('category')])

        # 题目统计卡片
        q_tiles = [self._card(ft.Row([
            ft.Icon(ft.Icons.QUESTION_ANSWER, color=ft.Colors.AMBER_700, size=24),
            ft.Column([
                ft.Text(str(total['cnt'] if total else 0), size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER_800),
                ft.Text("总题目数", size=11, color=ft.Colors.GREY_600),
            ], spacing=2),
        ], spacing=10))]
        for c in (cats or []):
            q_tiles.append(self._list_tile(
                ft.Icon(ft.Icons.BOOK, size=18, color=ft.Colors.AMBER_700),
                ft.Text(c.get('category', '未分类'), size=12),
                trailing=ft.Text(f"{c['cnt']} 题", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.AMBER_800),
            ))
        self._q_list_view = ft.ListView(controls=q_tiles, spacing=2, expand=True)

        # 题目列表（最近20条，可按分类筛选）
        self._question_tiles = []
        self._q_list_full = ft.ListView(spacing=2, expand=True)
        await self._reload_questions()

        self._content.controls = [
            # 题目统计
            ft.Text("题目统计", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.AMBER_800),
            self._q_list_view,
            ft.Container(height=8),
            # 题目管理
            ft.Row([
                ft.Text("题目管理", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.AMBER_800, expand=True),
                self._action_button("添加题目", ft.Icons.ADD, self._add_question, ft.Colors.AMBER_700),
            ]),
            self._build_cat_filter(),
            self._q_list_full,
        ]
        self.page.update()

    def _build_cat_filter(self):
        """分类筛选下拉"""
        opts = [ft.dropdown.Option(key="__all__", text="全部分类")]
        for c in self._cat_opts:
            opts.append(ft.dropdown.Option(key=c, text=c))
        self._cat_filter = ft.Dropdown(
            options=opts, value="__all__",
            on_change=lambda e: self.page.run_task(self._reload_questions),
            border_radius=8, text_size=11,
            content_padding=ft.padding.symmetric(horizontal=8, vertical=0),
        )
        return self._cat_filter

    async def _reload_questions(self):
        """加载题目列表（按分类筛选，最多50条）"""
        cat = self._cat_filter.value if self._cat_filter else "__all__"
        def _query():
            if cat == "__all__":
                return self._safe_q("SELECT * FROM questions ORDER BY id DESC LIMIT 50")
            return self._safe_q("SELECT * FROM questions WHERE category=? ORDER BY id DESC LIMIT 50", [cat])

        rows = await asyncio.to_thread(_query)
        tiles = []
        for r in rows or []:
            qid = r.get('id')
            qtext = (r.get('question') or '')[:40]
            cat_name = r.get('category', '未分类')
            level = r.get('level', '小学')
            diff = DIFFICULTY_NAMES.get(r.get('difficulty', 1), '普通')
            tiles.append(self._list_tile(
                ft.Icon(ft.Icons.QUIZ, size=18, color=ft.Colors.AMBER_700),
                ft.Text(f"[{qid}] {qtext}", size=11, weight=ft.FontWeight.W_600),
                ft.Text(f"{cat_name} · {level} · {diff}", size=9, color=ft.Colors.GREY_500),
                trailing=ft.Row([
                    ft.IconButton(ft.Icons.EDIT, icon_size=16, icon_color=ft.Colors.BLUE_500,
                                  on_click=lambda e, q=r: self._edit_question(q)),
                    ft.IconButton(ft.Icons.DELETE, icon_size=16, icon_color=ft.Colors.RED_400,
                                  on_click=lambda e, q=r: self._delete_question(q)),
                ], spacing=0),
                on_click=lambda e, q=r: self._edit_question(q),
            ))
        if not tiles:
            tiles.append(self._empty("暂无题目"))
        self._q_list_full.controls = tiles
        try:
            self.page.update()
        except Exception:
            pass

    def _safe_q(self, sql, params=None):
        try:
            return self.db.fetch_all(sql, params) or []
        except Exception as e:
            print(f"[guoxue] question query fail: {e}")
            return []

    # ---------- 题目 CRUD ----------
    def _add_question(self, e=None):
        self._open_question_form(None)

    def _edit_question(self, q):
        self._open_question_form(q)

    def _open_question_form(self, q):
        is_edit = q is not None
        cat_opts = self._cat_opts if hasattr(self, '_cat_opts') and self._cat_opts else CATEGORY_OPTIONS

        q_tf = ft.TextField(label="题目内容", value=q.get('question') if is_edit else "",
                            multiline=True, min_lines=2, max_lines=4, border_radius=8, expand=True)
        a_tf = ft.TextField(label="选项A", value=q.get('option_a') if is_edit else "", border_radius=8, expand=True)
        b_tf = ft.TextField(label="选项B", value=q.get('option_b') if is_edit else "", border_radius=8, expand=True)
        c_tf = ft.TextField(label="选项C", value=q.get('option_c') if is_edit else "", border_radius=8, expand=True)
        d_tf = ft.TextField(label="选项D", value=q.get('option_d') if is_edit else "", border_radius=8, expand=True)
        ans_dd = ft.Dropdown(label="正确答案",
                             value=str(q.get('answer', 1) if is_edit else 1),
                             options=[ft.dropdown.Option(key=str(i), text=f"选项{chr(64+i)}") for i in range(1, 5)],
                             border_radius=8, expand=True)
        exp_tf = ft.TextField(label="解析", value=q.get('explanation') if is_edit else "",
                              multiline=True, min_lines=1, max_lines=2, border_radius=8, expand=True)
        cat_dd = ft.Dropdown(label="分类",
                             value=q.get('category') if is_edit and q.get('category') else (cat_opts[0] if cat_opts else ""),
                             options=[ft.dropdown.Option(key=c, text=c) for c in cat_opts],
                             border_radius=8, expand=True)
        kp_tf = ft.TextField(label="知识点", value=q.get('knowledge_point') if is_edit else "", border_radius=8, expand=True)
        diff_dd = ft.Dropdown(label="难度",
                              value=str(q.get('difficulty', 1) if is_edit else 1),
                              options=[ft.dropdown.Option(key=str(k), text=v) for k, v in DIFFICULTY_NAMES.items()],
                              border_radius=8, expand=True)
        level_dd = ft.Dropdown(label="等级",
                               value=q.get('level', '小学') if is_edit else '小学',
                               options=[ft.dropdown.Option(key=l, text=l) for l in LEVEL_OPTIONS],
                               border_radius=8, expand=True)

        controls = [q_tf, a_tf, b_tf, c_tf, d_tf, ans_dd, exp_tf, cat_dd, kp_tf, diff_dd, level_dd]

        def do_submit(e):
            question = q_tf.value.strip()
            if not question:
                self.snack("题目内容不能为空")
                return
            if not all([a_tf.value.strip(), b_tf.value.strip(), c_tf.value.strip(), d_tf.value.strip()]):
                self.snack("四个选项都不能为空")
                return
            # 重复检测
            existing = self._safe_q("SELECT id FROM questions WHERE question=? LIMIT 1", [question])
            if existing and (not is_edit or existing[0]['id'] != q['id']):
                self.snack(f"题目已存在 (ID:{existing[0]['id']})，请勿重复添加")
                return
            params = {
                'question': question,
                'option_a': a_tf.value.strip(),
                'option_b': b_tf.value.strip(),
                'option_c': c_tf.value.strip(),
                'option_d': d_tf.value.strip(),
                'answer': int(ans_dd.value or 1),
                'explanation': exp_tf.value or "",
                'category': cat_dd.value or "",
                'knowledge_point': kp_tf.value or "",
                'difficulty': int(diff_dd.value or 1),
                'level': level_dd.value or '小学',
            }
            self._close_dialog(dlg)

            def do_save():
                if is_edit:
                    sets = ", ".join(f"{k}=?" for k in params)
                    self.db.execute(f"UPDATE questions SET {sets} WHERE id=?", list(params.values()) + [q['id']])
                    before = {k: q.get(k) for k in params}
                    self._log_operation("edit_question", "questions", target_id=q['id'],
                                        details=f"分类:{params['category']}",
                                        before_state=before, after_state=params)
                else:
                    params['created_at'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cols = ", ".join(params.keys())
                    ph = ", ".join("?" for _ in params)
                    self.db.execute(f"INSERT INTO questions ({cols}) VALUES ({ph})", list(params.values()))
                    self._log_operation("add_question", "questions",
                                        details=f"分类:{params['category']},难度:{params['difficulty']}",
                                        after_state=params)

            self.run_save_async(do_save, after_fn=lambda: self.page.run_task(self._load))

        dlg = ft.AlertDialog(
            title=ft.Text("编辑题目" if is_edit else "添加题目", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=ft.Column(controls, spacing=6, scroll=ft.ScrollMode.ADAPTIVE),
                                 width=420, height=600, padding=4),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.ElevatedButton("保存", on_click=do_submit,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.AMBER_700, color=ft.Colors.WHITE)),
            ],
        )
        self.page.open(dlg)

    def _delete_question(self, q):
        self.confirm_and_run("删除题目", f"确定删除题目 [{q.get('id')}] 吗？",
                             self._do_delete_question, q['id'],
                             success_msg="已删除", loading_msg="删除中...")

    async def _do_delete_question(self, qid):
        self.db.execute("DELETE FROM questions WHERE id=?", [qid])
        self._log_operation("delete_question", "questions", target_id=qid)
        await self._load()
