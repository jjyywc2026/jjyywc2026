import flet as ft

class LoadingOverlay:
    """
    全局加载遮罩，覆盖在页面最上层，内容居中。
    """
    def __init__(self, page: ft.Page):
        self.page = page
        # 遮罩容器：全屏，半透明黑
        self.container = ft.Container(
            expand=True,
            visible=False,
            bgcolor="#80000000",  # 50% 透明度黑
            content=ft.Column(
                [
                    ft.ProgressRing(
                        width=40,
                        height=40,
                        stroke_width=4,
                        color=ft.Colors.BLUE_500,
                    ),
                    ft.Text(
                        "加载中...",
                        size=16,
                        color=ft.Colors.WHITE,
                        weight=ft.FontWeight.W_500,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,  # 水平居中
                alignment=ft.MainAxisAlignment.CENTER,             # 垂直居中（关键）
                spacing=15,
            ),
            alignment=ft.alignment.center,  # 容器内居中（备用）
        )
        # 添加到页面覆盖层（最高层级，覆盖所有内容）
        try:
            if hasattr(self.page, 'overlay') and self.page.overlay is not None:
                self.page.overlay.append(self.container)
        except Exception as e:
            print(f"[LoadingOverlay] overlay append failed: {e}")

    def show(self, message: str = "加载中..."):
        """显示加载遮罩，可自定义提示文字"""
        self.container.content.controls[1].value = message
        self.container.visible = True
        self.page.update()

    def hide(self):
        """隐藏加载遮罩"""
        self.container.visible = False
        self.page.update()

    def dispose(self):
        """从页面移除遮罩（可选）"""
        try:
            if hasattr(self.page, 'overlay') and self.page.overlay is not None:
                if self.container in self.page.overlay:
                    self.page.overlay.remove(self.container)
                    self.page.update()
        except Exception:
            pass