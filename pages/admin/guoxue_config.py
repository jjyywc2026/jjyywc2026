# pages/admin/guoxue_config.py
import flet as ft
import asyncio
from pages.admin.base import AdminBaseTab

LEVEL_OPTIONS = ["小学", "初中", "高中"]
CATEGORY_OPTIONS = ["中国地理", "传统文化", "历史典故", "名著与常识",
                    "诗词曲赋", "经典蒙学", "文言文基础", "文学常识"]


class GuoxueConfigTab(AdminBaseTab):
    """国学测试配置管理（独立模块）"""

    def __init__(self, page):
        super().__init__(page)
        self._list_view = None
        self._cat_opts = []

    def build(self):
        self._list_view = ft.ListView(spacing=2, expand=True)
        return ft.Column([
            ft.Row([
                ft.Text("国学测试配置", size=14, weight=ft.FontWeight.W_600,
                        color=ft.Colors.DEEP_ORANGE_800, expand=True),
                self._action_button("添加配置", ft.Icons.ADD, self._add_config,
                                    ft.Colors.DEEP_ORANGE_600),
            ]),
            self._list_view,
        ], spacing=6, expand=True)

    async def load_data(self):
        await self._reload()

    async def _reload(self):
        await asyncio.sleep(0.05)

        def _query():
            try:
                configs = self.db.fetch_all(
                    "SELECT tc.*, u.username FROM test_config tc "
                    "LEFT JOIN users u ON tc.user_id=u.user_id ORDER BY tc.user_id, tc.id")
                cats = self.db.fetch_all(
                    "SELECT DISTINCT category FROM questions WHERE category IS NOT NULL ORDER BY category")
                return configs, cats, None
            except Exception as e:
                return None, [], str(e)

        configs, cats, err = await asyncio.to_thread(_query)
        if err:
            self.snack(f"加载失败: {err}")
            return
        self._cat_opts = [c['category'] for c in (cats or []) if c.get('category')]

        # 按用户分组
        groups = {}
        for cfg in configs or []:
            uid = cfg.get('user_id', 0)
            uname = cfg.get('username') or ('全部用户' if uid == 0 else f'用户{uid}')
            key = (uid, uname)
            if key not in groups:
                groups[key] = []
            groups[key].append(cfg)

        tiles = []
        for (uid, uname), cfgs in groups.items():
            # 分组标题（可点击折叠）
            group_items = ft.Column(spacing=2, tight=True)
            for cfg in cfgs:
                group_items.controls.append(self._list_tile(
                    ft.Icon(ft.Icons.ASSESSMENT, size=16, color=ft.Colors.DEEP_ORANGE_600),
                    ft.Text(f"{cfg.get('category','?')} · {cfg.get('level','?')}", size=12,
                            weight=ft.FontWeight.W_600),
                    ft.Text(f"{cfg.get('question_count',0)}题", size=10, color=ft.Colors.GREY_500),
                    trailing=ft.IconButton(ft.Icons.DELETE, icon_size=14, icon_color=ft.Colors.RED_400,
                                           on_click=lambda e, c=cfg: self._delete_config(c)),
                    on_click=lambda e, c=cfg: self._edit_config(c),
                ))
            group_items.visible = True

            def _toggle(e, gi=group_items):
                gi.visible = not gi.visible
                e.control.icon = ft.Icons.EXPAND_LESS if gi.visible else ft.Icons.EXPAND_MORE
                self.page.update()

            header = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.PERSON, size=16, color=ft.Colors.DEEP_ORANGE_700),
                    ft.Text(f"{uname}", size=13, weight=ft.FontWeight.BOLD,
                            color=ft.Colors.DEEP_ORANGE_800),
                    ft.Container(
                        content=ft.Text(f"{len(cfgs)}项", size=10, color=ft.Colors.WHITE),
                        bgcolor=ft.Colors.DEEP_ORANGE_400, border_radius=8,
                        padding=ft.padding.symmetric(horizontal=6, vertical=1),
                    ),
                    ft.Container(expand=True),
                    ft.IconButton(ft.Icons.EXPAND_LESS, icon_size=18,
                                  icon_color=ft.Colors.DEEP_ORANGE_500,
                                  on_click=lambda e, gi=group_items: _toggle(e, gi)),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=ft.Colors.DEEP_ORANGE_50,
                border_radius=6,
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                margin=ft.margin.only(top=4, bottom=2),
            )
            tiles.append(header)
            tiles.append(group_items)

        if not tiles:
            tiles.append(self._empty("暂无测试配置，点击右上角添加"))
        self._list_view.controls = tiles
        self.page.update()

    def _add_config(self, e=None):
        self._open_config_form(None)

    def _edit_config(self, cfg):
        self._open_config_form(cfg)

    def _open_config_form(self, cfg):
        is_edit = cfg is not None
        cat_opts = self._cat_opts or CATEGORY_OPTIONS

        fields = [
            ("用户ID(0=全部)", "user_id", cfg.get('user_id', 0) if is_edit else 0, "number"),
            ("分类", "category", cfg.get('category', '') if is_edit else "", cat_opts),
            ("等级", "level", cfg.get('level', '小学') if is_edit else "小学", LEVEL_OPTIONS),
            ("题目数量", "question_count", cfg.get('question_count', 5) if is_edit else 5, "number"),
        ]

        def on_submit(data):
            try:
                uid = int(data['user_id'] or 0)
                cat = data['category'].strip()
                level = data['level']
                qcnt = int(data['question_count'] or 5)
                if not cat:
                    self.snack("请输入分类")
                    return
                if is_edit:
                    self.db.execute(
                        "UPDATE test_config SET user_id=?, category=?, level=?, question_count=? WHERE id=?",
                        [uid, cat, level, qcnt, cfg['id']])
                    before = {k: cfg.get(k) for k in ['user_id','category','level','question_count']}
                    after = {'user_id': uid, 'category': cat, 'level': level, 'question_count': qcnt}
                    self._log_operation("edit_test_config", "test_config", target_id=cfg['id'],
                                        details=f"分类:{cat},级别:{level},题数:{qcnt}",
                                        before_state=before, after_state=after)
                else:
                    self.db.execute(
                        "INSERT INTO test_config (user_id, category, level, question_count) VALUES (?,?,?,?)",
                        [uid, cat, level, qcnt])
                    after = {'user_id': uid, 'category': cat, 'level': level, 'question_count': qcnt}
                    self._log_operation("add_test_config", "test_config",
                                        details=f"用户:{uid},分类:{cat},级别:{level},题数:{qcnt}",
                                        after_state=after)
                self.snack("已保存")
                self.page.run_task(self._reload)
            except Exception as ex:
                self.snack(f"保存失败: {ex}")

        self.form_dialog("编辑配置" if is_edit else "添加配置", fields, on_submit)

    def _delete_config(self, cfg):
        desc = f"{cfg.get('category','?')}/{cfg.get('level','?')}"
        self.confirm_and_run("删除配置", f"确定删除测试配置「{desc}」吗？",
                             self._do_delete_config, cfg['id'],
                             success_msg="已删除", loading_msg="删除中...")

    async def _do_delete_config(self, cfg_id):
        self.db.execute("DELETE FROM test_config WHERE id=?", [cfg_id])
        self._log_operation("delete_test_config", "test_config", target_id=cfg_id)
        await self._reload()
