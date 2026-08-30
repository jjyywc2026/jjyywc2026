import flet as ft
import os
import threading
import datetime
import time

# ===== 文件日志（统一路径，与my.py日志查看器一致） =====
_LOG_FILE = None
_LOG_FH = None  # 持久文件句柄，避免每次open/close
def _find_log_dir():
    try:
        from app_paths import get_log_dir
        return str(get_log_dir())
    except Exception:
        # 兜底：与get_log_dir相同的逻辑
        candidates = []
        ext = os.environ.get("EXTERNAL_STORAGE") or "/sdcard"
        candidates.append(os.path.join(ext, "Android/data/com.wordlearning/files"))
        candidates.append(os.path.join(ext, "Android/data/com.wordlearning/cache"))
        flet_dir = os.environ.get("FLET_APP_STORAGE_DIR")
        if flet_dir:
            candidates.append(flet_dir)
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
        for d in candidates:
            try:
                os.makedirs(d, exist_ok=True)
                test = os.path.join(d, ".write_test")
                with open(test, "w") as f:
                    f.write("ok")
                os.remove(test)
                return d
            except Exception:
                continue
        return candidates[-1]

def _flog(msg):
    global _LOG_FILE, _LOG_FH
    try:
        if _LOG_FILE is None:
            _LOG_FILE = os.path.join(_find_log_dir(), "startup_log.txt")
        if _LOG_FH is None:
            _LOG_FH = open(_LOG_FILE, "a", encoding="utf-8", buffering=1)  # 行缓冲
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        _LOG_FH.write(f"[{ts}] {msg}\n")
        _LOG_FH.flush()
    except Exception:
        pass

# 模块加载即写第一条日志（证明 Python 进程启动成功）
_flog("=== main.py 模块加载成功 ===")
_flog(f"FLET_APP_STORAGE_DIR={os.environ.get('FLET_APP_STORAGE_DIR')}")
_flog(f"EXTERNAL_STORAGE={os.environ.get('EXTERNAL_STORAGE')}")
_flog(f"日志文件路径: {_LOG_FILE}")

# ===== 所有重量级 import 用 try/except 包裹，失败也能写日志 =====
_import_errors = []
try:
    from ui_components import LoadingOverlay
    _flog("import ui_components OK")
except Exception as e:
    _import_errors.append(f"ui_components: {e}")
    _flog(f"import ui_components FAIL: {e}")

try:
    from pages.login import LoginPage
    _flog("import pages.login OK")
except Exception as e:
    _import_errors.append(f"pages.login: {e}")
    _flog(f"import pages.login FAIL: {e}")

# 以下模块登录后才需要，改为懒加载（在MainLayout中import），加快启动速度
# from pages.english import EnglishPage
# from pages.my import MyPage
# from pages.admin import AdminPage
# from pages.home import HomePage
# from pages.cihai import CihaiPage
# from pages.guoxue import GuoxuePage

try:
    from database import TursoClient
    _flog("import database OK")
except Exception as e:
    _import_errors.append(f"database: {e}")
    _flog(f"import database FAIL: {e}")

try:
    from sync_http import LocalSQLiteDB
    _flog("import sync_http OK")
except Exception as e:
    _import_errors.append(f"sync_http: {e}")
    _flog(f"import sync_http FAIL: {e}")

_flog(f"=== 所有 import 完成，失败 {len(_import_errors)} 个 ===")

class MainLayout:
    def __init__(self, page: ft.Page, user_data: dict):
        self.page = page
        self.user_data = user_data

        if 'home_filter' not in user_data:
            user_data['home_filter'] = {
                'selected_user_id': user_data.get('id'),
                'selected_grade': '全部'
            }

        # 懒加载页面模块（登录后才import，加快启动速度）
        from pages.home import HomePage
        from pages.english import EnglishPage
        from pages.cihai import CihaiPage
        from pages.guoxue import GuoxuePage
        from pages.my import MyPage
        _flog("[MainLayout] 页面模块懒加载完成")

        # 所有页面类实例
        self.pages = {
            0: HomePage(page, user_data),
            1: EnglishPage(page, user_data, filter_state=user_data['home_filter']),
            2: CihaiPage(page),
            3: GuoxuePage(page),
            4: MyPage(page, user_data),
        }
        # 全局用户ID（用于跨页面用户下拉联动）
        page.selected_user_id = user_data.get('id')

        destinations = [
            ft.NavigationBarDestination(icon=ft.Icons.HOME, label="首页"),
            ft.NavigationBarDestination(icon=ft.Icons.LANGUAGE, label="英语"),
            ft.NavigationBarDestination(icon=ft.Icons.MENU_BOOK, label="辞海"),
            ft.NavigationBarDestination(icon=ft.Icons.LOCAL_LIBRARY, label="国学"),  # 修改为 LOCAL_LIBRARY
            ft.NavigationBarDestination(icon=ft.Icons.PERSON, label="我的"),
        ]

        if user_data.get('type') == "admin":
            from pages.admin import AdminPage
            self.pages[5] = AdminPage(page)
            destinations.append(
                ft.NavigationBarDestination(icon=ft.Icons.ADMIN_PANEL_SETTINGS, label="管理")
            )

        self.nav_bar = ft.NavigationBar(
            selected_index=0,
            destinations=destinations,
            on_change=self.on_nav_change,
        )

        # 用Container交换content(避免Android上controls.clear()+append()不刷新的bug)
        self.content_area = ft.Container(expand=True, content=self.pages[0].build(), padding=0, margin=0)
        self._build_cache = {0: self.content_area.content}  # 缓存已构建页面，避免切换重建

        self.container = ft.Column(
            expand=True,
            controls=[
                self.content_area,
                self.nav_bar,
            ]
        )

    def on_nav_change(self, e):
        idx = e.control.selected_index
        page_obj = self.pages[idx]

        # 全局用户联动：同步全局用户ID到目标页面（None=全部用户，也要同步）
        global_uid = getattr(self.page, 'selected_user_id', None)
        if hasattr(page_obj, 'selected_user_id'):
            uid_changed = page_obj.selected_user_id != global_uid
            page_obj.selected_user_id = global_uid
        else:
            uid_changed = False

        # 已缓存页面：直接交换content，用户变化时触发刷新
        if idx in self._build_cache:
            self.content_area.content = self._build_cache[idx]
            self.page.update()
            if uid_changed:
                # 用户变化：调用页面自身的_on_user_changed（清缓存+Timer延迟run_task）
                if hasattr(page_obj, '_on_user_changed'):
                    page_obj._on_user_changed(global_uid)
                    self.page.update()
                elif hasattr(page_obj, '_on_refresh'):
                    page_obj._on_refresh()
                elif hasattr(page_obj, 'load_data'):
                    self.page.run_task(page_obj.load_data)
            return

        # 未缓存：用户ID已同步到page_obj，build()会使用正确的用户
        heavy = idx in (0, 1, 2, 3, 5)
        if heavy and hasattr(self.page, 'loading_overlay'):
            self.page.loading_overlay.show("加载中...")
        built = page_obj.build()
        self._build_cache[idx] = built
        self.content_area.content = built
        self.page.update()
        # 国学/辞海的load_data在build()内部通过page.run_task启动(同英语模式)
        if heavy and hasattr(self.page, 'loading_overlay') and not hasattr(page_obj, 'load_data'):
            def _quick_hide():
                import time
                time.sleep(0.15)
                self.page.loading_overlay.hide()
            threading.Thread(target=_quick_hide, daemon=True).start()

    def build(self):
        return self.container


def init_app_db(page):
    """首次启动：从 assets 复制预置数据库和配置到可写目录（APK assets 只读）"""
    try:
        from app_paths import get_app_dir
        import shutil
        app_dir = get_app_dir()
        assets_dir = getattr(page, 'assets_dir', None)
        if not assets_dir:
            return False
        copied = False
        # 复制数据库
        target = app_dir / "local_cache.db"
        if not target.exists():
            assets_db = os.path.join(assets_dir, "local_cache.db")
            if os.path.exists(assets_db):
                shutil.copy2(assets_db, target)
                print(f"[init] 已从 assets 复制数据库到 {target}")
                copied = True
        # 复制 turso 配置
        target_cfg = app_dir / "turso-config.json"
        if not target_cfg.exists():
            assets_cfg = os.path.join(assets_dir, "turso-config.json")
            if os.path.exists(assets_cfg):
                shutil.copy2(assets_cfg, target_cfg)
                print(f"[init] 已从 assets 复制配置到 {target_cfg}")
                copied = True
        return copied
    except Exception as e:
        print(f"[init] 初始化失败: {e}")
    return False


def main(page: ft.Page):
    _flog("=== main() 被调用 ===")
    # 如果有 import 错误，直接显示在页面上
    if _import_errors:
        _flog(f"存在 {len(_import_errors)} 个 import 错误，显示错误页")
        try:
            page.bgcolor = ft.Colors.WHITE
            page.add(ft.Container(
                content=ft.Column([
                    ft.Text("模块导入失败", size=20, color=ft.Colors.RED, weight=ft.FontWeight.BOLD),
                    ft.Text(f"日志文件: {_LOG_FILE}", size=10, color=ft.Colors.GREY_500),
                    ft.Container(height=10),
                ] + [ft.Text(e, size=12, color=ft.Colors.RED) for e in _import_errors],
                    scroll=ft.ScrollMode.AUTO, spacing=5),
                padding=20, expand=True,
            ))
            page.update()
        except Exception as ex:
            _flog(f"显示 import 错误页失败: {ex}")
        return
    try:
        _flog("设置页面属性...")
        page.title = "单词学习"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.bgcolor = ft.Colors.WHITE
        page.padding = 0

        # ---------- 退出确认弹窗 + 后台10分钟超时 ----------
        _exit_dlg = {"ref": None}
        _exit_dlg_open = {"v": False}  # 弹窗打开时忽略所有窗口事件，防止阻塞
        _blur_time = {"t": None}  # 记录失去焦点时间

        def _show_exit_confirm(e=None):
            if _exit_dlg_open["v"]:
                return
            _exit_dlg_open["v"] = True
            def _do_exit(_=None):
                _exit_dlg_open["v"] = False
                try:
                    page.window.prevent_close = False
                except Exception:
                    pass
                # 先正常关闭窗口（Android上finish Activity）
                try:
                    page.window.close()
                except Exception:
                    pass
                # 兜底：200ms后强制退出，防止window.close无效
                def _force_exit():
                    time.sleep(0.2)
                    os._exit(0)
                threading.Thread(target=_force_exit, daemon=True).start()
            def _cancel(_=None):
                _exit_dlg_open["v"] = False
                try:
                    _exit_dlg["ref"].open = False
                    page.update()
                except Exception:
                    pass
            def _on_dismiss(_=None):
                _exit_dlg_open["v"] = False
            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text("退出应用？", size=16, weight=ft.FontWeight.BOLD),
                content=ft.Text("是否确认退出单词学习？", size=13),
                actions=[
                    ft.TextButton("取消", on_click=_cancel),
                    ft.TextButton("退出", on_click=_do_exit,
                                  style=ft.ButtonStyle(color=ft.Colors.BLUE_600)),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
                on_dismiss=_on_dismiss,
            )
            _exit_dlg["ref"] = dlg
            page.open(dlg)
            page.update()

        def _on_window_event(e):
            """窗口事件：关闭→确认弹窗；失焦/恢复→后台超时检测"""
            if _exit_dlg_open["v"]:
                return  # 弹窗打开时忽略所有事件，防止UI阻塞
            evt = getattr(e, 'type', None) or getattr(e, 'data', None) or str(e)
            evt_lower = str(evt).lower()
            if "close" in evt_lower:
                _show_exit_confirm()
            elif evt in ("blur", "BLUR", "hide", "HIDE"):
                _blur_time["t"] = time.time()
            elif evt in ("focus", "FOCUS", "show", "SHOW"):
                if _blur_time["t"] and (time.time() - _blur_time["t"] > 600):
                    _blur_time["t"] = None
                    if hasattr(page, '_relogin') and callable(page._relogin):
                        page._relogin()
                else:
                    _blur_time["t"] = None

        # 拦截返回键（Android）
        try:
            page.on_view_pop = _show_exit_confirm
        except Exception:
            pass
        # 桌面窗口关闭拦截 + 前后台事件（用window.on_event，兼容0.28.3）
        try:
            page.window.prevent_close = True
            page.window.on_event = _on_window_event
        except Exception:
            pass

        _flog("page.update() 第一次...")
        page.update()
        _flog("page.update() 完成")
        # 用 threading 异步初始化（page.run_task 在部分 Android 上不工作）
        t = threading.Thread(target=_init_app_sync, args=(page,), daemon=True)
        t.start()
        _flog("初始化线程已启动")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        _flog(f"FATAL in main: {e}\n{tb}")
        try:
            page.add(ft.Container(
                content=ft.Column([
                    ft.Text("启动错误", size=20, color=ft.Colors.RED, weight=ft.FontWeight.BOLD),
                    ft.Text(str(e), size=14, color=ft.Colors.RED),
                    ft.Container(height=10),
                    ft.Text(tb, size=10, color=ft.Colors.GREY_700, selectable=True),
                ], scroll=ft.ScrollMode.AUTO, spacing=5),
                padding=20, expand=True,
            ))
            page.update()
        except Exception as e2:
            _flog(f"显示错误页失败: {e2}")
            try:
                page.add(ft.Text(f"FATAL: {e}", color=ft.Colors.RED))
                page.update()
            except Exception:
                pass


def _init_app_sync(page: ft.Page):
    """同步初始化（在子线程中执行）：数据库、登录页等"""
    try:
        _flog("[init] 开始初始化...")
        from app_paths import set_app_dir, get_app_dir
        _storage = os.environ.get("FLET_APP_STORAGE_DIR")
        _flog(f"[init] FLET_APP_STORAGE_DIR={_storage}")
        if _storage:
            set_app_dir(_storage)
        _flog(f"[init] app_dir={get_app_dir()}")

        _flog("[init] init_app_db...")
        init_app_db(page)
        _flog("[init] init_app_db 完成")

        _flog("[init] TursoClient...")
        page._db = TursoClient()
        _flog("[init] LocalSQLiteDB...")
        page._local_db = LocalSQLiteDB()
        page._user_data = {}

        if hasattr(page, 'window') and page.window is not None:
            try:
                page.window.width = 400
                page.window.height = 700
                page.window.resizable = True
            except Exception:
                pass

        # 强制竖屏（移动端）
        try:
            page.orientation = ft.PageOrientation.PORTRAIT
        except Exception:
            pass

        _flog("[init] LoadingOverlay...")
        try:
            loading = LoadingOverlay(page)
            page.loading_overlay = loading
            _flog("[init] LoadingOverlay 完成")
        except Exception as e:
            _flog(f"[init] LoadingOverlay 失败: {e}")

        def on_login_success(page, user_data):
            _flog("[init] 登录成功，加载首页...")
            page.loading_overlay.show("加载首页...")
            page._user_data = user_data
            main_layout = MainLayout(page, user_data)
            page.controls.clear()
            page.add(ft.SafeArea(content=main_layout.build(), expand=True))
            page.update()
            _flog("[init] 首页已显示")

        def _show_login_page(expired_msg=None):
            """返回登录页（后台超时调用）"""
            try:
                page.controls.clear()
                lp = LoginPage(page, on_login_success)
                content = lp.build()
                page.add(ft.SafeArea(content=content, expand=True))
                if expired_msg:
                    try:
                        lp.tip.value = expired_msg
                        lp.tip.color = ft.Colors.ORANGE_700
                    except Exception:
                        pass
                page.update()
            except Exception as ex:
                _flog(f"[relogin] 失败: {ex}")

        page._relogin = lambda: _show_login_page("登录已过期，请重新登录")

        # ---------- 会话超时：后台超过10分钟自动登出 ----------
        _SESSION_TIMEOUT = 600  # 10分钟（秒）
        _last_background_time = [None]  # 用列表实现闭包可变变量

        def _on_lifecycle(e):
            try:
                state = getattr(e, 'state', None)
                state_str = str(state).upper() if state is not None else ""
                # Flet 0.28.3 枚举可能无PAUSED，用字符串兼容
                if "PAUSE" in state_str or "INACTIVE" in state_str or "HIDE" in state_str:
                    # 进入后台/锁屏，记录时间
                    import time as _time
                    _last_background_time[0] = _time.time()
                elif "RESUME" in state_str:
                    # 恢复前台，检查是否超时
                    import time as _time
                    if _last_background_time[0] is not None:
                        elapsed = _time.time() - _last_background_time[0]
                        if elapsed > _SESSION_TIMEOUT:
                            _last_background_time[0] = None
                            page._relogin()
                            return
                    _last_background_time[0] = None
            except Exception as ex:
                _flog(f"[lifecycle] 异常: {ex}")

        try:
            page.on_app_lifecycle_state_change = _on_lifecycle
            _flog("[lifecycle] 生命周期监听已注册（超时10分钟）")
        except Exception as ex:
            _flog(f"[lifecycle] 注册失败: {ex}")

        _flog("[init] 创建 LoginPage...")
        login_page = LoginPage(page, on_login_success)
        _flog("[init] LoginPage.build()...")
        login_content = login_page.build()
        _flog("[init] 清除页面并添加登录页...")
        page.controls.clear()
        page.add(ft.SafeArea(content=login_content, expand=True))
        page.update()
        _flog("[init] 登录页已显示，初始化完成！")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        _flog(f"[init FATAL] {e}\n{tb}")
        try:
            page.controls.clear()
            page.add(ft.Container(
                content=ft.Column([
                    ft.Text("初始化失败", size=20, color=ft.Colors.RED, weight=ft.FontWeight.BOLD),
                    ft.Text(str(e), size=14, color=ft.Colors.RED),
                    ft.Container(height=10),
                    ft.Text(tb, size=10, color=ft.Colors.GREY_700, selectable=True),
                    ft.Container(height=10),
                    ft.Text(f"日志文件: {_LOG_FILE}", size=9, color=ft.Colors.GREY_500),
                ], scroll=ft.ScrollMode.AUTO, spacing=5),
                padding=20, expand=True,
            ))
            page.update()
        except Exception as e2:
            _flog(f"[init] 显示错误页失败: {e2}")

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
