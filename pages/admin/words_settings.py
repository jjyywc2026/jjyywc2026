# pages/admin/words_settings.py
import flet as ft
import asyncio
from pages.admin.base import AdminBaseTab


class WordsSettingsTab(AdminBaseTab):
    """单词设置：english_mode_config + practice_control"""

    def __init__(self, page):
        super().__init__(page)
        self._content = None
        self._collapsed_users = set()  # 折叠的用户ID集合

    def build(self):
        self._content = ft.Column(spacing=8, expand=True, scroll=ft.ScrollMode.ADAPTIVE)
        return self._content

    async def load_data(self):
        await self._load()

    def _safe(self, sql, params=None):
        try:
            return self.db.fetch_all(sql, params) or []
        except Exception as e:
            print(f"[words_settings] query fail: {e}")
            return []

    def _safe1(self, sql, params=None):
        try:
            return self.db.fetch_one(sql, params)
        except Exception as e:
            print(f"[words_settings] query1 fail: {e}")
            return None

    async def _load(self):
        await asyncio.sleep(0.05)

        def _query_all():
            # 10条SQL合并为1次批量HTTP请求（fetch_many），消除串行延迟
            statements = [
                ("SELECT COUNT(*) as cnt FROM words", []),
                ("SELECT COUNT(*) as cnt FROM units", []),
                ("SELECT COUNT(*) as cnt FROM grades", []),
                ("SELECT mode_id, word_length_min, word_length_max, weight_levels, score_per_game, time_limit, play_count_per_day, words_per_game, exp_num, min_score, max_score FROM english_mode_config ORDER BY mode_id", []),
                ("SELECT mode_id, mode_name, category, description FROM difficulty_modes ORDER BY mode_id", []),
                ("SELECT control_id, user_id, grade_id, volume_id, unit_id, enabled FROM practice_control ORDER BY user_id, grade_id, volume_id, unit_id", []),
                ("SELECT grade_id, grade_name FROM grades ORDER BY grade_id", []),
                ("SELECT volume_id, volume_type, grade_id FROM volumes ORDER BY grade_id, volume_id", []),
                ("SELECT unit_id, unit_name, volume_id FROM units ORDER BY volume_id, unit_id", []),
                ("SELECT user_id, username FROM users ORDER BY username", []),
            ]
            try:
                results = self.db.fetch_many(statements)
            except Exception as e:
                print(f"[words_settings] batch query fail: {e}")
                results = [[] for _ in statements]

            def _safe(idx):
                r = results[idx] if idx < len(results) else []
                return r if r is not None else []

            total_words = _safe(0)
            total_units = _safe(1)
            total_grades = _safe(2)
            modes = _safe(3)
            diff_modes = _safe(4)
            ranges = _safe(5)
            grades = _safe(6)
            volumes = _safe(7)
            units = _safe(8)
            users = _safe(9)
            return (total_words[0] if total_words else None,
                    total_units[0] if total_units else None,
                    total_grades[0] if total_grades else None,
                    modes, diff_modes, ranges, grades, volumes, units, users)

        total_words, total_units, total_grades, modes, diff_modes, ranges, grades, volumes, units, users = await asyncio.to_thread(_query_all)

        self._diff_modes = diff_modes
        mode_name_map = {m['mode_id']: m for m in diff_modes}
        self._grades = grades
        self._volumes = volumes
        self._units = units
        self._users = users
        grades_map = {g['grade_id']: g['grade_name'] for g in grades}
        vols_map = {v['volume_id']: v['volume_type'] for v in volumes}
        units_map = {u['unit_id']: u['unit_name'] for u in units}
        users_map = {u['user_id']: u['username'] for u in users}

        # 概览
        overview = self._card(ft.Column([
            ft.Text("词库概览", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800),
            ft.Divider(height=1, color=ft.Colors.GREY_200),
            ft.Row([
                self._stat("年级", total_grades['cnt'] if total_grades else 0),
                self._stat("单元", total_units['cnt'] if total_units else 0),
                self._stat("单词", total_words['cnt'] if total_words else 0),
            ], alignment=ft.MainAxisAlignment.SPACE_EVENLY),
        ]))

        # ---------- english_mode_config 列表 ----------
        mode_list = ft.ListView(spacing=2, expand=True)
        tiles = []
        for m in modes or []:
            mid = m['mode_id']
            dinfo = mode_name_map.get(mid, {})
            mname = dinfo.get('description') or dinfo.get('mode_name') or f"模式{mid}"
            mcat = dinfo.get('category', '')
            cat_label = f" · {mcat}" if mcat else ""
            tiles.append(self._list_tile(
                ft.Icon(ft.Icons.GAMES, size=20, color=ft.Colors.TEAL_600),
                ft.Text(f"{mname} (ID:{mid}){cat_label}", size=12, weight=ft.FontWeight.BOLD),
                ft.Text(f"每题{m['time_limit']}秒 · 每局{m['words_per_game']}词 · {m['play_count_per_day']}次/天 · {m['score_per_game']}分 · 经验{m.get('exp_num',1)} · 得分{m.get('min_score',1)}-{m.get('max_score',3)}",
                        size=10, color=ft.Colors.GREY_500),
                trailing=ft.Icon(ft.Icons.ARROW_FORWARD_IOS, size=14, color=ft.Colors.GREY_400),
                on_click=lambda e, mode=m: self._edit_mode(mode),
            ))
        if not tiles:
            tiles.append(self._empty("暂无模式配置"))
        mode_list.controls = tiles

        # ---------- practice_control 列表（按用户分组） ----------
        range_list = ft.ListView(spacing=2, expand=True)
        rt = []
        # 按user_id分组
        from collections import defaultdict
        user_groups = defaultdict(list)
        for r in ranges or []:
            uid = r.get('user_id', 0)
            user_groups[uid].append(r)

        # 排序：全部用户(uid=0)在前，其他按user_id
        sorted_uids = sorted(user_groups.keys(), key=lambda x: (0 if x == 0 else 1, x))

        for uid in sorted_uids:
            user_ranges = user_groups[uid]
            user_name = users_map.get(uid, f"用户{uid}") if uid else "全部用户"
            is_collapsed = uid in self._collapsed_users
            # 分组标题（可点击折叠）
            group_header = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.EXPAND_LESS if not is_collapsed else ft.Icons.EXPAND_MORE,
                            size=16, color=ft.Colors.TEAL_700 if uid else ft.Colors.GREY_600),
                    ft.Container(width=4, height=16, border_radius=2,
                                 bgcolor=ft.Colors.TEAL_500 if uid else ft.Colors.GREY_400),
                    ft.Text(f"{user_name}", size=12, weight=ft.FontWeight.BOLD,
                            color=ft.Colors.TEAL_800 if uid else ft.Colors.GREY_700),
                    ft.Container(
                        content=ft.Text(f"{len(user_ranges)}项", size=9, color=ft.Colors.WHITE,
                                        weight=ft.FontWeight.BOLD),
                        bgcolor=ft.Colors.TEAL_400 if uid else ft.Colors.GREY_400,
                        border_radius=8, padding=ft.padding.symmetric(horizontal=6, vertical=1)),
                    ft.Container(expand=True),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                bgcolor=ft.Colors.TEAL_50 if uid else ft.Colors.GREY_100,
                border_radius=4, margin=ft.margin.only(top=4, bottom=2),
                on_click=lambda e, u=uid: self._toggle_user_group(u),
            )
            rt.append(group_header)

            if not is_collapsed:
                for r in user_ranges:
                    is_enabled = bool(r.get('enabled', 1))
                    gid = r.get('grade_id')
                    vid = r.get('volume_id')
                    unit_id = r.get('unit_id')
                    gname = grades_map.get(gid, f"年级{gid}")
                    vname = vols_map.get(vid, f"册{vid}")
                    uname = units_map.get(unit_id, "全部单元") if unit_id else "全部单元"
                    rt.append(self._list_tile(
                        ft.Icon(ft.Icons.BOOK, size=16, color=ft.Colors.BLUE_500),
                        ft.Row([
                            ft.Text(f"{gname} · {vname} · {uname}", size=12),
                            self._status_chip(is_enabled, "启用", "禁用"),
                        ], spacing=4),
                        trailing=ft.IconButton(ft.Icons.DELETE, icon_size=14, icon_color=ft.Colors.RED_400,
                                               on_click=lambda e, rg=r: self._delete_range(rg)),
                        on_click=lambda e, rg=r: self._edit_range(rg),
                        leading_width=24,
                    ))
        if not rt:
            rt.append(self._empty("暂无范围配置"))
        range_list.controls = rt

        self._content.controls = [
            overview,
            ft.Row([
                ft.Text("游戏模式配置 (english_mode_config)", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.BLUE_700),
                ft.Container(expand=True),
                self._action_button("新增模式", ft.Icons.ADD, self._add_mode, ft.Colors.GREEN_600),
            ]),
            mode_list,
            ft.Container(height=6),
            ft.Row([
                ft.Text("单词范围配置 (practice_control)", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.TEAL_700),
                ft.Container(expand=True),
                self._action_button("添加范围", ft.Icons.ADD, self._add_range, ft.Colors.TEAL_600),
            ]),
            range_list,
        ]
        self.page.update()

    def _toggle_user_group(self, uid):
        """折叠/展开用户分组"""
        if uid in self._collapsed_users:
            self._collapsed_users.discard(uid)
        else:
            self._collapsed_users.add(uid)
        self.page.run_task(self._load)

    def _stat(self, label, value):
        return ft.Column([
            ft.Text(str(value), size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
            ft.Text(label, size=10, color=ft.Colors.GREY_500),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2)

    # ==================== english_mode_config CRUD ====================
    def _add_mode(self, e=None):
        self._open_mode_form(None)

    def _edit_mode(self, mode):
        self._open_mode_form(mode)

    def _open_mode_form(self, mode):
        is_edit = mode is not None
        fields = [
            ("模式ID", "mode_id", mode.get('mode_id') if is_edit else "", "number"),
            ("最短单词长度", "word_length_min", mode.get('word_length_min', 1) if is_edit else 1, "number"),
            ("最长单词长度", "word_length_max", mode.get('word_length_max', 50) if is_edit else 50, "number"),
            ("权重等级", "weight_levels", mode.get('weight_levels', 1) if is_edit else 1, "number"),
            ("每局得分", "score_per_game", mode.get('score_per_game', 1) if is_edit else 1, "number"),
            ("每题秒数", "time_limit", mode.get('time_limit', 3) if is_edit else 3, "number"),
            ("每天次数", "play_count_per_day", mode.get('play_count_per_day', 100) if is_edit else 100, "number"),
            ("每局单词数", "words_per_game", mode.get('words_per_game', 20) if is_edit else 20, "number"),
            ("每局经验值", "exp_num", mode.get('exp_num', 1) if is_edit else 1, "number"),
            ("最低得分", "min_score", mode.get('min_score', 1) if is_edit else 1, "number"),
            ("最高得分", "max_score", mode.get('max_score', 3) if is_edit else 3, "number"),
        ]

        def on_submit(data):
            try:
                mid = int(data['mode_id'] or 0)
                if mid <= 0:
                    self.snack("请输入模式ID")
                    return
                vals = [
                    int(data['word_length_min'] or 0), int(data['word_length_max'] or 0),
                    int(data['weight_levels'] or 0), int(data['score_per_game'] or 0),
                    int(data['time_limit'] or 0), int(data['play_count_per_day'] or 0),
                    int(data['words_per_game'] or 0),
                    int(data['exp_num'] or 0), int(data['min_score'] or 0), int(data['max_score'] or 0),
                ]
                existing = self._safe1("SELECT mode_id FROM english_mode_config WHERE mode_id=?", [mid])
                if existing:
                    old = self._safe1("SELECT * FROM english_mode_config WHERE mode_id=?", [mid])
                    self.db.execute("""UPDATE english_mode_config SET word_length_min=?, word_length_max=?,
                        weight_levels=?, score_per_game=?, time_limit=?, play_count_per_day=?, words_per_game=?,
                        exp_num=?, min_score=?, max_score=?
                        WHERE mode_id=?""", vals + [mid])
                    after = dict(zip(['word_length_min','word_length_max','weight_levels','score_per_game',
                                      'time_limit','play_count_per_day','words_per_game',
                                      'exp_num','min_score','max_score'], vals))
                    self._log_operation("edit_mode", "english_mode", target_id=mid,
                                        details=f"每题{data['time_limit']}秒,每局{data['words_per_game']}词,经验{data['exp_num']}",
                                        before_state=dict(old) if old else None, after_state=after)
                else:
                    self.db.execute("""INSERT INTO english_mode_config
                        (mode_id, word_length_min, word_length_max, weight_levels, score_per_game, time_limit, play_count_per_day, words_per_game, exp_num, min_score, max_score)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""", [mid] + vals)
                    after = dict(zip(['word_length_min','word_length_max','weight_levels','score_per_game',
                                      'time_limit','play_count_per_day','words_per_game',
                                      'exp_num','min_score','max_score'], vals))
                    self._log_operation("add_mode", "english_mode", target_id=mid,
                                        details=f"每题{data['time_limit']}秒,每局{data['words_per_game']}词,经验{data['exp_num']}",
                                        after_state=after)
                self.snack("已保存")
                self.page.run_task(self._load)
            except Exception as ex:
                self.snack(f"保存失败: {ex}")

        self.form_dialog("编辑模式" if is_edit else "新增模式", fields, on_submit)

    # ==================== practice_control CRUD（级联下拉） ====================
    def _add_range(self, e=None):
        self._open_range_form(None)

    def _edit_range(self, rg):
        self._open_range_form(rg)

    def _open_range_form(self, rg):
        is_edit = rg is not None
        # 数据兜底：如果未加载则实时查询
        grades = getattr(self, '_grades', []) or self._safe("SELECT grade_id, grade_name FROM grades ORDER BY grade_id")
        volumes = getattr(self, '_volumes', []) or self._safe("SELECT volume_id, volume_type, grade_id FROM volumes ORDER BY grade_id, volume_id")
        units = getattr(self, '_units', []) or self._safe("SELECT unit_id, unit_name, volume_id FROM units ORDER BY volume_id, unit_id")
        users = getattr(self, '_users', []) or self._safe("SELECT user_id, username FROM users ORDER BY username")
        self._grades, self._volumes, self._units, self._users = grades, volumes, units, users

        # 查询各单元单词数（用于过滤无单词单元 + 显示数量）
        word_counts = {}
        try:
            rows = self.db.fetch_all("SELECT unit_id, COUNT(*) as cnt FROM words GROUP BY unit_id")
            for r in rows or []:
                word_counts[str(r['unit_id'])] = int(r['cnt'] or 0)
        except Exception as e:
            print(f"[words_settings] word count query fail: {e}")

        # 预计算：每个册别的有效单元数和总词数
        vol_info = {}  # volume_id -> {'units': n, 'words': n}
        for v in volumes:
            vid = str(v['volume_id'])
            vol_units = [u for u in units if str(u.get('volume_id')) == vid]
            valid_units = [u for u in vol_units if word_counts.get(str(u['unit_id']), 0) > 0]
            total_words = sum(word_counts.get(str(u['unit_id']), 0) for u in valid_units)
            vol_info[vid] = {'units': len(valid_units), 'words': total_words}

        # 预计算：每个年级的有效册别数
        grade_vol_count = {}
        for g in grades:
            gid = str(g['grade_id'])
            count = sum(1 for v in volumes
                        if str(v.get('grade_id')) == gid and vol_info.get(str(v['volume_id']), {}).get('units', 0) > 0)
            grade_vol_count[gid] = count

        def _make_opt(key_val, label):
            return ft.dropdown.Option(key=str(key_val), text=str(label))

        # 级联下拉（key=ID, text=名称+数量）
        grade_dd = ft.Dropdown(label="年级", border_radius=8, expand=True,
            options=[_make_opt(g['grade_id'],
                f"{g['grade_name']} ({grade_vol_count.get(str(g['grade_id']),0)}册)")
                for g in grades])
        vol_dd = ft.Dropdown(label="册别", border_radius=8, expand=True, options=[])
        unit_dd = ft.Dropdown(label="单元(可选)", border_radius=8, expand=True, options=[])
        user_dd = ft.Dropdown(label="用户", border_radius=8, expand=True,
            options=[_make_opt("0", "全部用户")] + [_make_opt(u['user_id'], u['username']) for u in users])
        enabled_dd = ft.Dropdown(label="启用", border_radius=8, expand=True,
            options=[_make_opt("1", "启用"), _make_opt("0", "禁用")])

        # 联动状态提示
        hint_text = ft.Text("", size=11, color=ft.Colors.ORANGE_700,
                            weight=ft.FontWeight.W_500, visible=False)
        hint_row = ft.Container(content=hint_text, visible=False,
                                padding=ft.padding.symmetric(horizontal=4, vertical=2))

        def _show_hint(msg, color=ft.Colors.ORANGE_700):
            hint_text.value = msg
            hint_text.color = color
            hint_text.visible = True
            hint_row.visible = True

        def _hide_hint():
            hint_text.visible = False
            hint_row.visible = False

        def _set_vols(grade_id, preserve_value=None):
            gid_str = str(grade_id)
            vols = [v for v in volumes if str(v.get('grade_id')) == gid_str]
            # 过滤：只保留至少有一个单元含单词的册别
            valid_vols = [v for v in vols if vol_info.get(str(v['volume_id']), {}).get('units', 0) > 0]
            if not valid_vols:
                vol_dd.options = []
                vol_dd.value = None
                vol_dd.disabled = True
                unit_dd.options = [_make_opt("0", "全部单元")]
                unit_dd.value = "0"
                unit_dd.disabled = True
                if vols:
                    _show_hint(f"⚠ 该年级 {len(vols)} 个册别均无单词，已全部过滤",
                               color=ft.Colors.RED_600)
                else:
                    _show_hint("⚠ 该年级暂无册别，请先在册别表中添加对应数据")
                return
            vol_dd.disabled = False
            vol_dd.options = [_make_opt(v['volume_id'],
                f"{v['volume_type']} ({vol_info[str(v['volume_id'])]['units']}单元·{vol_info[str(v['volume_id'])]['words']}词)")
                for v in valid_vols]
            # 编辑回显：如果原册别被过滤，保留并标注
            if preserve_value and not any(str(o.key) == str(preserve_value) for o in vol_dd.options):
                vol_dd.options.insert(0, _make_opt(preserve_value, f"原册别(已无单词)"))
                vol_dd.value = str(preserve_value)
            else:
                vol_dd.value = vol_dd.options[0].key if vol_dd.options else None
            _set_units(vol_dd.value, preserve_value=None)

        def _set_units(volume_id, preserve_value=None):
            vid_str = str(volume_id) if volume_id else None
            uns = [u for u in units if str(u.get('volume_id')) == vid_str] if vid_str else []
            unit_dd.disabled = False
            # 过滤无单词的单元
            valid_units = [u for u in uns if word_counts.get(str(u['unit_id']), 0) > 0]
            empty_count = len(uns) - len(valid_units)
            total_words = sum(word_counts.get(str(u['unit_id']), 0) for u in valid_units)
            unit_dd.options = [_make_opt("0", f"全部单元 (共{total_words}词)")] + [
                _make_opt(u['unit_id'], f"{u['unit_name']} ({word_counts.get(str(u['unit_id']),0)}词)")
                for u in valid_units]
            # 编辑回显：如果原单元被过滤，保留并标注
            if preserve_value and preserve_value != "0" and not any(str(o.key) == str(preserve_value) for o in unit_dd.options):
                unit_dd.options.append(_make_opt(preserve_value, "原单元(已无单词)"))
                unit_dd.value = str(preserve_value)
            else:
                unit_dd.value = "0"
            if not uns:
                _show_hint("ℹ 该册别暂无单元，保存后默认使用该册别全部单元",
                           color=ft.Colors.BLUE_700)
            elif empty_count > 0:
                _show_hint(f"⚠ 已过滤 {empty_count} 个无单词的单元，不可选择",
                           color=ft.Colors.RED_600)
            else:
                _hide_hint()

        def on_grade_change(e):
            gid = grade_dd.value if grade_dd.value else None
            if gid:
                _set_vols(gid)
                self.page.update()

        def on_vol_change(e):
            vid = vol_dd.value if vol_dd.value else None
            _set_units(vid)
            self.page.update()

        grade_dd.on_change = on_grade_change
        vol_dd.on_change = on_vol_change

        # 初始化值
        if is_edit:
            user_dd.value = str(rg.get('user_id', 0))
            grade_dd.value = str(rg['grade_id'])
            _set_vols(rg['grade_id'], preserve_value=rg.get('volume_id'))
            vol_dd.value = str(rg['volume_id'])
            _set_units(rg['volume_id'], preserve_value=rg.get('unit_id', 0))
            unit_dd.value = str(rg.get('unit_id', 0) or 0)
            enabled_dd.value = "1" if rg.get('enabled', 1) else "0"
        else:
            user_dd.value = "0"
            enabled_dd.value = "1"
            if grades:
                # 新增时默认选第一个有数据的年级
                first_valid = next((g for g in grades if grade_vol_count.get(str(g['grade_id']), 0) > 0), grades[0])
                grade_dd.value = str(first_valid['grade_id'])
                _set_vols(first_valid['grade_id'])

        controls = [user_dd, grade_dd, vol_dd, unit_dd, enabled_dd, hint_row]

        def do_submit(e):
            try:
                uid = int(user_dd.value or 0)
                gid = int(grade_dd.value or 0)
                vid = int(vol_dd.value or 0)
                unit_id = int(unit_dd.value or 0)
                unit_id = unit_id if unit_id > 0 else None
                enabled = 1 if enabled_dd.value == "1" else 0
                if not gid or not vid:
                    self.snack("请选择年级和册别")
                    return
                if is_edit:
                    self.db.execute(
                        "UPDATE practice_control SET user_id=?, grade_id=?, volume_id=?, unit_id=?, enabled=? WHERE control_id=?",
                        [uid, gid, vid, unit_id, enabled, rg['control_id']])
                    before = {k: rg.get(k) for k in ['user_id','grade_id','volume_id','unit_id','enabled']}
                    after = {'user_id': uid, 'grade_id': gid, 'volume_id': vid,
                             'unit_id': unit_id, 'enabled': enabled}
                    self._log_operation("edit_range", "practice_control", target_id=rg['control_id'],
                                        details=f"用户:{uid},年级:{gid},册:{vid},单元:{unit_id}",
                                        before_state=before, after_state=after)
                else:
                    self.db.execute(
                        "INSERT INTO practice_control (user_id, grade_id, volume_id, unit_id, enabled) VALUES (?,?,?,?,?)",
                        [uid, gid, vid, unit_id, enabled])
                    after = {'user_id': uid, 'grade_id': gid, 'volume_id': vid,
                             'unit_id': unit_id, 'enabled': enabled}
                    self._log_operation("add_range", "practice_control",
                                        details=f"用户:{uid},年级:{gid},册:{vid},单元:{unit_id}",
                                        after_state=after)
                dlg.open = False
                self._close_dialog(dlg)
                self.snack("已保存")
                self.page.run_task(self._load)
            except Exception as ex:
                self.snack(f"保存失败: {ex}")

        dlg = ft.AlertDialog(
            title=ft.Text("编辑范围" if is_edit else "添加范围", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=ft.Column(controls, spacing=8, scroll=ft.ScrollMode.ADAPTIVE),
                                 width=400, padding=4),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.ElevatedButton("保存", on_click=do_submit,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE)),
            ],
        )
        self.page.open(dlg)

    def _delete_range(self, rg):
        desc = f"用户{rg.get('user_id')} 年级{rg.get('grade_id')} 册{rg.get('volume_id')}"
        self.confirm_and_run("删除范围", f"确定删除范围「{desc}」吗？",
                             self._do_delete_range, rg['control_id'],
                             success_msg="已删除", loading_msg="删除中...")

    async def _do_delete_range(self, control_id):
        self.db.execute("DELETE FROM practice_control WHERE control_id=?", [control_id])
        self._log_operation("delete_range", "practice_control", target_id=control_id)
        await self._load()
