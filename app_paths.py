# app_paths.py — 统一应用数据目录
# 桌面: ~/.word_learning_app
# 手机: FLET_APP_STORAGE_DIR 环境变量（Flet 自动注入，应用私有可写目录）
import os
import pathlib

_app_dir = None


def set_app_dir(path):
    """启动时设置应用目录（Android/iOS 调用）"""
    global _app_dir
    _app_dir = pathlib.Path(path)
    _app_dir.mkdir(parents=True, exist_ok=True)


def get_app_dir():
    """获取应用数据目录"""
    global _app_dir
    if _app_dir is None:
        # 1. 手机端优先用 FLET_APP_STORAGE_DIR
        env_dir = os.environ.get("FLET_APP_STORAGE_DIR")
        if env_dir:
            _app_dir = pathlib.Path(env_dir)
        else:
            # 2. 检测 Android（通过 __file__ 路径，不用 resolve 避免跟软链接）
            self_path = os.path.abspath(__file__)
            if "/data/user/0/" in self_path or "/data/data/" in self_path:
                # Android: __file__ = /data/user/0/com.xxx/files/flet/app/app_paths.py
                # 上溯3级到 files/，应用私有可写目录
                _app_dir = pathlib.Path(self_path).parent.parent.parent / ".word_learning_app"
            else:
                # 3. 桌面端回退到用户目录
                _app_dir = pathlib.Path.home() / ".word_learning_app"
        # 4. 尝试创建，失败则兜底到当前文件目录
        try:
            _app_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            _app_dir = pathlib.Path(os.path.abspath(__file__)).parent
            try:
                _app_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
    return _app_dir


_log_dir = None

def get_log_dir():
    """获取日志目录（优先外部存储，文件管理器可直接查看；兜底到应用目录）"""
    global _log_dir
    if _log_dir is not None:
        return _log_dir
    candidates = []
    ext = os.environ.get("EXTERNAL_STORAGE") or "/sdcard"
    candidates.append(os.path.join(ext, "Android/data/com.wordlearning/files"))
    candidates.append(os.path.join(ext, "Android/data/com.wordlearning/cache"))
    flet_dir = os.environ.get("FLET_APP_STORAGE_DIR")
    if flet_dir:
        candidates.append(flet_dir)
    candidates.append(str(get_app_dir()))
    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            test = os.path.join(d, ".write_test")
            with open(test, "w") as f:
                f.write("ok")
            os.remove(test)
            _log_dir = pathlib.Path(d)
            return _log_dir
        except Exception:
            continue
    _log_dir = get_app_dir()
    return _log_dir
