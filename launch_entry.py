"""Frozen application entry: redirect diagnostics before loading services."""
import sys
from desktop_runtime import DATA, log

if sys.stdout is None:
    sys.stdout = (DATA / 'application.log').open('a', encoding='utf-8', buffering=1)
if sys.stderr is None:
    sys.stderr = sys.stdout

try:
    from desktop_window import run
    run()
except Exception:
    import ctypes
    import traceback
    log(traceback.format_exc())
    ctypes.windll.user32.MessageBoxW(None, f'启动遇到问题，请保留并提供日志：\n{DATA}', '屿账启动提示', 0x10)
