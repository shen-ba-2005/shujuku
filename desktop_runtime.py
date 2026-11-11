"""Local application lifecycle. No GUI dependency or ORM."""
from __future__ import annotations
import configparser
import ctypes
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
FROZEN = bool(getattr(sys, 'frozen', False))
INSTALL = Path(sys.executable).resolve().parent if FROZEN else ROOT
DATA = Path(os.environ.get('SHUJUKU_DATA_DIR') or (
    str(Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Shujuku' / 'data')
    if FROZEN else str(ROOT / '.runtime'))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
os.environ['SHUJUKU_PROJECT_ROOT'] = str(ROOT)
os.environ['SHUJUKU_RUNTIME_DIR'] = str(DATA)


def log(message):
    with (DATA / 'launcher.log').open('a', encoding='utf-8') as stream:
        stream.write(time.strftime('[%Y-%m-%d %H:%M:%S] ') + message + '\n')


def connect(admin=True, database=False):
    from scripts.dev import connect as db_connect
    return db_connect(admin=admin, database=database)


def verify_owned(connection):
    identity = configparser.ConfigParser()
    identity.read(DATA / 'mysql' / 'auto.cnf', encoding='utf-8')
    with connection.cursor() as cursor:
        cursor.execute('SELECT @@server_uuid AS uuid')
        if cursor.fetchone()['uuid'] != identity.get('auto', 'server-uuid', fallback=''):
            raise RuntimeError('数据库端口已被其他应用使用，已停止操作以保留原有数据。')


class Runtime:
    def __init__(self, status):
        self.status = status
        self.mysql = self.api = self.api_thread = self.web = None
        self.api_port, self.web_port = 8000, 5173
        self.url = ''
        self.instance_id = secrets.token_urlsafe(16)

    def update(self, message):
        log(message)
        self.status(message)

    def start(self):
        for port in (self.api_port, self.web_port):
            with socket.socket() as probe:
                try:
                    probe.bind(('127.0.0.1', port))
                except OSError:
                    raise RuntimeError('应用端口正在使用中。请关闭其他屿账或开发窗口，再双击打开。')
        self.update('正在准备数据，首次启动请稍候…')
        self.start_database()
        self.update('正在打开应用…')
        self.start_services()
        self.url = f'http://127.0.0.1:{self.web_port}'
        self.update('已启动。请在浏览器中使用；关闭此窗口即可退出。')

    def start_database(self):
        mysql_dir = DATA / 'mysql'
        mysql_dir.mkdir(exist_ok=True)
        executable = INSTALL / 'mysql' / 'bin' / 'mysqld.exe'
        if not FROZEN and os.environ.get('SHUJUKU_MYSQLD'):
            executable = Path(os.environ['SHUJUKU_MYSQLD'])
        if not executable.is_file() and not FROZEN:
            executable = Path(r'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqld.exe')
        if not executable.is_file():
            raise RuntimeError('应用文件不完整：缺少 mysql 文件夹。请重新解压整个发布包，不要只复制 exe。')
        config_file = DATA / 'db.json'
        if not config_file.exists():
            config_file.write_text(json.dumps({
                'port': 3307, 'password': secrets.token_urlsafe(24),
                'root_password': secrets.token_urlsafe(24)}), encoding='utf-8')
        config = json.loads(config_file.read_text(encoding='utf-8'))
        basedir = executable.resolve().parent.parent.as_posix()
        # MySQL's Windows path options use the Windows system code page.
        # Keep argv[0] ASCII and write path options using that same encoding.
        (DATA / 'launcher.cnf').write_text(
            '[mysqld]\n' + f'basedir="{basedir}"\n' +
            f'datadir="{mysql_dir.as_posix()}"\n' +
            f'lc-messages-dir="{(executable.resolve().parent.parent / "share").as_posix()}"\n' +
            'log-error=server.err\npid-file=server.pid\ntmpdir=.\n'
            'bind-address=127.0.0.1\n' + f'port={config["port"]}\n' +
            'mysqlx=0\ncharacter-set-server=utf8mb4\n'
            'collation-server=utf8mb4_0900_ai_ci\n', encoding='mbcs' if os.name == 'nt' else 'utf-8')
        if os.name == 'nt' and FROZEN:
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        kwargs = dict(executable=str(executable), cwd=DATA,
                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        with socket.socket() as probe:
            occupied = probe.connect_ex(('127.0.0.1', config['port'])) == 0
        if occupied:
            try:
                with connect() as connection:
                    verify_owned(connection)
            except Exception as error:
                raise RuntimeError('项目数据库端口已被占用，请先关闭其他屿账窗口。') from error
        else:
            if not (mysql_dir / 'mysql').exists():
                result = subprocess.run(
                    ['mysqld', '--defaults-file=launcher.cnf', '--initialize-insecure', '--console'],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, **kwargs)
                (DATA / 'mysql-init.log').write_bytes(result.stdout)
                if result.returncode:
                    raise RuntimeError('首次准备数据失败。请点击“查看日志”，将日志提供给维护者。')
            with (DATA / 'mysql-console.log').open('ab') as output:
                self.mysql = subprocess.Popen(
                    ['mysqld', '--defaults-file=launcher.cnf', '--console'],
                    stdout=output, stderr=output, **kwargs)
            import pymysql
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if self.mysql.poll() is not None:
                    raise RuntimeError('本地数据库未能启动。请点击“查看日志”，数据会保留。')
                try:
                    with connect():
                        break
                except pymysql.err.OperationalError:
                    try:
                        with pymysql.connect(host='127.0.0.1', port=config['port'], user='root',
                                             password='', connect_timeout=1) as fresh:
                            with fresh.cursor() as cursor:
                                cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (config['root_password'],))
                        break
                    except pymysql.err.OperationalError:
                        time.sleep(.25)
            else:
                raise RuntimeError('准备数据超时，请退出后重试。')
        with connect() as connection:
            verify_owned(connection)
            with connection.cursor() as cursor:
                cursor.execute('CREATE DATABASE IF NOT EXISTS subscription_lab CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
                cursor.execute("CREATE USER IF NOT EXISTS 'lab_app'@'localhost' IDENTIFIED BY %s", (config['password'],))
                cursor.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON subscription_lab.* TO 'lab_app'@'localhost'")
            connection.commit()
        with connect(database=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SHOW TABLES')
                if not cursor.fetchall():
                    for filename in ('001_schema.sql', '002_seed.sql'):
                        for statement in (ROOT / 'database' / filename).read_text(encoding='utf-8').split(';'):
                            if statement.strip():
                                cursor.execute(statement)
                    connection.commit()
                    log('首次准备示例数据完成。')
                else:
                    log('保留已有数据，未重复导入。')

    def start_services(self):
        import uvicorn
        from backend.app import app
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        from functools import partial

        @app.get('/api/launcher-identity', include_in_schema=False)
        def identity():
            return {'instance': self.instance_id}

        self.api = uvicorn.Server(uvicorn.Config(
            app, host='127.0.0.1', port=self.api_port, log_config=None,
            log_level='warning', access_log=False, loop='asyncio', http='h11'))
        self.api_thread = threading.Thread(target=self.api.run, daemon=True)
        self.api_thread.start()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{self.api_port}/api/launcher-identity', timeout=1) as response:
                    if json.load(response)['instance'] != self.instance_id:
                        raise RuntimeError('应用端口冲突，请关闭其他屿账窗口。')
                with urllib.request.urlopen(f'http://127.0.0.1:{self.api_port}/api/health', timeout=2) as response:
                    if json.load(response)['status'] == 'ok':
                        break
            except (OSError, ValueError, KeyError):
                if not self.api_thread.is_alive():
                    raise RuntimeError('应用服务启动失败，请查看日志。')
                time.sleep(.2)
        else:
            raise RuntimeError('应用服务准备超时，请退出后重试。')

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        self.web = ThreadingHTTPServer(('127.0.0.1', self.web_port), partial(Handler, directory=str(ROOT / 'frontend')))
        threading.Thread(target=self.web.serve_forever, daemon=True).start()

    def stop(self):
        self.update('正在保存并退出，请稍候…')
        if self.web:
            self.web.shutdown()
            self.web.server_close()
        if self.api:
            self.api.should_exit = True
        if self.api_thread:
            self.api_thread.join(timeout=10)
        if self.mysql and self.mysql.poll() is None:
            with connect() as connection:
                verify_owned(connection)
                with connection.cursor() as cursor:
                    cursor.execute('SHUTDOWN')
            self.mysql.wait(timeout=30)
        log('项目服务已安全退出。')
