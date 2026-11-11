"""End-to-end Windows EXE test, native buttons, isolated data, real MySQL."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / '.runtime' / ('exe验收-' + uuid.uuid4().hex[:8])
EXE = ROOT / 'release/屿账/屿账.exe'
user = C.WinDLL('user32')
user.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
user.IsWindow.argtypes = [W.HWND]
user.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
CHECKS = []


def check(name):
    CHECKS.append(name)
    print('PASS:', name, flush=True)


def windows(process):
    found = []
    children = subprocess.run(['powershell', '-NoProfile', '-Command',
        f'Get-CimInstance Win32_Process -Filter "ParentProcessId={process.pid}" | Select-Object -ExpandProperty ProcessId'],
        capture_output=True, text=True)
    pids = {process.pid} | {int(n) for n in children.stdout.split() if n.isdigit()}
    @C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def callback(hwnd, _):
        pid = W.DWORD()
        user.GetWindowThreadProcessId(hwnd, C.byref(pid))
        title = C.create_unicode_buffer(256)
        user.GetWindowTextW(hwnd, title, 256)
        if pid.value in pids and title.value == '屿账 · 应用启动器':
            found.append(hwnd)
        return True
    user.EnumWindows(callback, 0)
    return found


def request(path, body=None, method='GET'):
    req = urllib.request.Request('http://127.0.0.1:8000/api/' + path,
        data=json.dumps(body).encode() if body else None,
        headers={'Content-Type':'application/json'}, method=method)
    with urllib.request.urlopen(req, timeout=3) as response:
        return json.load(response)


def start():
    env = os.environ.copy()
    env['SHUJUKU_DATA_DIR'] = str(DATA)
    env['SHUJUKU_NO_BROWSER'] = '1'
    # Deliberately remove Python and MySQL paths from the child's PATH.
    env['PATH'] = os.path.join(os.environ['SystemRoot'], 'System32')
    process = subprocess.Popen([str(EXE)], cwd=EXE.parent, env=env,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    deadline = time.monotonic() + 100
    while time.monotonic() < deadline:
        assert process.poll() is None, f'EXE stopped early: {process.returncode}'
        try:
            if request('health')['status'] == 'ok':
                with urllib.request.urlopen('http://127.0.0.1:5173', timeout=2) as response:
                    if response.status == 200:
                        assert windows(process), 'No visible native launcher window'
                        return process
        except (OSError, ValueError):
            pass
        time.sleep(.4)
    log = (DATA / 'launcher.log').read_text(encoding='utf-8') if (DATA / 'launcher.log').exists() else ''
    raise AssertionError('EXE startup timeout: ' + log)


def stop(process):
    found = windows(process)
    assert found, 'Native launcher window missing'
    user.PostMessageW(found[0], 0x0111, 102, 0)  # actual Exit button
    process.wait(timeout=45)
    assert process.returncode == 0, process.returncode
    for port in (8000, 5173, 3307):
        with socket.socket() as sock:
            assert sock.connect_ex(('127.0.0.1', port)) != 0, f'Leaked service on {port}'


if __name__ == '__main__':
    process = None
    try:
        process = start()
        check('冻结EXE独立启动，无Python/MySQL PATH依赖；原生窗口可见')
        assert float(request('dashboard')['spending']) == 175
        check('随包MySQL中文路径、首次初始化、真实接口和静态页面')
        payment = request('payments', {'label':'重启保留验证','channel':'other'}, 'POST')
        env = os.environ.copy()
        env.update(SHUJUKU_DATA_DIR=str(DATA), SHUJUKU_NO_BROWSER='1')
        second = subprocess.Popen([str(EXE)], cwd=EXE.parent, env=env,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        assert second.wait(timeout=15) == 0
        assert request('health')['status'] == 'ok'
        check('重复双击复用已运行实例，没有新建后台服务')
        stop(process)
        process = None
        check('点击退出应用正常关闭窗口、API、前端及项目MySQL')
        process = start()
        assert any(p['id'] == payment['id'] for p in request('payments'))
        assert float(request('dashboard')['spending']) == 175
        request('payments/' + str(payment['id']), method='DELETE')
        check('再次双击成功；用户新增数据保留且未重复导入示例')
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page(viewport={'width':1100,'height':800})
            page.goto('http://127.0.0.1:5173')
            page.locator('#spending').wait_for()
            from playwright.sync_api import expect
            expect(page.locator('#spending')).to_have_text('¥175.00')
            page.screenshot(path=str(ROOT / 'docs/evidence/launcher-browser.png'), full_page=True)
            browser.close()
        check('冻结版服务在真实浏览器正确呈现175元仪表盘')
        stop(process)
        process = None
        check('第二次退出同样释放所有项目端口')
        (ROOT / 'docs/evidence/launcher-exe.json').write_text(
            json.dumps({'passed':True,'checks':CHECKS,'data_scope':'isolated test directory',
                        'executable':'release/屿账/屿账.exe'}, ensure_ascii=False, indent=2)+'\n',
            encoding='utf-8', newline='\n')
    finally:
        if process and process.poll() is None:
            found = windows(process)
            if found:
                user.PostMessageW(found[0], 0x0010, 0, 0)
