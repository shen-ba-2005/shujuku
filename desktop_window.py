"""Small native Windows launcher window; uses ctypes, never tkinter."""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import os
import threading
import webbrowser
from desktop_runtime import DATA, Runtime, log


def run():
    import msvcrt
    user = C.WinDLL('user32', use_last_error=True)
    kernel = C.WinDLL('kernel32', use_last_error=True)
    gdi = C.WinDLL('gdi32', use_last_error=True)
    result_type = C.c_ssize_t
    callback_type = C.WINFUNCTYPE(result_type, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

    class WindowClass(C.Structure):
        _fields_ = [('style', W.UINT), ('proc', callback_type), ('extra', C.c_int),
                    ('window_extra', C.c_int), ('instance', W.HINSTANCE), ('icon', W.HANDLE),
                    ('cursor', W.HANDLE), ('background', W.HBRUSH),
                    ('menu', W.LPCWSTR), ('name', W.LPCWSTR)]

    user.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                                    C.c_int, C.c_int, C.c_int, C.c_int,
                                    W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p]
    user.CreateWindowExW.restype = W.HWND
    user.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
    user.DefWindowProcW.restype = result_type
    user.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
    user.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
    user.SetWindowTextW.argtypes = [W.HWND, W.LPCWSTR]
    user.EnableWindow.argtypes = [W.HWND, W.BOOL]
    user.DestroyWindow.argtypes = [W.HWND]
    user.MessageBoxW.argtypes = [W.HWND, W.LPCWSTR, W.LPCWSTR, W.UINT]
    user.SetForegroundWindow.argtypes = [W.HWND]
    user.FindWindowW.argtypes = [W.LPCWSTR, W.LPCWSTR]
    user.FindWindowW.restype = W.HWND
    user.ShowWindow.argtypes = [W.HWND, C.c_int]
    kernel.GetModuleHandleW.argtypes = [W.LPCWSTR]
    kernel.GetModuleHandleW.restype = W.HINSTANCE
    gdi.GetStockObject.argtypes = [C.c_int]
    gdi.GetStockObject.restype = W.HANDLE
    name = 'Shujuku_' + hashlib.sha256(str(DATA).encode()).hexdigest()[:16]
    lock = (DATA / 'launcher.lock').open('a+b')
    lock.seek(0)
    if lock.read(1) == b'':
        lock.write(b'0')
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        other = user.FindWindowW(name, None)
        if other:
            user.SetForegroundWindow(other)
            user.PostMessageW(other, 0x8003, 0, 0)
        lock.close()
        return

    stop_event = threading.Event()
    state = {'text': '正在准备应用，首次启动可能需要约半分钟…', 'ready': False,
             'stopped': False, 'closing': False, 'status': None, 'open': None}
    hwnd = None

    def status(message):
        state['text'] = message
        if hwnd:
            user.PostMessageW(hwnd, 0x8001, 0, 0)

    runtime = Runtime(status)

    def open_browser():
        if state['ready'] and not os.environ.get('SHUJUKU_NO_BROWSER'):
            webbrowser.open(runtime.url)

    def worker():
        failure = None
        try:
            runtime.start()
            state['ready'] = True
            user.PostMessageW(hwnd, 0x8001, 0, 0)
            if not stop_event.is_set():
                open_browser()
            stop_event.wait()
        except Exception as error:
            failure = str(error)
            log(f'启动失败：{error}')
            status(str(error))
        finally:
            try:
                runtime.stop()
            except Exception as error:
                log(f'退出失败：{error}')
                state['text'] = '服务退出未完成，请查看日志。'
            if failure:
                state['text'] = failure
            state['stopped'] = True
            user.PostMessageW(hwnd, 0x8002, 0, 0)

    @callback_type
    def procedure(window, message, wparam, lparam):
        if message == 0x0010:  # WM_CLOSE
            if state['stopped']:
                user.DestroyWindow(window)
            elif not state['closing']:
                state['closing'] = True
                stop_event.set()
                user.SetWindowTextW(state['status'], '正在保存并退出，请稍候…')
                user.EnableWindow(state['open'], False)
            return 0
        if message == 0x0002:  # WM_DESTROY
            user.PostQuitMessage(0)
            return 0
        if message == 0x0111:  # WM_COMMAND
            command = wparam & 0xFFFF
            if command == 101:
                open_browser()
            elif command == 102:
                user.PostMessageW(window, 0x0010, 0, 0)
            elif command == 103:
                os.startfile(str(DATA))
            return 0
        if message == 0x8001:
            user.SetWindowTextW(state['status'], state['text'])
            user.EnableWindow(state['open'], state['ready'] and not state['closing'])
            return 0
        if message == 0x8002:
            if state['closing']:
                user.DestroyWindow(window)
            else:
                user.SetWindowTextW(state['status'], '启动未完成，请点击“查看日志”后联系维护者。')
                # The actual error remains in the native text area and log.
                user.MessageBoxW(window, state['text'], '屿账启动提示', 0x10)
            return 0
        if message == 0x8003:
            open_browser()
            return 0
        return user.DefWindowProcW(window, message, wparam, lparam)

    instance = kernel.GetModuleHandleW(None)
    wc = WindowClass(0, procedure, 0, 0, instance, None, None, W.HBRUSH(6), None, name)
    user.RegisterClassW(C.byref(wc))
    hwnd = user.CreateWindowExW(0, name, '屿账 · 应用启动器', 0x00CA0000,
                                300, 250, 550, 245, None, None, instance, None)
    if not hwnd:
        raise C.WinError(C.get_last_error())
    font = gdi.GetStockObject(17)

    def control(kind, text, x, y, width, height, identifier=0):
        child = user.CreateWindowExW(0, kind, text, 0x50000000,
                                    x, y, width, height, hwnd, W.HMENU(identifier), instance, None)
        user.SendMessageW(child, 0x0030, font, 1)
        return child

    control('STATIC', '屿账  |  个人数字资产与订阅管理', 24, 20, 490, 25)
    state['status'] = control('STATIC', state['text'], 24, 58, 490, 50)
    control('STATIC', '关闭浏览器不会退出应用；使用下方“退出应用”安全关闭。', 24, 114, 490, 25)
    state['open'] = control('BUTTON', '打开应用', 24, 151, 120, 32, 101)
    control('BUTTON', '查看日志', 160, 151, 120, 32, 103)
    control('BUTTON', '退出应用', 385, 151, 120, 32, 102)
    user.EnableWindow(state['open'], False)
    user.ShowWindow(hwnd, 5)
    threading.Thread(target=worker, daemon=True).start()
    message = W.MSG()
    while user.GetMessageW(C.byref(message), None, 0, 0) > 0:
        user.TranslateMessage(C.byref(message))
        user.DispatchMessageW(C.byref(message))
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    lock.close()
