# pages/admin/cihai_config.py
import flet as ft
import asyncio
from pages.admin.base import AdminBaseTab

# type 英文 → 中文映射
TYPE_MAP = {"word": "好词", "sentence": "好句", "opening": "好开头", "ending": "好结尾"}
TYPE_REVERSE = {v: k for k, v in TYPE_MAP.items()}
TYPE_ORDER = ["word", "sentence", "opening", "ending"]

# 类型主题色
TYPE_THEME = {
    "word":     {"primary": "#16A34A", "bg": "#F0FDF4", "border": "#BBF7D0", "light": "#DCFCE7", "text": "#166534"},
    "sentence": {"primary": "#2563EB", "bg": "#EFF6FF", "border": "#BFDBFE", "light": "#DBEAFE", "text": "#1E40AF"},
    "opening":  {"primary": "#D97706", "bg": "#FFFBEB", "border": "#FDE68A", "light": "#FEF3C7", "text": "#92400E"},
    "ending":   {"primary": "#DB2777", "bg": "#FDF2F8", "border": "#F9A8D4", "light": "#FCE7F3", "text": "#9D174D"},
}

# 配置中各类型数量字段
COUNT_FIELDS = {
    "word": "word_count",
    "sentence": "sentence_count",
    "opening": "opening_count",
    "ending": "ending_count",
}


class CihaiConfigTab(AdminBaseTab):
    """辞海答题配置管理（chinese_mode_config）"""

    def __init__(self, page):
        super().__init__(page)
        self._list_view = None
        self._material_count_cache = {}  # type -> count

    def build(self):
        self._list_view = ft.ListView(spacing=2, expand=True)
        return ft.Column([
            ft.Row([
                ft.Container(content=ft.Icon(ft.Icons.TIMER_OUTLINED, size=16, color=ft.Colors.WHITE),
                            bgcolor="#0D9488", border_radius=6, padding=4),
                ft.Text("辞海答题配置", size=14, weight=ft.FontWeight.W_700, color="#134E4A", expand=True),
                self._action_button("添加配置", ft.Icons.ADD, self._add_config, "#0D9488"),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            self._list_view,
        ], spacing=6, expand=True)

    async def load_data(self):
        await self._reload()

    async def _reload(self):
        await asyncio.sleep(0.05)

        def _query():
            try:
                configs = self.db.fetch_all("SELECT * FROM chinese_mode_config ORDER BY mode_id")
                # 统计各类型题目数量
                counts = {}
                for t in TYPE_ORDER:
                    r = self.db.fetch_one("SELECT COUNT(*) as cnt FROM materials WHERE type=?", [t])
                    counts[t] = r['cnt'] if r else 0
                return configs, counts, None
            except Exception as e:
                return [], {}, str(e)

        configs, counts, err = await asyncio.to_thread(_query)
        if err:
            self.snack(f"加载失败: {err}")
            return
        self._material_count_cache = counts

        tiles = []
        if not configs:
            tiles.append(self._empty("暂无配置，点击右上角添加"))
        else:
            for cfg in configs:
                tiles.append(self._config_card(cfg, counts))
        self._list_view.controls = tiles
        try:
            self.page.update()
        except Exception:
            pass

    def _config_card(self, cfg, counts):
        mode_id = cfg.get('mode_id', '?')
        study_time = cfg.get('study_time', 0)
        answer_duration = cfg.get('answer_duration', 0)

        # 各类型数量 chips
        count_chips = []
        for t_en in TYPE_ORDER:
            field = COUNT_FIELDS[t_en]
            cnt = int(cfg.get(field, 0) or 0)
            available = counts.get(t_en, 0)
            th = TYPE_THEME[t_en]
            if cnt > 0:
                count_chips.append(ft.Container(
                    content=ft.Text(f"{TYPE_MAP[t_en]} {cnt}/{available}", size=9,
                                    weight=ft.FontWeight.W_600, color=th["text"]),
                    bgcolor=th["light"], border_radius=5,
                    padding=ft.padding.symmetric(horizontal=6, vertical=2),
                    border=ft.border.all(0.5, th["border"]),
                ))

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.LABEL, size=12, color="#0F766E"),
                            ft.Text(f"模式 {mode_id}", size=12, weight=ft.FontWeight.W_700, color="#134E4A"),
                        ], spacing=3),
                        bgcolor="#F0FDFA", border_radius=6,
                        padding=ft.padding.symmetric(horizontal=8, vertical=3),
                    ),
                    ft.Container(expand=True),
                    ft.IconButton(ft.Icons.EDIT_SQUARE, icon_size=16, icon_color="#3B82F6",
                                  on_click=lambda e, c=cfg: self._edit_config(c)),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color="#EF4444",
                                  on_click=lambda e, c=cfg: self._delete_config(c)),
                ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    self._stat_chip("背诵", f"{study_time}s/字", "#F0FDFA", "#0F766E"),
                    self._stat_chip("答题", f"{answer_duration}s/字", "#FFFBEB", "#92400E"),
                ], spacing=6),
                ft.Row(count_chips, spacing=4, wrap=True) if count_chips else ft.Container(),
            ], spacing=5, tight=True),
            bgcolor="#FAFAFA", border_radius=8, padding=8, margin=ft.margin.only(bottom=4),
            border=ft.border.all(0.5, "#E5E7EB"),
            on_click=lambda e, c=cfg: self._edit_config(c),
            ink=True,
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        )

    def _stat_chip(self, label, value, bg, text_color):
        return ft.Container(
            content=ft.Row([
                ft.Text(label, size=9, color="#6B7280"),
                ft.Text(value, size=11, weight=ft.FontWeight.W_700, color=text_color),
            ], spacing=3),
            bgcolor=bg, border_radius=5, padding=ft.padding.symmetric(horizontal=7, vertical=3),
        )

    # ---------- 配置 CRUD ----------
    def _add_config(self, e=None):
        self._open_config_form(None)

    def _edit_config(self, cfg):
        self._open_config_form(cfg)

    def _open_config_form(self, cfg):
        is_edit = cfg is not None

        mode_tf = ft.TextField(
            label="模式ID", value=str(cfg.get('mode_id', '')) if is_edit else '',
            border_radius=8, expand=True, text_size=13,
            keyboard_type=ft.KeyboardType.NUMBER,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
            prefix_icon=ft.Icons.LABEL,
            disabled=is_edit,
        )
        study_tf = ft.TextField(
            label="背诵时间（秒/字）",
            value=str(cfg.get('study_time', 2.5)) if is_edit else "2.5",
            border_radius=8, expand=True, text_size=13,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
            prefix_icon=ft.Icons.HOURGLASS_TOP,
        )
        answer_tf = ft.TextField(
            label="答题时间（秒/字）",
            value=str(cfg.get('answer_duration', 3.8)) if is_edit else "3.8",
            border_radius=8, expand=True, text_size=13,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
            prefix_icon=ft.Icons.TIMER,
        )
        # 各类型数量（带可用数量提示）
        count_fields = {}
        count_rows = []
        for t_en in TYPE_ORDER:
            field = COUNT_FIELDS[t_en]
            th = TYPE_THEME[t_en]
            available = self._material_count_cache.get(t_en, 0)
            tf = ft.TextField(
                label=f"{TYPE_MAP[t_en]}数量",
                value=str(cfg.get(field, 0)) if is_edit else "0",
                border_radius=8, text_size=13, width=130,
                keyboard_type=ft.KeyboardType.NUMBER,
                content_padding=ft.padding.symmetric(horizontal=8, vertical=6),
                suffix_text=f"/{available}",
            )
            count_fields[t_en] = tf
            count_rows.append(ft.Container(
                content=tf, bgcolor=th["bg"], border_radius=8,
                border=ft.border.all(0.5, th["border"]), padding=2,
            ))

        def on_submit():
            try:
                mode_id = int(mode_tf.value or 0)
                study_time = float(study_tf.value or 2.5)
                answer_duration = float(answer_tf.value or 3.8)
                counts = {t_en: int(tf.value or 0) for t_en, tf in count_fields.items()}
                if is_edit:
                    before = {k: cfg.get(k) for k in ['mode_id', 'study_time', 'answer_duration'] + list(COUNT_FIELDS.values())}
                    self.db.execute(
                        "UPDATE chinese_mode_config SET study_time=?, answer_duration=?, word_count=?, sentence_count=?, opening_count=?, ending_count=? WHERE mode_id=?",
                        [study_time, answer_duration, counts['word'], counts['sentence'],
                         counts['opening'], counts['ending'], mode_id])
                    after = {'mode_id': mode_id, 'study_time': study_time, 'answer_duration': answer_duration, **counts}
                    self._log_operation("edit_cihai_config", "chinese_mode_config", target_id=mode_id,
                                        details=f"模式{mode_id},背诵:{study_time}s,答题:{answer_duration}s",
                                        before_state=before, after_state=after)
                else:
                    self.db.execute(
                        "INSERT INTO chinese_mode_config (mode_id, study_time, answer_duration, word_count, sentence_count, opening_count, ending_count) VALUES (?,?,?,?,?,?,?)",
                        [mode_id, study_time, answer_duration, counts['word'], counts['sentence'],
                         counts['opening'], counts['ending']])
                    after = {'mode_id': mode_id, 'study_time': study_time, 'answer_duration': answer_duration, **counts}
                    self._log_operation("add_cihai_config", "chinese_mode_config", target_id=mode_id,
                                        details=f"模式{mode_id},背诵:{study_time}s,答题:{answer_duration}s",
                                        after_state=after)
                self.snack("已保存")
                self.page.run_task(self._reload)
            except Exception as ex:
                self.snack(f"保存失败: {ex}")

        body = ft.Column([
            mode_tf, study_tf, answer_tf,
            ft.Text("各类型题目数量", size=12, weight=ft.FontWeight.W_600, color="#374151"),
            ft.Row(count_rows, spacing=6, wrap=True),
        ], spacing=10, tight=True, width=360)

        dlg = self._beauty_dialog("编辑配置" if is_edit else "添加配置",
                                  ft.Icons.SETTINGS, "#0D9488", body, on_submit, "#0D9488")
        self.page.open(dlg)

    def _delete_config(self, cfg):
        mode_id = cfg.get('mode_id', '?')
        self.confirm_and_run("删除配置", f"确定删除模式 {mode_id} 的配置吗？",
                             self._do_delete_config, cfg.get('id', mode_id),
                             success_msg="已删除", loading_msg="删除中...")

    async def _do_delete_config(self, cfg_id):
        self.db.execute("DELETE FROM chinese_mode_config WHERE id=?", [cfg_id])
        self._log_operation("delete_cihai_config", "chinese_mode_config", target_id=cfg_id)
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
