# pages/admin/base.py
import asyncio
import flet as ft
from .reward_service import RewardService


class _SilentLoading:
    """管理标签页专用：不触发全局遮罩，避免干扰首页/英语页的loading。"""
    def show(self, msg=""):
        pass
    def hide(self):
        pass


class AdminBaseTab:
    """管理模块基类：提供数据库访问、通用控件、loading、snack、操作日志"""

    _log_table_created = False

    def __init__(self, page: ft.Page):
        self.page = page
        self.db = page._db          # 云端 TursoClient
        self.loading = _SilentLoading()
        self._reward_svc = None
        self._ensure_log_table()

    def _ensure_log_table(self):
        """确保管理员操作日志表存在（只执行一次）"""
        if AdminBaseTab._log_table_created:
            return
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS admin_operation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    admin_name TEXT,
                    operation_type TEXT,
                    target_type TEXT,
                    target_id TEXT,
                    target_name TEXT,
                    details TEXT,
                    before_state TEXT,
                    after_state TEXT,
                    operation_time TEXT DEFAULT (datetime('now','localtime'))
                )
            """)
            # 兼容旧表：添加新列（已存在则忽略）
            for col in ['before_state TEXT', 'after_state TEXT']:
                try:
                    self.db.execute(f"ALTER TABLE admin_operation_logs ADD COLUMN {col}")
                except Exception:
                    pass
            AdminBaseTab._log_table_created = True
        except Exception as e:
            print(f"[admin_log] create table fail: {e}")

    def _log_operation(self, operation_type, target_type, target_id="", target_name="",
                       details="", before_state=None, after_state=None):
        """记录管理员操作日志（异步非阻塞，失败不影响主流程）
        before_state/after_state: dict 或 JSON字符串，记录修改前后状态"""
        self._ensure_log_table()
        import datetime, json
        admin_id = getattr(self.page, '_user_data', {}).get('user_id', 0)
        admin_name = getattr(self.page, '_user_data', {}).get('username', 'unknown')
        # 用北京时间（UTC+8），避免云端SQLite默认UTC慢8小时
        now = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')

        def _to_json(obj):
            if obj is None:
                return None
            if isinstance(obj, str):
                return obj[:1000]
            try:
                return json.dumps(obj, ensure_ascii=False, default=str)[:1000]
            except Exception:
                return str(obj)[:1000]

        before_json = _to_json(before_state)
        after_json = _to_json(after_state)
        params = [admin_id, admin_name, operation_type, target_type, str(target_id),
                  str(target_name)[:100], str(details)[:500], before_json, after_json, now]

        async def _do_log():
            try:
                self.db.execute(
                    "INSERT INTO admin_operation_logs (admin_id, admin_name, operation_type, target_type, target_id, target_name, details, before_state, after_state, operation_time) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    params)
            except Exception as e:
                print(f"[admin_log] insert fail: {e}")

        try:
            self.page.run_task(_do_log)
        except Exception:
            # run_task 不可用时同步执行
            try:
                self.db.execute(
                    "INSERT INTO admin_operation_logs (admin_id, admin_name, operation_type, target_type, target_id, target_name, details, before_state, after_state, operation_time) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    params)
            except Exception as e:
                print(f"[admin_log] insert fail (sync): {e}")

    @property
    def reward_svc(self):
        if self._reward_svc is None:
            self._reward_svc = RewardService(self.db)
        return self._reward_svc

    # ---------- 统一刷新 ----------
    def _refresh_button(self):
        """紧凑刷新按钮，管理模块统一使用"""
        return ft.IconButton(
            icon=ft.Icons.REFRESH,
            icon_size=18,
            tooltip="刷新数据",
            icon_color=ft.Colors.BLUE_600,
            on_click=self._on_refresh,
            style=ft.ButtonStyle(padding=ft.padding.all(8)),
        )

    def _refresh_header(self, title=""):
        """统一页面顶部栏：标题 + 刷新按钮"""
        return ft.Container(
            content=ft.Row([
                ft.Text(title, size=13, weight=ft.FontWeight.BOLD,
                        color=ft.Colors.GREY_700, expand=True),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.REFRESH, size=16, color=ft.Colors.WHITE),
                        ft.Text("刷新", size=12, color=ft.Colors.WHITE),
                    ], spacing=4),
                    bgcolor=ft.Colors.BLUE_600,
                    border_radius=6,
                    padding=ft.padding.symmetric(horizontal=10, vertical=5),
                    on_click=self._on_refresh,
                    ink=True,
                ),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            height=38,
            padding=ft.padding.symmetric(horizontal=2),
        )

    def _show_refresh_loading(self, msg="刷新中..."):
        """显示刷新加载动画（模态遮罩）"""
        if not hasattr(self, '_refresh_dlg') or self._refresh_dlg is None:
            self._refresh_dlg = ft.AlertDialog(
                modal=True,
                content=ft.Column([
                    ft.ProgressRing(width=32, height=32, color=ft.Colors.BLUE_500, stroke_width=3),
                    ft.Text(msg, size=13, color=ft.Colors.GREY_600),
                ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            )
        try:
            self.page.open(self._refresh_dlg)
        except Exception:
            pass

    def _hide_refresh_loading(self):
        """隐藏刷新加载动画"""
        dlg = getattr(self, '_refresh_dlg', None)
        if dlg is not None:
            try:
                self.page.close(dlg)
            except Exception:
                pass

    def _on_refresh(self, e=None):
        """统一刷新入口：显示加载动画 → 调用 load_data → 关闭动画"""
        async def _do():
            self._show_refresh_loading()
            try:
                await self.load_data()
                self.snack("刷新完成")
            except Exception as ex:
                self.snack(f"刷新失败: {ex}")
            finally:
                self._hide_refresh_loading()
        self.page.run_task(_do)

    # ---------- 通用控件 ----------
    def _search_bar(self, label, hint, on_search, width=None):
        """移动端紧凑搜索栏：hint_text替代label，减少垂直高度"""
        tf = ft.TextField(
            hint_text=hint,
            prefix_icon=ft.Icons.SEARCH,
            expand=True, height=34,
            border_radius=8,
            text_size=13,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=0),
            dense=True,
        )
        self._search_loading = ft.ProgressRing(width=18, height=18, color=ft.Colors.BLUE_500, visible=False, stroke_width=2)
        btn = ft.IconButton(
            icon=ft.Icons.SEARCH,
            icon_size=18,
            tooltip="查询",
            on_click=lambda e: on_search(tf.value),
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.padding.all(6),
            ),
        )
        self._search_btn = btn
        row = ft.Row([tf, self._search_loading, btn], spacing=6,
                     vertical_alignment=ft.CrossAxisAlignment.CENTER,
                     height=40)
        if width:
            row.width = width
        return row, tf

    def _search_loading_show(self, show=True):
        ring = getattr(self, '_search_loading', None)
        btn = getattr(self, '_search_btn', None)
        if ring is not None:
            ring.visible = show
            try:
                if ring.page is not None:
                    ring.update()
            except Exception:
                pass
        if btn is not None:
            btn.disabled = show
            try:
                if btn.page is not None:
                    btn.update()
            except Exception:
                pass

    def _action_button(self, text, icon, on_click, color=ft.Colors.BLUE_600):
        return ft.ElevatedButton(
            text, icon=icon, on_click=on_click,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                bgcolor=color, color=ft.Colors.WHITE, elevation=2,
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
            ),
        )

    def _icon_button(self, icon, on_click, color=ft.Colors.BLUE_600, tooltip=""):
        return ft.IconButton(icon, icon_size=22, icon_color=color,
                             on_click=on_click, tooltip=tooltip,
                             style=ft.ButtonStyle(padding=ft.padding.all(10)))

    async def load_data(self):
        """初始数据加载，由 __init__ 在显示前 await。子类重写。"""
        pass

    def _card(self, content, padding=12):
        return ft.Container(
            content=content, padding=padding,
            bgcolor=ft.Colors.WHITE, border_radius=12,
            shadow=ft.BoxShadow(blur_radius=8, color="#10000000", offset=ft.Offset(0, 2)),
        )

    def _list_tile(self, leading, title, subtitle=None, trailing=None, on_click=None, bgcolor=None, leading_width=32):
        """紧凑列表行：自定义Row，比ListTile省空间"""
        row = ft.Row(
            controls=[
                ft.Container(width=leading_width, alignment=ft.alignment.center, content=leading)
                if leading else ft.Container(width=4),
                ft.Column([
                    title,
                    subtitle if subtitle else ft.Container(),
                ], spacing=1, expand=True, tight=True),
                trailing if trailing else ft.Container(),
            ],
            spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return ft.Container(
            content=row,
            padding=ft.padding.symmetric(horizontal=8, vertical=5),
            bgcolor=bgcolor if bgcolor else ft.Colors.WHITE,
            border_radius=6,
            margin=ft.margin.only(bottom=2),
            on_click=on_click,
            ink=True,
        )

    def _card_tile(self, row1, row2=None, row3=None, on_click=None, bgcolor=None):
        """三行卡片：row1标题行, row2详情行, row3底部信息行"""
        children = [row1]
        if row2:
            children.append(row2)
        if row3:
            children.append(row3)
        return ft.Container(
            content=ft.Column(children, spacing=2, tight=True),
            padding=ft.padding.symmetric(horizontal=10, vertical=7),
            bgcolor=bgcolor if bgcolor else ft.Colors.WHITE,
            border_radius=8,
            margin=ft.margin.only(bottom=3),
            on_click=on_click,
            ink=True,
        )

    def _loading_view(self, text="加载中..."):
        return ft.Container(
            content=ft.Column([
                ft.ProgressRing(width=32, height=32, color=ft.Colors.BLUE_400),
                ft.Text(text, size=12, color=ft.Colors.GREY_500),
            ], alignment=ft.MainAxisAlignment.CENTER,
               horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            expand=True, alignment=ft.alignment.center, padding=30,
        )

    def _empty(self, text="暂无数据"):
        return ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.INBOX, size=32, color=ft.Colors.GREY_400),
                ft.Text(text, size=12, color=ft.Colors.GREY_500),
            ], alignment=ft.MainAxisAlignment.CENTER,
               horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
            expand=True, alignment=ft.alignment.center, padding=20,
        )

    # ---------- 反馈 ----------
    def _close_dialog(self, dlg):
        """统一关闭弹窗：page.close + update"""
        try:
            dlg.open = False
        except Exception:
            pass
        try:
            self.page.close(dlg)
        except Exception:
            pass
        try:
            self.page.update()
        except Exception:
            pass

    def snack(self, msg):
        sb = ft.SnackBar(content=ft.Text(msg), duration=2000)
        try:
            self.page.open(sb)
        except AttributeError:
            self.page.snack_bar = sb
            sb.open = True
            self.page.update()

    def confirm_dialog(self, title, content, on_confirm):
        def yes(e):
            self._close_dialog(dlg)
            on_confirm()
        def no(e):
            self._close_dialog(dlg)
        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Text(content),
            actions=[
                ft.TextButton("取消", on_click=no),
                ft.TextButton("确认", on_click=yes),
            ],
        )
        self.page.open(dlg)

    def confirm_and_run(self, title, content, coro_fn, *args,
                        success_msg="操作成功", loading_msg="处理中..."):
        """确认对话框 → loading → 异步执行 → 结果提示。coro_fn 是协程函数引用。"""
        def on_confirm():
            loading = ft.AlertDialog(
                content=ft.Column([
                    ft.ProgressRing(width=32, height=32, color=ft.Colors.BLUE_400),
                    ft.Text(loading_msg, size=13, color=ft.Colors.GREY_600),
                ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                modal=True,
            )
            self.page.open(loading)

            async def do_work():
                try:
                    await coro_fn(*args)
                    self._close_dialog(loading)
                    self.snack(success_msg)
                except Exception as e:
                    self._close_dialog(loading)
                    self.snack(f"操作失败: {e}")

            self.page.run_task(do_work)

        self.confirm_dialog(title, content, on_confirm)

    def form_dialog(self, title, fields, on_submit, submit_text="保存",
                    need_confirm=True, confirm_msg="确定要保存修改吗？"):
        """通用表单对话框。fields = [(label, key, initial_value, type), ...]
        type: 'text'|'number'|'dropdown'(options) | 'textarea'
        need_confirm: 保存前是否二次确认（默认True）
        保存时自动显示加载动画，异步执行不阻塞UI。"""
        refs = {}
        controls = []
        for label, key, initial, ftype in fields:
            if ftype == 'textarea':
                tf = ft.TextField(label=label, value=str(initial or ''),
                                  multiline=True, min_lines=2, max_lines=4,
                                  border_radius=8, expand=True)
            elif isinstance(ftype, (list, tuple)):
                tf = ft.Dropdown(
                    label=label, value=str(initial) if initial is not None else None,
                    options=[ft.dropdown.Option(str(o)) for o in ftype],
                    border_radius=8, expand=True)
            elif ftype == 'number':
                tf = ft.TextField(label=label, value=str(initial or ''),
                                  keyboard_type=ft.KeyboardType.NUMBER,
                                  border_radius=8, expand=True)
            else:
                tf = ft.TextField(label=label, value=str(initial or ''),
                                  border_radius=8, expand=True)
            refs[key] = tf
            controls.append(tf)

        def do_submit(e):
            data = {}
            for key, ctrl in refs.items():
                data[key] = ctrl.value
            self._close_dialog(dlg)

            def run_save():
                loading = ft.AlertDialog(
                    content=ft.Column([
                        ft.ProgressRing(width=32, height=32, color=ft.Colors.BLUE_400),
                        ft.Text("保存中...", size=13, color=ft.Colors.GREY_600),
                    ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                    modal=True,
                )
                self.page.open(loading)

                async def work():
                    try:
                        await asyncio.to_thread(on_submit, data)
                        self._close_dialog(loading)
                        self.snack("保存成功")
                    except Exception as ex:
                        self._close_dialog(loading)
                        self.snack(f"保存失败: {ex}")

                self.page.run_task(work)

            if need_confirm:
                self.confirm_dialog("确认保存", confirm_msg, run_save)
            else:
                run_save()

        # 响应式宽度：小屏手机留边距，大屏最大400
        page_w = getattr(self.page, 'width', 400) or 400
        dlg_w = min(400, max(280, int(page_w) - 40))
        dlg = ft.AlertDialog(
            title=ft.Text(title, size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=ft.Column(controls, spacing=10, scroll=ft.ScrollMode.ADAPTIVE),
                                 width=dlg_w, padding=4),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self._close_dialog(dlg)),
                ft.ElevatedButton(submit_text, on_click=do_submit,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE)),
            ],
        )
        self.page.open(dlg)
        return refs

    def run_save_async(self, save_fn, success_msg="保存成功", loading_msg="保存中...",
                       need_confirm=True, confirm_msg="确定要保存修改吗？", after_fn=None):
        """通用保存：二次确认 + 加载动画 + 异步执行 + 结果提示。
        save_fn: 无参数的保存函数（同步函数，内部用asyncio.to_thread执行）
        after_fn: 保存成功后执行的回调（如刷新列表），可选"""
        def do_run():
            loading = ft.AlertDialog(
                content=ft.Column([
                    ft.ProgressRing(width=32, height=32, color=ft.Colors.BLUE_400),
                    ft.Text(loading_msg, size=13, color=ft.Colors.GREY_600),
                ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                modal=True,
            )
            self.page.open(loading)

            async def work():
                try:
                    await asyncio.to_thread(save_fn)
                    self._close_dialog(loading)
                    self.snack(success_msg)
                    if after_fn:
                        try:
                            after_fn()
                        except Exception:
                            pass
                except Exception as ex:
                    self._close_dialog(loading)
                    self.snack(f"保存失败: {ex}")

            self.page.run_task(work)

        if need_confirm:
            self.confirm_dialog("确认保存", confirm_msg, do_run)
        else:
            do_run()

    def build(self):
        """子类实现"""
        return ft.Text("未实现")

    # ---------- 品质颜色映射 ----------
    QUALITY_COLORS = {
        "普通": "#9E9E9E", "优秀": "#4CAF50", "稀有": "#2196F3",
        "史诗": "#9C27B0", "传说": "#FF9800", "神器": "#F44336",
        "高级": "#8BC34A", "神秘": "#D32F2F", "传奇": "#FFC107",
    }

    @staticmethod
    def _hex_bg(hex_color, opacity=0.08):
        """hex颜色(#RRGGBB)转rgba透明色，用于行背景"""
        h = (hex_color or "#9E9E9E").lstrip('#')
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{opacity})"

    def _quality_chip(self, quality):
        """品质彩色标签"""
        q = quality or "普通"
        color = self.QUALITY_COLORS.get(q, "#9E9E9E")
        return ft.Container(
            content=ft.Text(q, size=9, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            bgcolor=color, border_radius=4,
            padding=ft.padding.symmetric(horizontal=5, vertical=1),
        )

    def _status_chip(self, enabled, on_text="启用", off_text="禁用"):
        """启用/禁用状态彩色标签"""
        if enabled:
            return ft.Container(
                content=ft.Text(on_text, size=9, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                bgcolor=ft.Colors.GREEN_600, border_radius=4,
                padding=ft.padding.symmetric(horizontal=5, vertical=1),
            )
        return ft.Container(
            content=ft.Text(off_text, size=9, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.GREY_500, border_radius=4,
            padding=ft.padding.symmetric(horizontal=5, vertical=1),
        )

    def _onoff_chip(self, val, on_text="上架", off_text="下架"):
        """上架/下架状态标签（val=1/0 或 True/False）"""
        try:
            on = int(val) == 1 or val is True
        except (ValueError, TypeError):
            on = False
        return self._status_chip(on, on_text, off_text)
