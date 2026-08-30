import os
import asyncio
import json
import shutil
import flet as ft
from auth import AuthService, save_login_config, load_login_config
from app_paths import get_app_dir
from sync_http import sync_to_local  # HTTP同步到本地SQLite

class LoginPage:
    def __init__(self, page: ft.Page, on_success_callback):
        self.page = page
        self.on_success = on_success_callback
        self.auth = AuthService()

        # ---------- 文件选择器 ----------
        self.file_picker = ft.FilePicker(on_result=self.on_file_picked)
        try:
            if hasattr(self.page, 'overlay') and self.page.overlay is not None:
                self.page.overlay.append(self.file_picker)
        except Exception as e:
            print(f"[login] overlay append failed: {e}")

        # ---------- 配置面板 ----------
        self.config_url = ft.TextField(
            label="Turso URL",
            hint_text="libsql://your-db.turso.io",
            prefix_icon=ft.Icons.LINK,
            border=ft.InputBorder.OUTLINE,
            border_color=ft.Colors.GREY_300,
            focused_border_color=ft.Colors.BLUE_600,
            bgcolor=ft.Colors.WHITE,
            filled=True,
            text_style=ft.TextStyle(size=14),
            width=320,
        )
        self.config_token = ft.TextField(
            label="Turso Token",
            hint_text="eyJ...",
            prefix_icon=ft.Icons.KEY,
            password=True,
            can_reveal_password=True,
            border=ft.InputBorder.OUTLINE,
            border_color=ft.Colors.GREY_300,
            focused_border_color=ft.Colors.BLUE_600,
            bgcolor=ft.Colors.WHITE,
            filled=True,
            text_style=ft.TextStyle(size=14),
            width=320,
        )
        self.config_status = ft.Text("", color=ft.Colors.GREEN_600, size=13)
        self.import_btn = ft.ElevatedButton(
            "📂 导入配置文件",
            icon=ft.Icons.UPLOAD_FILE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=20),
                bgcolor=ft.Colors.ORANGE_600,
                color=ft.Colors.WHITE,
            ),
            on_click=lambda e: self.file_picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.ANY,
                dialog_title="选择 turso-config.json"
            )
        )
        self.save_config_btn = ft.ElevatedButton(
            "💾 保存配置",
            icon=ft.Icons.SAVE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=20),
                bgcolor=ft.Colors.GREEN_600,
                color=ft.Colors.WHITE,
            ),
            on_click=self._save_config
        )

        # ---------- 配置弹窗 ----------
        self.config_bottom_sheet = ft.BottomSheet(
            content=ft.Container(
                padding=ft.padding.all(20),
                content=ft.Column([
                    ft.Text("数据库配置", size=20, weight=ft.FontWeight.BOLD),
                    self.config_url,
                    self.config_token,
                    ft.Row([self.import_btn, self.save_config_btn], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
                    self.config_status,
                ], spacing=16, scroll=ft.ScrollMode.ADAPTIVE),
            ),
            is_scroll_controlled=True,
            enable_drag=True,
        )

        # ---------- 登录输入 ----------
        self.username = ft.TextField(
            label="用户名",
            prefix_icon=ft.Icons.PERSON_OUTLINE,
            border=ft.InputBorder.OUTLINE,
            border_color=ft.Colors.GREY_300,
            focused_border_color=ft.Colors.BLUE_600,
            bgcolor=ft.Colors.WHITE,
            filled=True,
            text_style=ft.TextStyle(size=15),
        )
        self.password = ft.TextField(
            label="密码",
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK_OUTLINE,
            border=ft.InputBorder.OUTLINE,
            border_color=ft.Colors.GREY_300,
            focused_border_color=ft.Colors.BLUE_600,
            bgcolor=ft.Colors.WHITE,
            filled=True,
            text_style=ft.TextStyle(size=15),
        )

        self.tip = ft.Text("", color=ft.Colors.RED_400, size=13)
        self.status = ft.Text("", color=ft.Colors.BLUE_600, size=13)

        self.login_btn = ft.ElevatedButton(
            "登 录",
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=25),
                bgcolor=ft.Colors.BLUE_600,
                color=ft.Colors.WHITE,
                elevation=6,
            ),
            on_click=self.on_login_click
        )

        self._load_saved()
        self._load_config_to_dialog()
        self.page._login_page = self

    # ---------- 文件选择回调 ----------
    def on_file_picked(self, e):
        if e.files:
            file_path = e.files[0].path
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if 'turso_token' in data and 'turso_url' in data:
                    dest_path = get_app_dir() / "turso-config.json"
                    shutil.copy(file_path, dest_path)
                    self.auth.reload_config()
                    self.config_url.value = data.get("turso_url")
                    self.config_token.value = data.get("turso_token")
                    self.config_status.value = "✅ 配置已导入并生效"
                    self.config_status.color = ft.Colors.GREEN_600
                    self.page.update()
                else:
                    self.config_status.value = "❌ 缺少 turso_token 或 turso_url"
                    self.config_status.color = ft.Colors.RED_400
                    self.page.update()
            except Exception as ex:
                self.config_status.value = f"❌ 导入失败: {ex}"
                self.config_status.color = ft.Colors.RED_400
                self.page.update()

    def _load_config_to_dialog(self):
        cfg_path = get_app_dir() / "turso-config.json"
        if cfg_path.exists():
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.config_url.value = data.get("turso_url", "")
                self.config_token.value = data.get("turso_token", "")
            except:
                pass

    def _save_config(self, e):
        url = self.config_url.value.strip()
        token = self.config_token.value.strip()
        if not url or not token:
            self.config_status.value = "❌ URL 和 Token 不能为空"
            self.config_status.color = ft.Colors.RED_400
            self.page.update()
            return
        try:
            cfg_path = get_app_dir() / "turso-config.json"
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump({"turso_url": url, "turso_token": token}, f, indent=2)
            self.auth.reload_config()
            self.config_status.value = "✅ 配置已保存并生效"
            self.config_status.color = ft.Colors.GREEN_600
            self.page.update()
        except Exception as ex:
            self.config_status.value = f"❌ 保存失败: {ex}"
            self.config_status.color = ft.Colors.RED_400
            self.page.update()

    def _update_sizes(self):
        win_w = getattr(self.page, 'width', 400) or 400
        avail = win_w - 40
        target = max(200, min(420, avail * 0.9))
        self.username.width = target
        self.password.width = target
        self.login_btn.width = max(140, min(260, target * 0.6))
        self.login_btn.height = 44

    def build(self):
        self._update_sizes()
        return ft.Container(
            expand=True,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_center,
                end=ft.alignment.bottom_center,
                colors=[ft.Colors.BLUE_50, ft.Colors.INDIGO_50, ft.Colors.PURPLE_50],
            ),
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text("欢迎回来", size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                                ft.IconButton(
                                    icon=ft.Icons.SETTINGS,
                                    icon_color=ft.Colors.GREY_600,
                                    tooltip="数据库配置",
                                    on_click=self._open_config_dialog,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.padding.symmetric(horizontal=20, vertical=10),
                    ),
                    ft.Container(
                        width=80,
                        height=80,
                        border_radius=40,
                        gradient=ft.LinearGradient(
                            begin=ft.alignment.top_left,
                            end=ft.alignment.bottom_right,
                            colors=[ft.Colors.BLUE_400, ft.Colors.PURPLE_400],
                        ),
                        content=ft.Icon(ft.Icons.PERSON, size=44, color=ft.Colors.WHITE),
                        shadow=ft.BoxShadow(blur_radius=20, color=ft.Colors.BLUE_200, spread_radius=4),
                        margin=ft.margin.only(top=10, bottom=10),
                    ),
                    ft.Text("登录可查看您的学习统计数据", size=14, color=ft.Colors.GREY_600),
                    ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                    ft.Card(
                        elevation=12,
                        margin=ft.margin.symmetric(horizontal=20),
                        shadow_color=ft.Colors.BLUE_200,
                        content=ft.Container(
                            padding=ft.padding.symmetric(horizontal=24, vertical=30),
                            bgcolor=ft.Colors.WHITE,
                            border_radius=16,
                            content=ft.Column([
                                self.username,
                                self.password,
                                self.tip,
                                self.status,
                                ft.Row([self.login_btn], alignment=ft.MainAxisAlignment.CENTER),
                            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=14, scroll=ft.ScrollMode.ADAPTIVE)
                        )
                    ),
                    ft.Container(
                        content=ft.Text("© 2025 单词学习 · 版本 2.0", size=10, color=ft.Colors.GREY_400),
                        margin=ft.margin.only(top=20),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
                scroll=ft.ScrollMode.ADAPTIVE
            )
        )

    def _open_config_dialog(self, e):
        self._load_config_to_dialog()
        self.config_status.value = ""
        self.page.open(self.config_bottom_sheet)

    # ---------- 登录相关 ----------
    def _load_saved(self):
        """自动填充：记住密码开启时填充用户名+密码，否则只填充用户名"""
        u, p, auto = load_login_config()
        if u:
            self.username.value = u
        if u and p and auto:
            self.password.value = p

    def on_login_click(self, e):
        self.page.run_task(self._do_login)

    # ---------- 核心登录方法（直接验证，无同步） ----------
    async def _do_login(self):
        self.tip.value = ""
        self.status.value = ""
        self.page.update()

        uname = self.username.value.strip()
        pwd = self.password.value.strip()
        if not uname or not pwd:
            self.tip.value = "⚠️ 请输入用户名和密码"
            self.tip.color = ft.Colors.RED_400
            self.page.update()
            return

        if hasattr(self.page, 'loading_overlay'):
            self.page.loading_overlay.show("正在验证身份...")

        self.login_btn.disabled = True
        self.username.disabled = True
        self.password.disabled = True
        self.login_btn.text = "登录中..."
        self.page.update()

        try:
            success, msg, user_data = await asyncio.to_thread(self.auth.login, uname, pwd)
        except Exception as e:
            success, msg, user_data = False, f"未知异常: {e}", None

        if not success:
            if hasattr(self.page, 'loading_overlay'):
                self.page.loading_overlay.hide()
            self.login_btn.disabled = False
            self.username.disabled = False
            self.password.disabled = False
            self.login_btn.text = "登 录"
            self.page.update()
            self.tip.value = f"❌ {msg}"
            self.tip.color = ft.Colors.RED_400
            self.page.update()
            return

        # 登录成功：保存密码缓存，保留之前的记住密码状态（auto）
        _, _, prev_auto = load_login_config()
        save_login_config(uname, pwd, prev_auto)

        # 根据云端 sync_enabled 决定是否同步
        try:
            sync_enabled = int(user_data.get('sync_enabled', 1)) if user_data else 1
        except (ValueError, TypeError):
            sync_enabled = 1
        if sync_enabled:
            if hasattr(self.page, 'loading_overlay'):
                self.page.loading_overlay.show("正在同步数据...")
            try:
                sync_ok, sync_msg = await asyncio.wait_for(
                    asyncio.to_thread(sync_to_local, 120), timeout=130)
                print(f"[login] 同步结果: {sync_msg}")
            except asyncio.TimeoutError:
                print("[login] 同步超时(130s)，跳过同步继续登录")
            except Exception as e:
                print(f"[login] 同步异常: {e}")
            finally:
                if hasattr(self.page, 'loading_overlay'):
                    self.page.loading_overlay.hide()
        else:
            print("[login] 同步已关闭，跳过")

        # 同步完成，恢复按钮，跳转首页（on_success会显示"加载首页..."）
        self.login_btn.disabled = False
        self.username.disabled = False
        self.password.disabled = False
        self.login_btn.text = "登 录"
        self.page.update()
        self.on_success(self.page, user_data)
