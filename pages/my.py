# pages/my.py
import flet as ft
import os
import asyncio
import hashlib
import datetime
import sqlite3
from app_paths import get_app_dir, get_log_dir
from auth import save_login_config, load_login_config
from pages.notification_center import NotificationCenter

# 账户状态映射
STATUS_MAP = {
    0: ("正常", ft.Colors.GREEN_600),
    1: ("禁用", ft.Colors.RED_600),
    2: ("冻结", ft.Colors.ORANGE_600),
    3: ("封禁", ft.Colors.RED_800),
    4: ("注销中", ft.Colors.GREY_600),
    5: ("已注销", ft.Colors.GREY_400),
}

SYNC_TABLES = ["users", "grades", "volumes", "units", "questions", "words",
               "words_answer_records", "user_chinese_culture_answer_history",
               "user_chinese_culture_questions_history",
               "user_chinese_culture_answer_summary", "chinese_sentences_history"]


class MyPage:
    def __init__(self, page: ft.Page, user_data: dict):
        self.page = page
        self.user_data = user_data
        self._sync_time_ref = None
        self._sync_count_ref = None
        self._remember_switch = None

    # ============================================================
    # 数据查询
    # ============================================================
    def _get_user_detail(self):
        """从本地库查用户完整信息"""
        uid = self.user_data.get("id") or self.user_data.get("user_id")
        try:
            db_path = get_app_dir() / "local_cache.db"
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT username, user_type, score, level_id, reg_date, "
                "user_status, sync_enabled, total_time, consecutive_login_days, "
                "experience, total_stars, nickname, last_login_date, "
                "evaluation_score, avg_evaluation_score "
                "FROM users WHERE user_id = ?", [uid]
            ).fetchone()
            conn.close()
            return dict(row) if row else {}
        except Exception:
            return {}

    def _get_sync_info(self):
        """获取同步状态：上次同步时间 + 本地记录总数"""
        info = {"last_sync": "从未同步", "total_rows": 0, "table_count": 0}
        try:
            sf = get_app_dir() / "sync_state.json"
            if sf.exists():
                import json
                state = json.loads(sf.read_text(encoding="utf-8"))
                info["last_sync"] = state.get("last_sync", "从未同步")
        except Exception:
            pass
        try:
            db_path = get_app_dir() / "local_cache.db"
            conn = sqlite3.connect(str(db_path))
            total = 0
            tbl_count = 0
            for t in SYNC_TABLES:
                try:
                    cnt = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                    total += cnt
                    tbl_count += 1
                except Exception:
                    pass
            conn.close()
            info["total_rows"] = total
            info["table_count"] = tbl_count
        except Exception:
            pass
        return info

    def _get_learning_stats(self):
        """三科总学习时长/总答题数/正确率"""
        uid = self.user_data.get("id") or self.user_data.get("user_id")
        stats = {"total_time": 0, "total_answers": 0, "correct": 0}
        try:
            db_path = get_app_dir() / "local_cache.db"
            conn = sqlite3.connect(str(db_path))
            # 英语
            try:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt, COALESCE(SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END),0) as ok, "
                    "COALESCE(SUM(duration),0) as dur FROM words_answer_records WHERE user_id=?", [uid]).fetchone()
                stats["total_answers"] += row[0] or 0
                stats["correct"] += row[1] or 0
                stats["total_time"] += row[2] or 0
            except Exception:
                pass
            # 国学
            try:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt, COALESCE(SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END),0) as ok, "
                    "COALESCE(SUM(duration),0) as dur FROM user_chinese_culture_answer_history WHERE user_id=?", [uid]).fetchone()
                stats["total_answers"] += row[0] or 0
                stats["correct"] += row[1] or 0
                stats["total_time"] += row[2] or 0
            except Exception:
                pass
            # 辞海
            try:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt, COALESCE(SUM(CASE WHEN accuracy>=1 THEN 1 ELSE 0 END),0) as ok, "
                    "COALESCE(SUM(answer_duration),0) as dur FROM chinese_sentences_history WHERE user_id=?", [uid]).fetchone()
                stats["total_answers"] += row[0] or 0
                stats["correct"] += row[1] or 0
                stats["total_time"] += row[2] or 0
            except Exception:
                pass
            conn.close()
        except Exception:
            pass
        return stats

    def _build_stats_card(self, stats):
        """学习数据概览卡片"""
        total_min = stats["total_time"] // 60
        if total_min >= 60:
            time_str = f"{total_min // 60}h{total_min % 60}m"
        else:
            time_str = f"{total_min}分钟"
        accuracy = f"{(stats['correct'] / stats['total_answers'] * 100):.1f}%" if stats["total_answers"] > 0 else "—"

        def _stat_item(icon, icon_bg, label, value, value_color):
            return ft.Container(
                content=ft.Column([
                    ft.Container(
                        content=ft.Icon(icon, size=18, color=ft.Colors.WHITE),
                        width=36, height=36, border_radius=10, bgcolor=icon_bg,
                        alignment=ft.alignment.center),
                    ft.Container(height=4),
                    ft.Text(value, size=16, weight=ft.FontWeight.BOLD, color=value_color),
                    ft.Text(label, size=10, color=ft.Colors.GREY_500),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0, tight=True),
                expand=True, alignment=ft.alignment.center,
            )

        return ft.Container(
            padding=14, bgcolor=ft.Colors.WHITE, border_radius=14,
            shadow=ft.BoxShadow(blur_radius=8, color="#10000000", offset=ft.Offset(0, 2)),
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.INSIGHTS, size=16, color=ft.Colors.INDIGO_500),
                    ft.Text("学习数据概览", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.INDIGO_700),
                ], spacing=4),
                ft.Container(height=8),
                ft.Row([
                    _stat_item(ft.Icons.TIMER, ft.Colors.BLUE_500, "总学习时长", time_str, ft.Colors.BLUE_700),
                    _stat_item(ft.Icons.QUIZ, ft.Colors.GREEN_500, "总答题数", str(stats["total_answers"]), ft.Colors.GREEN_700),
                    _stat_item(ft.Icons.TRACK_CHANGES, ft.Colors.ORANGE_500, "正确率", accuracy, ft.Colors.ORANGE_700),
                ], spacing=4, alignment=ft.MainAxisAlignment.SPACE_AROUND),
            ], spacing=0),
        )

    # ============================================================
    # 用户信息卡
    # ============================================================
    def _build_user_card(self, detail):
        username = detail.get("username", self.user_data.get("username", "未登录"))
        user_type = detail.get("user_type", self.user_data.get("type", ""))
        type_label = "管理员" if str(user_type) in ("1", "admin") else "普通用户"
        score = detail.get("score", self.user_data.get("score", 0))
        level = detail.get("level_id", self.user_data.get("level_id", 1))
        experience = detail.get("experience", 0)
        total_stars = detail.get("total_stars", 0)
        # 保存可刷新的文本引用
        self._score_text = ft.Text(str(score), size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700)
        self._level_text = ft.Text(f"Lv.{level}", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700)
        self._exp_text = ft.Text(str(experience), size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_700)
        self._stars_text = ft.Text(str(total_stars), size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER_700)
        reg_date = str(detail.get("reg_date", "-"))[:10]
        status_val = detail.get("user_status", 0)
        try:
            status_val = int(status_val)
        except (ValueError, TypeError):
            status_val = 0
        status_label, status_color = STATUS_MAP.get(status_val, ("未知", ft.Colors.GREY_600))
        sync_enabled = detail.get("sync_enabled", 1)
        try:
            sync_enabled = int(sync_enabled)
        except (ValueError, TypeError):
            sync_enabled = 1

        avatar = ft.Container(
            content=ft.CircleAvatar(
                content=ft.Text(username[0].upper(), size=24, color=ft.Colors.WHITE,
                                weight=ft.FontWeight.BOLD),
                bgcolor=ft.Colors.BLUE_600, radius=30
            ),
        )

        # 状态标签
        status_tag = ft.Container(
            content=ft.Text(status_label, size=10, color=ft.Colors.WHITE,
                            weight=ft.FontWeight.BOLD),
            padding=ft.padding.symmetric(horizontal=8, vertical=2),
            bgcolor=status_color, border_radius=10,
        )
        sync_tag = ft.Container(
            content=ft.Text("同步开" if sync_enabled else "同步关", size=10,
                            color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            padding=ft.padding.symmetric(horizontal=8, vertical=2),
            bgcolor=ft.Colors.BLUE_500 if sync_enabled else ft.Colors.GREY_400,
            border_radius=10,
        )

        return ft.Container(
            padding=16, bgcolor=ft.Colors.WHITE, border_radius=16,
            shadow=ft.BoxShadow(blur_radius=12, color="#15000000",
                                offset=ft.Offset(0, 2)),
            content=ft.Column([
                ft.Row([
                    avatar,
                    ft.Column([
                        ft.Text(username, size=20, weight=ft.FontWeight.BOLD,
                                color=ft.Colors.BLUE_900),
                        ft.Row([status_tag, sync_tag], spacing=6),
                    ], spacing=4, expand=True),
                ], spacing=12),
                ft.Container(height=1, bgcolor=ft.Colors.GREY_200),
                ft.Row([
                    ft.Column([
                        ft.Text("积分", size=11, color=ft.Colors.GREY_500),
                        self._score_text,
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                    ft.Container(width=1, height=36, bgcolor=ft.Colors.GREY_200),
                    ft.Column([
                        ft.Text("等级", size=11, color=ft.Colors.GREY_500),
                        self._level_text,
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                    ft.Container(width=1, height=36, bgcolor=ft.Colors.GREY_200),
                    ft.Column([
                        ft.Text("经验", size=11, color=ft.Colors.GREY_500),
                        self._exp_text,
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                    ft.Container(width=1, height=36, bgcolor=ft.Colors.GREY_200),
                    ft.Column([
                        ft.Text("星星", size=11, color=ft.Colors.GREY_500),
                        self._stars_text,
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ], alignment=ft.MainAxisAlignment.SPACE_EVENLY),
                ft.Row([
                    ft.Icon(ft.Icons.CALENDAR_TODAY, size=14, color=ft.Colors.GREY_400),
                    ft.Text(f"注册时间: {reg_date}", size=12, color=ft.Colors.GREY_500),
                ], spacing=4),
            ], spacing=10),
        )

    # ============================================================
    # 数据同步卡
    # ============================================================
    def _build_sync_card(self):
        info = self._get_sync_info()
        self._sync_time_ref = ft.Text(info["last_sync"], size=12,
                                      color=ft.Colors.GREY_600)
        self._sync_count_ref = ft.Text(
            f"{info['table_count']} 张表 · {info['total_rows']} 条记录",
            size=12, color=ft.Colors.GREY_600)

        sync_btn = ft.ElevatedButton(
            "立即同步", icon=ft.Icons.SYNC,
            on_click=self._do_sync,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=16, vertical=8),
            ),
        )

        return ft.Container(
            padding=16, bgcolor=ft.Colors.WHITE, border_radius=16,
            shadow=ft.BoxShadow(blur_radius=12, color="#15000000",
                                offset=ft.Offset(0, 2)),
            content=ft.Column([
                ft.Row([
                    ft.Container(
                        padding=ft.padding.all(8), bgcolor=ft.Colors.BLUE_50,
                        border_radius=10,
                        content=ft.Icon(ft.Icons.CLOUD_SYNC, size=22,
                                        color=ft.Colors.BLUE_600),
                    ),
                    ft.Column([
                        ft.Text("数据同步", size=15, weight=ft.FontWeight.BOLD,
                                color=ft.Colors.GREY_800),
                        self._sync_time_ref,
                        self._sync_count_ref,
                    ], spacing=2, expand=True),
                    sync_btn,
                ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=0),
        )

    async def _do_sync(self, e):
        """手动同步"""
        if hasattr(self.page, 'loading_overlay'):
            self.page.loading_overlay.show("正在同步数据...")
        try:
            from sync_http import sync_to_local
            ok, msg = await asyncio.to_thread(sync_to_local, 120)
            # 刷新同步信息显示
            info = self._get_sync_info()
            self._sync_time_ref.value = info["last_sync"]
            self._sync_count_ref.value = f"{info['table_count']} 张表 · {info['total_rows']} 条记录"
            self._sync_time_ref.update()
            self._sync_count_ref.update()
            # 刷新用户卡数据（积分/等级/经验/星星）
            try:
                detail = self._get_user_detail()
                if hasattr(self, '_score_text') and detail:
                    self._score_text.value = str(detail.get("score", 0))
                    self._level_text.value = f"Lv.{detail.get('level_id', 1)}"
                    self._exp_text.value = str(detail.get("experience", 0))
                    self._stars_text.value = str(detail.get("total_stars", 0))
                    self._score_text.update()
                    self._level_text.update()
                    self._exp_text.update()
                    self._stars_text.update()
            except Exception:
                pass
            self.page.open(ft.SnackBar(ft.Text(msg), duration=2500))
        except Exception as ex:
            self.page.open(ft.SnackBar(ft.Text(f"同步失败: {ex}"), duration=2500))
        finally:
            if hasattr(self.page, 'loading_overlay'):
                self.page.loading_overlay.hide()

    # ============================================================
    # 消息通知中心
    # ============================================================
    def _open_notifications(self):
        nc = NotificationCenter(self.page, self.user_data)
        dlg = ft.AlertDialog(
            content=ft.Container(content=nc.build(), width=380, height=520),
            actions_padding=8,
            on_dismiss=lambda e: self._refresh_notif_badge(),
        )
        self.page.open(dlg)

    def _refresh_notif_badge(self):
        """弹窗关闭后刷新未读红点"""
        nc = NotificationCenter(self.page, self.user_data)
        unread = nc.get_unread_count()
        if hasattr(self, '_notif_badge') and self._notif_badge:
            self._notif_badge.content.value = str(unread)
            self._notif_badge.visible = unread > 0
        if hasattr(self, '_notif_subtitle') and self._notif_subtitle:
            self._notif_subtitle.value = f"{unread}条未读" if unread > 0 else "查看奖励与系统通知"
        self.page.update()

    # ============================================================
    # 修改密码
    # ============================================================
    def _open_change_password(self, e):
        # ---------- 输入框 ----------
        old_pwd = ft.TextField(
            label="当前密码", password=True, can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK_OUTLINE,
            border_radius=10, border_color=ft.Colors.GREY_300,
            focused_border_color=ft.Colors.BLUE_500,
            bgcolor=ft.Colors.GREY_50, filled=True,
            text_size=14,
        )
        new_pwd = ft.TextField(
            label="新密码", password=True, can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK,
            border_radius=10, border_color=ft.Colors.GREY_300,
            focused_border_color=ft.Colors.BLUE_500,
            bgcolor=ft.Colors.GREY_50, filled=True,
            text_size=14,
        )
        confirm_pwd = ft.TextField(
            label="确认新密码", password=True, can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK_CLOCK,
            border_radius=10, border_color=ft.Colors.GREY_300,
            focused_border_color=ft.Colors.BLUE_500,
            bgcolor=ft.Colors.GREY_50, filled=True,
            text_size=14,
        )

        # ---------- 密码强度条 ----------
        strength_bars = [ft.Container(width=36, height=5, bgcolor=ft.Colors.GREY_200,
                                       border_radius=3) for _ in range(4)]
        strength_label = ft.Text("密码强度", size=10, color=ft.Colors.GREY_400)

        def _calc_strength(pwd):
            if not pwd: return 0, ft.Colors.GREY_400, "密码强度"
            score = 0
            if len(pwd) >= 4: score += 1
            if len(pwd) >= 8: score += 1
            if any(c.isdigit() for c in pwd) and any(c.isalpha() for c in pwd): score += 1
            if any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in pwd): score += 1
            colors = [ft.Colors.GREY_300, ft.Colors.RED_400, ft.Colors.ORANGE_400,
                      ft.Colors.AMBER_400, ft.Colors.GREEN_500]
            labels = ["密码强度", "弱", "一般", "良好", "强"]
            return score, colors[score], labels[score]

        def _on_new_change(ev):
            score, color, label = _calc_strength(new_pwd.value or "")
            for i, bar in enumerate(strength_bars):
                bar.bgcolor = color if i < score else ft.Colors.GREY_200
                bar.update()
            strength_label.value = label
            strength_label.color = color if score > 0 else ft.Colors.GREY_400
            strength_label.update()

        new_pwd.on_change = _on_new_change

        # ---------- 确认匹配提示 ----------
        match_icon = ft.Icon(ft.Icons.CIRCLE, size=12, color=ft.Colors.GREY_300)
        match_text = ft.Text("再次输入新密码", size=10, color=ft.Colors.GREY_400)
        match_row = ft.Row([match_icon, match_text], spacing=3, visible=False)

        def _on_confirm_change(ev):
            cv = confirm_pwd.value or ""
            nv = new_pwd.value or ""
            if not cv:
                match_row.visible = False
            elif cv == nv:
                match_icon.name = ft.Icons.CHECK_CIRCLE
                match_icon.color = ft.Colors.GREEN_500
                match_text.value = "两次密码一致"
                match_text.color = ft.Colors.GREEN_500
                match_row.visible = True
            else:
                match_icon.name = ft.Icons.ERROR
                match_icon.color = ft.Colors.RED_400
                match_text.value = "两次密码不一致"
                match_text.color = ft.Colors.RED_400
                match_row.visible = True
            match_row.update()

        confirm_pwd.on_change = _on_confirm_change

        # ---------- 错误提示 ----------
        err_text = ft.Text("", size=12, color=ft.Colors.RED_500)
        err_row = ft.Row([
            ft.Icon(ft.Icons.ERROR_OUTLINE, size=14, color=ft.Colors.RED_500),
            err_text,
        ], spacing=4, visible=False)

        def _show_err(msg):
            err_text.value = msg
            err_row.visible = True
            err_row.update()

        # ---------- 提交 ----------
        def do_submit(ev):
            err_row.visible = False
            err_row.update()

            old = old_pwd.value or ""
            new = new_pwd.value or ""
            confirm = confirm_pwd.value or ""
            if not old or not new:
                _show_err("请输入当前密码和新密码")
                return
            if len(new) < 6 or len(new) > 20:
                _show_err("新密码长度需6-20位")
                return
            if ' ' in new:
                _show_err("密码不能包含空格")
                return
            import re
            if not re.match(r'^[a-zA-Z0-9]+$', new):
                _show_err("密码只能包含英文字母和数字，不能使用特殊字符")
                return
            if not any(c.isalpha() for c in new):
                _show_err("新密码必须包含字母")
                return
            if not any(c.isdigit() for c in new):
                _show_err("新密码必须包含数字")
                return
            if new != confirm:
                _show_err("两次输入的新密码不一致")
                return

            submit_btn.disabled = True
            submit_btn.text = "提交中..."
            submit_btn.update()

            try:
                h1 = hashlib.md5(old.strip().encode()).hexdigest()
                h2 = hashlib.md5(h1.encode()).hexdigest()
                uid = self.user_data.get("id") or self.user_data.get("user_id")
                from database import TursoClient
                db = TursoClient()
                row = db.fetch_one("SELECT password FROM users WHERE user_id = ?", [uid])
                if not row or row.get("password") != h2:
                    _show_err("当前密码错误")
                    submit_btn.disabled = False
                    submit_btn.text = "确认修改"
                    submit_btn.update()
                    return
                new_h1 = hashlib.md5(new.strip().encode()).hexdigest()
                new_h2 = hashlib.md5(new_h1.encode()).hexdigest()
                db.execute("UPDATE users SET password = ? WHERE user_id = ?", [new_h2, uid])
                self.page.close(dlg)
                self.page.open(ft.SnackBar(
                    content=ft.Row([
                        ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color=ft.Colors.GREEN_500),
                        ft.Text("密码修改成功", color=ft.Colors.GREEN_700),
                    ], spacing=6),
                    duration=2000))
            except Exception as ex:
                _show_err(f"修改失败: {ex}")
                submit_btn.disabled = False
                submit_btn.text = "确认修改"
                submit_btn.update()

        # ---------- 按钮 ----------
        cancel_btn = ft.TextButton("取消", on_click=lambda ev: self.page.close(dlg))
        submit_btn = ft.ElevatedButton(
            "确认修改", icon=ft.Icons.SAVE, on_click=do_submit,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=20, vertical=8),
            ))

        # ---------- 标题 ----------
        title_row = ft.Row([
            ft.Container(
                width=36, height=36, border_radius=18,
                bgcolor=ft.Colors.BLUE_100,
                content=ft.Icon(ft.Icons.LOCK, size=18, color=ft.Colors.BLUE_600),
                alignment=ft.alignment.center,
            ),
            ft.Column([
                ft.Text("修改密码", size=16, weight=ft.FontWeight.BOLD,
                        color=ft.Colors.GREY_800),
                ft.Text("请输入当前密码并设置新密码", size=10, color=ft.Colors.GREY_400),
            ], spacing=0, tight=True),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # ---------- 弹窗（标准结构） ----------
        dlg = ft.AlertDialog(
            title=title_row,
            content=ft.Container(
                width=320,
                content=ft.Column([
                    old_pwd,
                    new_pwd,
                    ft.Row(strength_bars + [ft.Container(width=6), strength_label],
                           spacing=3, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    confirm_pwd,
                    match_row,
                    err_row,
                ], spacing=8, tight=True,
                   horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                padding=0,
            ),
            actions=[cancel_btn, submit_btn],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(dlg)

    # ============================================================
    # 记住密码开关
    # ============================================================
    def _build_remember_tile(self):
        _, _, auto = load_login_config()
        self._remember_switch = ft.Switch(value=auto, on_change=self._toggle_remember)
        return ft.ListTile(
            leading=ft.Container(
                padding=ft.padding.all(8), bgcolor=ft.Colors.GREEN_50,
                border_radius=10,
                content=ft.Icon(ft.Icons.REMEMBER_ME, size=20,
                                color=ft.Colors.GREEN_600),
            ),
            title=ft.Text("记住密码", size=14, color=ft.Colors.GREY_800),
            subtitle=ft.Text("有效期10分钟，过期后需重新输入", size=11,
                             color=ft.Colors.GREY_400),
            trailing=self._remember_switch,
            content_padding=ft.padding.symmetric(horizontal=4, vertical=2),
        )

    def _toggle_remember(self, e):
        username = self.user_data.get("username", "")
        if self._remember_switch.value:
            # 开启：从登录缓存读取密码（10分钟内有效）
            _, pwd, _ = load_login_config()
            if not pwd:
                self.page.open(ft.SnackBar(
                    ft.Text("密码已过期，请重新登录后再开启记住密码"),
                    duration=2000))
                self._remember_switch.value = False
                self._remember_switch.update()
                return
            save_login_config(username, pwd, True)
            self.page.open(ft.SnackBar(
                ft.Text("已开启记住密码（有效期10分钟）"), duration=1500))
        else:
            # 关闭：清除密码，保留用户名
            save_login_config(username, "", False)
            self.page.open(ft.SnackBar(
                ft.Text("已关闭记住密码"), duration=1500))

    # ============================================================
    # 日志查看
    # ============================================================
    def _open_log_viewer(self, e):
        log_path = get_app_dir() / "startup_log.txt"
        if not log_path.exists():
            self.page.open(ft.SnackBar(ft.Text("暂无日志文件"), duration=1500))
            return
        try:
            content = log_path.read_text(encoding="utf-8")
            # 只显示最后200行
            lines = content.splitlines()
            if len(lines) > 200:
                lines = lines[-200:]
            display = "\n".join(lines)
        except Exception as ex:
            display = f"读取日志失败: {ex}"

        log_field = ft.TextField(
            value=display, read_only=True, multiline=True,
            min_lines=15, max_lines=20, border_radius=8,
            text_size=11, expand=True,
        )

        def copy_log(ev):
            self.page.set_clipboard(display)
            self.page.open(ft.SnackBar(ft.Text("日志已复制到剪贴板"), duration=1500))

        dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Text("运行日志", size=16, weight=ft.FontWeight.BOLD, expand=True),
                ft.IconButton(ft.Icons.COPY, icon_size=18, on_click=copy_log,
                              tooltip="复制全部"),
            ]),
            content=ft.Container(content=log_field, width=320, padding=4),
            actions=[
                ft.TextButton("关闭", on_click=lambda ev: self.page.close(dlg)),
            ],
        )
        self.page.open(dlg)

    # ============================================================
    # 关于信息
    # ============================================================
    def _open_about(self, e):
        app_dir = str(get_app_dir())
        db_path = str(get_app_dir() / "local_cache.db")
        db_size = "未知"
        try:
            sz = os.path.getsize(db_path)
            if sz > 1024 * 1024:
                db_size = f"{sz / 1024 / 1024:.1f} MB"
            else:
                db_size = f"{sz / 1024:.0f} KB"
        except Exception:
            pass

        info_items = [
            ("版本", "2.0.0"),
            ("数据目录", app_dir),
            ("本地数据库", db_size),
            ("同步表数", str(len(SYNC_TABLES))),
        ]
        rows = []
        for k, v in info_items:
            rows.append(ft.Row([
                ft.Text(k, size=12, color=ft.Colors.GREY_500, width=80),
                ft.Text(v, size=12, color=ft.Colors.GREY_800, expand=True,
                        no_wrap=False),
            ], spacing=8))

        dlg = ft.AlertDialog(
            title=ft.Text("关于", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(content=ft.Column(rows, spacing=8, tight=True,
                                                   width=300), padding=4),
            actions=[
                ft.TextButton("关闭", on_click=lambda ev: self.page.close(dlg)),
            ],
        )
        self.page.open(dlg)

    # ============================================================
    # 退出登录
    # ============================================================
    def _do_logout(self, e):
        def confirm(ev):
            self.page.close(confirm_dlg)
            # 清除登录配置
            try:
                cf = get_app_dir() / "login_config.txt"
                if cf.exists():
                    cf.unlink()
            except Exception:
                pass
            # 返回登录页
            if hasattr(self.page, '_relogin') and callable(self.page._relogin):
                self.page._relogin()

        confirm_dlg = ft.AlertDialog(
            title=ft.Text("退出登录", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Text("确定要退出当前账号吗？", size=13),
            actions=[
                ft.TextButton("取消", on_click=lambda ev: self.page.close(confirm_dlg)),
                ft.ElevatedButton("退出", on_click=confirm,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.RED_600,
                                                       color=ft.Colors.WHITE)),
            ],
        )
        self.page.open(confirm_dlg)

    # ============================================================
    # 功能入口列表项
    # ============================================================
    def _menu_tile(self, icon, icon_bg, icon_color, title, subtitle, on_click,
                   trailing=None):
        return ft.Container(
            on_click=on_click,
            bgcolor=ft.Colors.WHITE, border_radius=12,
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            content=ft.Row([
                ft.Container(
                    padding=ft.padding.all(8), bgcolor=icon_bg, border_radius=10,
                    content=ft.Icon(icon, size=20, color=icon_color),
                ),
                ft.Column([
                    ft.Text(title, size=14, weight=ft.FontWeight.W_600,
                            color=ft.Colors.GREY_800),
                    ft.Text(subtitle, size=11, color=ft.Colors.GREY_400),
                ], spacing=1, tight=True, expand=True),
                trailing if trailing else ft.Icon(
                    ft.Icons.KEYBOARD_ARROW_RIGHT, size=18, color=ft.Colors.GREY_300),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

    # ============================================================
    # 页面入口
    # ============================================================
    def build(self):
        detail = self._get_user_detail()
        stats = self._get_learning_stats()

        # 功能入口
        notif_center = NotificationCenter(self.page, self.user_data)
        unread = notif_center.get_unread_count()
        self._notif_badge = ft.Container(
            content=ft.Text(str(unread), size=10, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.RED_500, border_radius=10,
            padding=ft.padding.symmetric(horizontal=5, vertical=1),
            visible=unread > 0,
        )
        self._notif_subtitle = ft.Text(
            f"{unread}条未读" if unread > 0 else "查看奖励与系统通知",
            size=11, color=ft.Colors.GREY_400,
        )
        notif_tile = ft.Container(
            on_click=lambda e: self._open_notifications(),
            bgcolor=ft.Colors.WHITE, border_radius=12,
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            content=ft.Row([
                ft.Container(
                    padding=ft.padding.all(8), bgcolor=ft.Colors.PURPLE_50, border_radius=10,
                    content=ft.Icon(ft.Icons.NOTIFICATIONS, size=20, color=ft.Colors.PURPLE_600),
                ),
                ft.Column([
                    ft.Text("消息通知", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_800),
                    self._notif_subtitle,
                ], spacing=1, tight=True, expand=True),
                self._notif_badge,
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )
        pwd_tile = self._menu_tile(
            ft.Icons.LOCK, ft.Colors.RED_50, ft.Colors.RED_600,
            "修改密码", "修改登录密码", self._open_change_password)
        remember_tile = self._build_remember_tile()
        # 把 remember_tile 包装成统一风格
        remember_container = ft.Container(
            bgcolor=ft.Colors.WHITE, border_radius=12,
            padding=ft.padding.symmetric(horizontal=12, vertical=4),
            content=remember_tile,
        )
        log_tile = self._menu_tile(
            ft.Icons.BUG_REPORT, ft.Colors.ORANGE_50, ft.Colors.ORANGE_600,
            "运行日志", "查看应用运行日志（最近200行）", self._open_log_viewer)
        about_tile = self._menu_tile(
            ft.Icons.INFO, ft.Colors.BLUE_50, ft.Colors.BLUE_600,
            "关于", "版本信息与数据目录", self._open_about)

        logout_btn = ft.ElevatedButton(
            "退出登录", icon=ft.Icons.LOGOUT,
            on_click=self._do_logout,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.RED_50, color=ft.Colors.RED_600,
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=ft.padding.symmetric(vertical=12),
            ),
            expand=True,
        )

        footer = ft.Text("© 2026 单词学习 · 版本 2.0", size=10,
                         color=ft.Colors.GREY_400,
                         text_align=ft.TextAlign.CENTER)

        content = ft.Column([
            ft.Text("我的", size=24, weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_900),
            ft.Container(height=4),
            self._build_user_card(detail),
            self._build_stats_card(stats),
            self._build_sync_card(),
            ft.Text("账户与设置", size=13, weight=ft.FontWeight.BOLD,
                    color=ft.Colors.GREY_500),
            notif_tile,
            pwd_tile,
            remember_container,
            log_tile,
            about_tile,
            ft.Container(height=8),
            logout_btn,
            footer,
        ], scroll=ft.ScrollMode.ADAPTIVE, spacing=10)

        return ft.Container(
            content=content, expand=True, padding=16,
            bgcolor=ft.Colors.TRANSPARENT,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                colors=[ft.Colors.BLUE_50, ft.Colors.INDIGO_50,
                        ft.Colors.PURPLE_50, ft.Colors.PINK_50],
            ),
        )
