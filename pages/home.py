# pages/home.py
import flet as ft
import asyncio
import datetime
import time

# 首页数据缓存：{ (user_id, date_str): (timestamp, data) }
_home_cache = {}
_CACHE_TTL = 300  # 5分钟


class HomePage:
    """首页：时间控制数据展示，数据走云端 Turso，admin可切换用户"""

    EMPOWERMENT_ITEM_ID = 1001  # 限时赋能卡

    def __init__(self, page: ft.Page, user_data: dict):
        self.page = page
        self.user_data = user_data
        self.is_admin = user_data.get('type') == "admin"
        self.db = page._db          # 云端 TursoClient
        self.loading = page.loading_overlay

        # 当前查看的用户（admin可切换）
        self.selected_user_id = user_data.get('id')
        self._user_list = []

        # 数据
        self._data = None
        self._content = ft.Column(spacing=12, scroll=ft.ScrollMode.ADAPTIVE)

        # 控件引用
        self._user_name_ref = None
        self._records_col_ref = None
        self._load_more_btn_ref = None

        # 记录分页
        self._records_offset = 0
        self._records_all_loaded = False
        self._RECORDS_PAGE_SIZE = 10
        self._loaded = False

        # 预加载用户列表（admin）
        if self.is_admin:
            self._load_user_list()

        self.page.run_task(self.load_data)

    # ================================================================
    # 用户列表 & 切换（admin）
    # ================================================================
    def _load_user_list(self):
        try:
            rows = self.db.fetch_all("SELECT user_id, username FROM users ORDER BY username")
            self._user_list = [(r['user_id'], r['username']) for r in rows] if rows else []
        except Exception as e:
            print(f"[home] 用户列表加载失败: {e}")
            self._user_list = [(self.user_data.get('id'), self.user_data.get('username', '未知'))]

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
                title=ft.Text(name, size=16),
                on_click=lambda _, u=uid: self._select_user(u),
                selected=(self.selected_user_id == uid),
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
        self.page.selected_user_id = user_id  # 全局联动
        self._loaded = False
        # 关闭所有 BottomSheet
        for o in list(self.page.overlay):
            if isinstance(o, ft.BottomSheet):
                self.page.close(o)
        if self._user_name_ref:
            self._user_name_ref.value = f"用户：{self._get_selected_user_name()}"
            self._user_name_ref.update()
        self.page.update()
        self.page.run_task(self.load_data)

    # ================================================================
    # 数据查询（云端）
    # ================================================================
    async def load_data(self):
        self.loading.show("加载首页数据...")
        start = time.time()
        await asyncio.sleep(0.1)
        try:
            self._data = await asyncio.to_thread(self._query_home_data)
        except Exception as e:
            print(f"[home] 数据加载失败: {e}")
            self._data = self._default_data()
        self._build_ui()
        elapsed = time.time() - start
        if elapsed < 0.4:
            await asyncio.sleep(0.4 - elapsed)
        self.loading.container.visible = False
        self._loaded = True
        self.page.update()

    def _on_refresh(self, e=None):
        """手动刷新：清缓存+重新加载"""
        _home_cache.clear()
        self._loaded = False
        self.page.run_task(self.load_data)

    def _default_data(self):
        return {
            'username': self._get_selected_user_name(),
            'level': 1, 'stars': 0, 'score': 0,
            'today_used': 0, 'daily_limit': 180, 'unused_today': 0, 'daily_total_time': 0,
            'week_total': 0, 'month_total': 0, 'year_total': 0, 'total_duration': 0,
            'exchange_total': 0, 'exchange_remaining': 0,
            'slots': [], 'current_slot_limit': 60,
            'temp_boost': 0, 'effective_limit': 60,
            'card_count': 0, 'cooldown_minutes': 0, 'in_cooldown': False,
            'remaining_cooldown': 0,
            'tasks': [], 'records': [],
        }

    def _query_home_data(self):
        uid = self.selected_user_id
        d = self._default_data()
        if uid is None:
            return d
        now = datetime.datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        tomorrow_str = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        # ---- 缓存检查 ----
        cache_key = (uid, today_str)
        cached = _home_cache.get(cache_key)
        if cached and (time.time() - cached[0]) < _CACHE_TTL:
            return cached[1]

        month_start = now.strftime("%Y-%m-01")
        year_start = f"{now.year}-01-01"
        week_start = (now - datetime.timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        dur_expr = "ROUND((julianday(end_time)-julianday(start_time))*24*60)"
        today_start = today_str + " 00:00:00"
        tomorrow_start = tomorrow_str + " 00:00:00"

        # ---- 批量查询：1次HTTP请求拉全部数据 ----
        statements = [
            # 0: 用户信息
            ("SELECT username, level_id, total_stars, score, total_time FROM users WHERE user_id=?", [uid]),
            # 1: 时长聚合（today跨天：计算会话与今天窗口[今0点,明0点)的交集）
            (f"""
                SELECT COALESCE(SUM(CASE WHEN end_time>? AND start_time<? THEN
                           ROUND((julianday(MIN(end_time,?))-julianday(MAX(start_time,?)))*24*60)
                           ELSE 0 END),0) AS today,
                       COALESCE(SUM(CASE WHEN start_time>=? THEN {dur_expr} ELSE 0 END),0) AS week,
                       COALESCE(SUM(CASE WHEN start_time>=? THEN {dur_expr} ELSE 0 END),0) AS month,
                       COALESCE(SUM(CASE WHEN start_time>=? THEN {dur_expr} ELSE 0 END),0) AS year,
                       COALESCE(SUM({dur_expr}),0) AS total
                FROM time_jilu WHERE user_id=? AND end_time IS NOT NULL""",
             [today_start, tomorrow_start, tomorrow_start, today_start, week_start, month_start, year_start, uid]),
            # 2: 时间限制
            ("SELECT * FROM User_time_Limits WHERE user_id=?", [uid]),
            # 3: 使用记录
            (f"SELECT start_time, end_time, {dur_expr} as dur "
             "FROM time_jilu WHERE user_id=? AND end_time IS NOT NULL "
             "ORDER BY end_time DESC LIMIT ?", [uid, self._RECORDS_PAGE_SIZE]),
            # 4: 赋能卡数量
            ("SELECT COALESCE(SUM(quantity),0) as cnt FROM user_items WHERE user_id=? AND item_id=?",
             [uid, self.EMPOWERMENT_ITEM_ID]),
            # 5: 已兑换时间
            ("SELECT time_s FROM TIME_sy WHERE user_id=?", [uid]),
            # 6: 兑换记录
            ("SELECT minutes FROM use_computer_time_records WHERE user_id=? ORDER BY timestamp DESC LIMIT 1", [uid]),
            # 7: 任务列表（过滤有效期，不依赖user_tasks）
            ("SELECT t.id, t.name, t.target_count, t.reward_type, t.reward_value, "
             "t.mode_id, t.content_category "
             "FROM tasks t "
             "WHERE (t.user_id IS NULL OR t.user_id=?) AND t.status=1 "
             "AND (t.start_time IS NULL OR t.start_time='' OR date(t.start_time)<=?) "
             "AND (t.end_time IS NULL OR t.end_time='' OR date(t.end_time)>=?) "
             "ORDER BY t.sort_order, t.id",
             [uid, today_str, today_str]),
            # 8: 今日各模式正确答题数（从user__play_game_history，与桌面版一致）
            ("SELECT difficulty_type, SUM(play_count) as total "
             "FROM user__play_game_history "
             "WHERE user_id=? AND is_true=1 AND date>=? AND date<? "
             "GROUP BY difficulty_type",
             [uid, today_str, tomorrow_str]),
        ]

        try:
            results = self.db.fetch_many(statements)
        except Exception as e:
            print(f"[home] 批量查询失败: {e}")
            results = [[] for _ in statements]

        # 解析结果（按statements顺序）
        u = results[0][0] if results[0] else None
        dur = results[1][0] if results[1] else None
        tl = results[2][0] if results[2] else None
        rec_rows = results[3] if results[3] else []
        card = results[4][0] if results[4] else None
        sy = results[5][0] if results[5] else None
        ex = results[6][0] if results[6] else None
        tasks = results[7] if results[7] else []
        # 今日各模式正确答题数（从user__play_game_history，按difficulty_type分组）
        progress_map = {}
        for row in (results[8] if results[8] else []):
            progress_map[int(row['difficulty_type'])] = int(row['total'])

        # ---- 计算（纯内存，无IO）----
        if u:
            d['username'] = u.get('username') or d['username']
            d['level'] = int(u.get('level_id') or 1)
            d['stars'] = int(u.get('total_stars') or 0)
            d['score'] = int(u.get('score') or 0)
            d['daily_total_time'] = int(u.get('total_time') or 0)

        if dur:
            d['today_used'] = int(dur['today'])
            d['week_total'] = int(dur['week'])
            d['month_total'] = int(dur['month'])
            d['year_total'] = int(dur['year'])
            d['total_duration'] = int(dur['total'])

        latest_end = None
        latest_dur = 0
        if rec_rows:
            d['records'] = [{'start': r['start_time'], 'end': r['end_time'],
                             'minutes': int(r['dur'] or 0)} for r in rec_rows]
            self._records_offset = len(d['records'])
            self._records_all_loaded = len(d['records']) < self._RECORDS_PAGE_SIZE
            latest_end = d['records'][0]['end']
            latest_dur = d['records'][0]['minutes']
        else:
            d['records'] = []

        if tl:
            daily = int(tl.get('max_daily_limit') or tl.get('default_daily_limit') or 180)
            d['daily_limit'] = daily if daily > 0 else 180
            d['temp_boost'] = int(tl.get('temp_slot_boost') or 0)
            d['cooldown_minutes'] = int(tl.get('cool_time') or 0)
            slots = []
            for i in range(1, 4):
                s = tl.get(f'time_slot_{i}_start')
                e = tl.get(f'time_slot_{i}_end')
                lim = tl.get(f'time_slot_{i}_limit')
                if s and e and lim is not None:
                    slots.append((s, e, int(lim)))
            d['slots'] = slots
            cur_hm = now.strftime("%H:%M")
            for s, e, lim in slots:
                if s <= cur_hm <= e or (s > e and (cur_hm >= s or cur_hm <= e)):
                    d['current_slot_limit'] = lim
                    break
            d['effective_limit'] = d['current_slot_limit'] + d['temp_boost']
            # 冷却
            if d['cooldown_minutes'] > 0 and latest_end:
                try:
                    last_dt = datetime.datetime.strptime(latest_end, "%Y-%m-%d %H:%M:%S")
                    elapsed = (now - last_dt).total_seconds() / 60.0
                    if elapsed < d['cooldown_minutes']:
                        d['in_cooldown'] = True
                        d['remaining_cooldown'] = int(d['cooldown_minutes'] - elapsed)
                except Exception:
                    pass

        if card:
            d['card_count'] = int(card['cnt'])

        sy_total = int(sy['time_s']) if sy and sy.get('time_s') is not None else 0
        daily_tt = d.get('daily_total_time', 0)
        if daily_tt > 0:
            d['exchange_remaining'] = sy_total if d['today_used'] >= daily_tt else daily_tt - d['today_used'] + sy_total
        else:
            d['exchange_remaining'] = sy_total

        ex_mins = int(ex['minutes']) if ex and ex.get('minutes') else 0
        d['unused_today'] = max(0, ex_mins - latest_dur)

        task_list = []
        for t in (tasks or []):
            target = int(t.get('target_count') or 1)
            mode_id = int(t.get('mode_id') or 0)
            # 从user__play_game_history按mode_id(=difficulty_type)取今日正确数（与桌面版一致）
            progress = progress_map.get(mode_id, 0)
            task_list.append({
                'name': t.get('name', ''),
                'progress': progress,
                'target': target,
                'completed': progress >= target,
                'reward': f"{t.get('reward_type','')} {t.get('reward_value',0)}",
            })
        d['tasks'] = task_list

        # 写入缓存
        _home_cache[cache_key] = (time.time(), d)
        return d

    # ================================================================
    # 记录分页加载
    # ================================================================
    def _load_more_records(self, e=None):
        if self._records_all_loaded or self.selected_user_id is None:
            return
        uid = self.selected_user_id
        try:
            rows = self.db.fetch_all(
                "SELECT start_time, end_time, "
                "ROUND((julianday(end_time)-julianday(start_time))*24*60) as dur "
                "FROM time_jilu WHERE user_id=? AND end_time IS NOT NULL "
                "ORDER BY end_time DESC LIMIT ? OFFSET ?",
                [uid, self._RECORDS_PAGE_SIZE, self._records_offset])
            if not rows:
                self._records_all_loaded = True
                if self._load_more_btn_ref:
                    self._load_more_btn_ref.visible = False
                    self._load_more_btn_ref.update()
                return
            new_recs = [
                {'start': r['start_time'], 'end': r['end_time'],
                 'minutes': int(r['dur'] or 0)}
                for r in rows
            ]
            self._data['records'].extend(new_recs)
            self._records_offset += len(new_recs)
            if len(new_recs) < self._RECORDS_PAGE_SIZE:
                self._records_all_loaded = True

            # 追加到UI
            if self._records_col_ref:
                for r in new_recs:
                    self._records_col_ref.controls.append(self._record_row(r))
                if self._records_all_loaded and self._load_more_btn_ref:
                    self._load_more_btn_ref.visible = False
                self._records_col_ref.update()
                if self._load_more_btn_ref:
                    self._load_more_btn_ref.update()
        except Exception as ex:
            print(f"[home] 加载更多记录: {ex}")

    def _record_row(self, r):
        try:
            st = datetime.datetime.strptime(r['start'], "%Y-%m-%d %H:%M:%S")
            et = datetime.datetime.strptime(r['end'], "%Y-%m-%d %H:%M:%S")
            date_str = f"{st.year} {st.strftime('%m-%d')} {st.strftime('%H:%M')}-{et.strftime('%H:%M')}"
        except Exception:
            date_str = str(r.get('start', ''))
        return ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.COMPUTER, size=16, color=ft.Colors.BLUE_400),
                ft.Text(date_str, size=12, color=ft.Colors.GREY_700, expand=True),
                ft.Text(f"{r['minutes']}分钟", size=13,
                        color=ft.Colors.BLUE_700, weight=ft.FontWeight.W_600),
            ], spacing=8),
            padding=ft.padding.symmetric(vertical=5))

    # ================================================================
    # UI 构建
    # ================================================================
    def _build_ui(self):
        d = self._data or self._default_data()
        controls = []

        # ---------- 标题栏（与其他标签页统一） ----------
        title_icon = ft.Container(
            width=38, height=38, border_radius=10,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                colors=[ft.Colors.BLUE_400, ft.Colors.PURPLE_500]),
            content=ft.Icon(ft.Icons.HOME, size=20, color=ft.Colors.WHITE),
            alignment=ft.alignment.center,
        )
        title_bar = ft.Container(
            content=ft.Row([
                title_icon,
                ft.Column([
                    ft.Text("时间统计", size=18, weight=ft.FontWeight.BOLD, color="white", no_wrap=True),
                    ft.Text(f"{d['username']} · 今日数据", size=10,
                        color=ft.Colors.with_opacity(0.85, ft.Colors.WHITE), no_wrap=True),
                ], spacing=0, tight=True),
                ft.Container(expand=True),
                ft.IconButton(ft.Icons.REFRESH, icon_size=20, icon_color=ft.Colors.WHITE,
                              on_click=self._on_refresh, tooltip="刷新"),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
            gradient=ft.LinearGradient(
                begin=ft.alignment.center_left, end=ft.alignment.center_right,
                colors=[ft.Colors.BLUE_400, ft.Colors.BLUE_600, ft.Colors.PURPLE_600]),
            border_radius=14,
            shadow=ft.BoxShadow(blur_radius=10, color="#20000000", offset=ft.Offset(0, 3)),
        )
        controls.append(title_bar)
        controls.append(ft.Container(height=8))

        # ---------- 用户选择（admin，靠左） ----------
        if self.is_admin:
            self._user_name_ref = ft.Text(
                f"用户：{self._get_selected_user_name()}", size=13,
                color=ft.Colors.BLUE_800, weight=ft.FontWeight.W_600, no_wrap=True)
            user_btn = ft.Container(
                padding=ft.padding.symmetric(horizontal=12, vertical=6),
                bgcolor=ft.Colors.WHITE, border_radius=24,
                shadow=ft.BoxShadow(blur_radius=8, color="#15000000", offset=ft.Offset(0, 1)),
                on_click=self._open_user_sheet,
                content=ft.Row([
                    ft.Container(width=24, height=24, border_radius=12,
                                 gradient=ft.LinearGradient(
                                     begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                                     colors=[ft.Colors.BLUE_400, ft.Colors.PURPLE_400]),
                                 content=ft.Icon(ft.Icons.PERSON, size=13, color=ft.Colors.WHITE),
                                 alignment=ft.alignment.center),
                    self._user_name_ref,
                    ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=16, color=ft.Colors.PURPLE_400),
                ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
            )
            controls.append(ft.Row([user_btn], alignment=ft.MainAxisAlignment.START))
            controls.append(ft.Container(height=6))

        # 账户信息卡
        avatar = ft.Container(
            width=52, height=52, border_radius=26,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                colors=[ft.Colors.BLUE_500, ft.Colors.PURPLE_500]),
            content=ft.Text(d['username'][0], size=22, color=ft.Colors.WHITE,
                            weight=ft.FontWeight.BOLD),
            alignment=ft.alignment.center,
            shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.BLUE_300, spread_radius=1))
        account_card = ft.Container(
            padding=16, bgcolor=ft.Colors.WHITE, border_radius=16,
            shadow=ft.BoxShadow(blur_radius=12, color="#15000000", offset=ft.Offset(0, 2)),
            content=ft.Row([
                avatar,
                ft.Column([
                    ft.Text(d['username'], size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                    ft.Row([
                        ft.Icon(ft.Icons.STAR, size=14, color=ft.Colors.AMBER_500),
                        ft.Text(f"Lv.{d['level']}  {d['stars']}星  {d['score']}分",
                                size=12, color=ft.Colors.GREY_600),
                    ], spacing=4),
                ], spacing=4, expand=True),
            ], spacing=14))
        controls.append(account_card)

        # ---------- 时长统计卡（小时）----------
        def _to_hours(mins):
            return f"{mins / 60:.1f}h"
        stats = [
            ("总时长", _to_hours(d['total_duration']), ft.Colors.BLUE_600),
            ("今年", _to_hours(d['year_total']), ft.Colors.PURPLE_600),
            ("本月", _to_hours(d['month_total']), ft.Colors.TEAL_600),
            ("本周", _to_hours(d['week_total']), ft.Colors.ORANGE_600),
        ]
        stat_cards = ft.Row([
            ft.Container(
                content=ft.Column([
                    ft.Text(val, size=16, weight=ft.FontWeight.BOLD, color=color),
                    ft.Text(label, size=10, color=ft.Colors.GREY_500),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
                expand=True, padding=ft.padding.symmetric(vertical=10),
                bgcolor=ft.Colors.WHITE, border_radius=12,
                shadow=ft.BoxShadow(blur_radius=6, color="#10000000"))
            for label, val, color in stats
        ], spacing=8)
        controls.append(stat_cards)

        # ---------- 今日使用 + 冷却 ----------
        used_pct = (d['today_used'] / d['daily_limit'] * 100) if d['daily_limit'] > 0 else 0
        used_pct = min(used_pct, 100)
        bar_color = ft.Colors.GREEN_500 if used_pct < 60 else (ft.Colors.ORANGE_500 if used_pct < 90 else ft.Colors.RED_500)

        if d['in_cooldown']:
            cd_text = f"冷却中 {d['remaining_cooldown']}分钟"
            cd_color = ft.Colors.RED_600
            cd_icon = ft.Icons.HOURGLASS_TOP
        else:
            cd_text = "可使用"
            cd_color = ft.Colors.GREEN_600
            cd_icon = ft.Icons.CHECK_CIRCLE

        time_card = ft.Container(
            padding=16, bgcolor=ft.Colors.WHITE, border_radius=16,
            shadow=ft.BoxShadow(blur_radius=12, color="#15000000", offset=ft.Offset(0, 2)),
            content=ft.Column([
                ft.Row([
                    ft.Column([
                        ft.Text("今日已使用", size=12, color=ft.Colors.GREY_500),
                        ft.Text(f"{d['today_used']} / {d['daily_limit']} 分钟",
                                size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800),
                    ], spacing=2, expand=True),
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(cd_icon, size=18, color=cd_color),
                            ft.Text(cd_text, size=11, color=cd_color, weight=ft.FontWeight.W_600),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
                        padding=8, bgcolor=ft.Colors.with_opacity(0.1, cd_color),
                        border_radius=10),
                ], spacing=8),
                ft.Container(height=6),
                ft.Stack([
                    ft.Container(width=300, height=10, bgcolor=ft.Colors.GREY_200, border_radius=5),
                    ft.Container(width=max(2, int(300 * used_pct / 100)), height=10,
                                 bgcolor=bar_color, border_radius=5),
                ]),
                ft.Text(f"使用率 {used_pct:.1f}%", size=11, color=ft.Colors.GREY_500),
                ft.Divider(height=10, color=ft.Colors.GREY_200),
                ft.Row([
                    ft.Column([
                        ft.Text("使用未完成", size=11, color=ft.Colors.GREY_500),
                        ft.Text(f"{d['unused_today']} 分钟", size=15,
                                weight=ft.FontWeight.BOLD, color=ft.Colors.TEAL_600),
                    ], spacing=2, expand=True,
                       horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(width=1, bgcolor=ft.Colors.GREY_200, height=36),
                    ft.Column([
                        ft.Text("兑换剩余", size=11, color=ft.Colors.GREY_500),
                        ft.Text(f"{d['exchange_remaining']} 分钟", size=15,
                                weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER_600),
                    ], spacing=2, expand=True,
                       horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ], spacing=8),
            ], spacing=4))
        controls.append(time_card)

        # ---------- 时段限制 ----------
        if d['slots']:
            slot_rows = []
            cur_hm = datetime.datetime.now().strftime("%H:%M")
            for s, e, lim in d['slots']:
                is_current = (s <= cur_hm <= e) or (s > e and (cur_hm >= s or cur_hm <= e))
                slot_rows.append(ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.SCHEDULE, size=16,
                                color=ft.Colors.BLUE_600 if is_current else ft.Colors.GREY_400),
                        ft.Text(f"{s} - {e}", size=13,
                                color=ft.Colors.BLUE_800 if is_current else ft.Colors.GREY_700,
                                weight=ft.FontWeight.W_600 if is_current else ft.FontWeight.NORMAL),
                        ft.Container(expand=True),
                        ft.Text(f"{lim}分钟", size=13,
                                color=ft.Colors.BLUE_700 if is_current else ft.Colors.GREY_600,
                                weight=ft.FontWeight.W_600),
                    ], spacing=8),
                    padding=ft.padding.symmetric(vertical=6, horizontal=10),
                    bgcolor=ft.Colors.BLUE_50 if is_current else ft.Colors.TRANSPARENT,
                    border_radius=8,
                ))
            slot_card = ft.Container(
                padding=14, bgcolor=ft.Colors.WHITE, border_radius=16,
                shadow=ft.BoxShadow(blur_radius=10, color="#12000000"),
                content=ft.Column([
                    ft.Text("时段限制", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800),
                    ft.Divider(height=8, color=ft.Colors.GREY_200),
                ] + slot_rows, spacing=2))
            controls.append(slot_card)

        # ---------- 赋能卡 + 任务 ----------
        card_row = ft.Row([
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.CARD_GIFTCARD, size=22, color=ft.Colors.AMBER_600),
                    ft.Text(str(d['card_count']), size=20, weight=ft.FontWeight.BOLD,
                            color=ft.Colors.AMBER_700),
                    ft.Text("赋能卡", size=10, color=ft.Colors.GREY_500),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                expand=True, padding=12, bgcolor=ft.Colors.WHITE, border_radius=14,
                shadow=ft.BoxShadow(blur_radius=8, color="#1000000")),
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.ASSIGNMENT_TURNED_IN, size=22, color=ft.Colors.GREEN_600),
                    ft.Text(f"{sum(1 for t in d['tasks'] if t['completed'])}/{len(d['tasks'])}",
                            size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700),
                    ft.Text("任务完成", size=10, color=ft.Colors.GREY_500),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                expand=True, padding=12, bgcolor=ft.Colors.WHITE, border_radius=14,
                shadow=ft.BoxShadow(blur_radius=8, color="#1000000")),
        ], spacing=10)
        controls.append(card_row)

        # 任务列表
        if d['tasks']:
            task_rows = []
            for t in d['tasks']:
                pct = min(100, int(t['progress'] / t['target'] * 100)) if t['target'] > 0 else 0
                task_rows.append(ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text(t['name'], size=13, weight=ft.FontWeight.W_600,
                                    color=ft.Colors.GREEN_800 if t['completed'] else ft.Colors.GREY_800),
                            ft.Container(expand=True),
                            ft.Text(f"{t['progress']}/{t['target']}", size=12,
                                    color=ft.Colors.GREEN_600 if t['completed'] else ft.Colors.GREY_500),
                            ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color=ft.Colors.GREEN_500)
                            if t['completed'] else ft.Container(),
                        ], spacing=6),
                        ft.Stack([
                            ft.Container(width=280, height=6, bgcolor=ft.Colors.GREY_200, border_radius=3),
                            ft.Container(width=max(2, int(280 * pct / 100)), height=6,
                                         bgcolor=ft.Colors.GREEN_500 if t['completed'] else ft.Colors.BLUE_400,
                                         border_radius=3),
                        ]),
                    ], spacing=4),
                    padding=ft.padding.symmetric(vertical=6)))
            task_card = ft.Container(
                padding=14, bgcolor=ft.Colors.WHITE, border_radius=16,
                shadow=ft.BoxShadow(blur_radius=10, color="#12000000"),
                content=ft.Column([
                    ft.Text("今日任务", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800),
                    ft.Divider(height=8, color=ft.Colors.GREY_200),
                ] + task_rows, spacing=2))
            controls.append(task_card)

        # ---------- 最近使用记录 ----------
        if d['records']:
            rec_rows = [self._record_row(r) for r in d['records']]
            self._records_col_ref = ft.Column(controls=rec_rows, spacing=0)

            # 查看更多按钮
            self._load_more_btn_ref = ft.Container(
                content=ft.Text("查看更多", size=12, color=ft.Colors.BLUE_600,
                                weight=ft.FontWeight.W_600),
                padding=ft.padding.symmetric(vertical=8),
                alignment=ft.alignment.center,
                on_click=self._load_more_records,
                visible=not self._records_all_loaded,
            )

            rec_card = ft.Container(
                padding=14, bgcolor=ft.Colors.WHITE, border_radius=16,
                shadow=ft.BoxShadow(blur_radius=10, color="#12000000"),
                content=ft.Column([
                    ft.Text("最近使用记录", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800),
                    ft.Divider(height=8, color=ft.Colors.GREY_200),
                    self._records_col_ref,
                    self._load_more_btn_ref,
                ], spacing=0))
            controls.append(rec_card)

        controls.append(ft.Text("© 2025 单词学习", size=9,
                                color=ft.Colors.GREY_400, text_align=ft.TextAlign.CENTER))

        self._content.controls = controls

    def build(self):
        if self._data is not None and not self._content.controls:
            self._build_ui()
        return ft.Container(
            content=self._content, expand=True, padding=16,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                colors=[ft.Colors.BLUE_50, ft.Colors.INDIGO_50,
                        ft.Colors.PURPLE_50, ft.Colors.PINK_50]))
