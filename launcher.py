"""User-facing launcher for 屿账.

The launcher keeps the course project's browser UI and native-SQL API, while
removing the need for users to know PowerShell, Python, ports, or database
commands.  PyInstaller packages this file as a one-file Windows executable.
"""
from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
import ctypes


APP_NAME = "屿账"
API_PORT = 8000
WEB_PORT = 5173
MYSQL_PORT = 3307
DB_NAME = "subscription_lab"


def resource_root() -> Path:
    """Read bundled files from PyInstaller's extraction directory when frozen."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def data_root() -> Path:
    """Use a user-writable location in the packaged app, project .runtime in dev."""
    configured = os.environ.get("SHUJUKU_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if not getattr(sys, "frozen", False):
        return resource_root() / ".runtime"
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return local_app_data / "Shujuku" / "data"


def configure_environment() -> tuple[Path, Path]:
    root = resource_root()
    runtime = data_root()
    runtime.mkdir(parents=True, exist_ok=True)
    os.environ["SHUJUKU_RUNTIME_DIR"] = str(runtime)
    os.environ["SHUJUKU_PROJECT_ROOT"] = str(root)
    return root, runtime


ROOT, RUNTIME = configure_environment()
CONFIG = RUNTIME / "db.json"
MYSQL_DATA = RUNTIME / "mysql"


def load_config() -> dict:
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    import secrets

    config = {
        "port": MYSQL_PORT,
        "password": secrets.token_urlsafe(24),
        "root_password": secrets.token_urlsafe(24),
    }
    CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def mysql_executable() -> str | None:
    candidates = []
    configured = os.environ.get("SHUJUKU_MYSQLD")
    if configured:
        candidates.append(Path(configured))
    executable_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT
    candidates.extend([
        executable_dir / "mysql" / "bin" / "mysqld.exe",
        ROOT / "mysql" / "bin" / "mysqld.exe",
        Path(r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqld.exe"),
        Path(r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe"),
    ])
    found = shutil.which("mysqld.exe") or shutil.which("mysqld")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def mysql_connect(config: dict, admin: bool = False, database: bool = True):
    import pymysql

    return pymysql.connect(
        host="127.0.0.1",
        port=int(config["port"]),
        user="root" if admin else "lab_app",
        password=config["root_password"] if admin else config["password"],
        database=DB_NAME if database else None,
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=3,
        cursorclass=pymysql.cursors.DictCursor,
    )


def verify_owned(conn: object) -> None:
    identity = configparser.ConfigParser()
    identity.read(MYSQL_DATA / "auto.cnf", encoding="utf-8")
    expected = identity.get("auto", "server-uuid", fallback="")
    with conn.cursor() as cursor:  # type: ignore[attr-defined]
        cursor.execute("SELECT @@server_uuid AS server_uuid")
        actual = cursor.fetchone()["server_uuid"]
    if not expected or actual != expected:
        raise RuntimeError("检测到 3307 端口已有其他数据库实例，已停止启动以保护原有数据。")


def wait_for_mysql(config: dict, process: subprocess.Popen) -> None:
    import pymysql

    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError(f"数据库启动失败，请查看日志：{RUNTIME / 'mysql-console.log'}")
        try:
            with mysql_connect(config, admin=True, database=False):
                return
        except pymysql.err.OperationalError:
            try:
                with pymysql.connect(host="127.0.0.1", port=int(config["port"]), user="root", password="", connect_timeout=1) as fresh:
                    with fresh.cursor() as cursor:
                        cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (config["root_password"],))
                    return
            except pymysql.err.OperationalError:
                time.sleep(0.5)
    raise RuntimeError("数据库启动超时，请查看日志后重试。")


def ensure_database(log) -> subprocess.Popen:
    executable = mysql_executable()
    if not executable:
        raise RuntimeError(
            "没有找到 MySQL 服务器。请先安装 MySQL 8.0 或更高版本，\n"
            "安装完成后再次双击屿账.exe；其他电脑也只需完成这一次安装。"
        )
    config = load_config()
    MYSQL_DATA.mkdir(parents=True, exist_ok=True)
    if not (MYSQL_DATA / "mysql").exists():
        result = subprocess.run(
            [executable, "--no-defaults", "--initialize-insecure", f"--datadir={MYSQL_DATA.as_posix()}", "--console"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        (RUNTIME / "mysql-init.log").write_bytes(result.stdout or b"")
        if result.returncode:
            raise RuntimeError(f"数据库初始化失败，请查看日志：{RUNTIME / 'mysql-init.log'}")
    with socket.socket() as probe:
        occupied = probe.connect_ex(("127.0.0.1", int(config["port"]))) == 0
    if occupied:
        process = None
        with mysql_connect(config, admin=True, database=False) as connection:
            verify_owned(connection)
    else:
        log_file = open(RUNTIME / "mysql-console.log", "ab")
        process = subprocess.Popen(
            [
                executable,
                "--no-defaults",
                "--datadir=.",
                "--log-error=server.err",
                "--pid-file=server.pid",
                "--tmpdir=.",
                "--bind-address=127.0.0.1",
                f"--port={config['port']}",
                "--mysqlx=0",
                "--character-set-server=utf8mb4",
                "--collation-server=utf8mb4_0900_ai_ci",
                "--console",
            ],
            cwd=MYSQL_DATA,
            stdout=log_file,
            stderr=log_file,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        (RUNTIME / "mysql.pid").write_text(str(process.pid), encoding="utf-8")
        wait_for_mysql(config, process)
    with mysql_connect(config, admin=True, database=False) as connection:
        verify_owned(connection)
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
            cursor.execute("CREATE USER IF NOT EXISTS 'lab_app'@'localhost' IDENTIFIED BY %s", (config["password"],))
            cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {DB_NAME}.* TO 'lab_app'@'localhost'")
        connection.commit()
    with mysql_connect(config, admin=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            if not cursor.fetchall():
                for filename in ("001_schema.sql", "002_seed.sql"):
                    sql = (ROOT / "database" / filename).read_text(encoding="utf-8")
                    for statement in sql.split(";"):
                        if statement.strip():
                            cursor.execute(statement)
                connection.commit()
                log("首次启动已准备示例数据。")
            else:
                log("已发现现有项目数据，保留原数据。")
    return process


def start_services(log):
    import uvicorn

    os.environ["SHUJUKU_RUNTIME_DIR"] = str(RUNTIME)
    os.environ["SHUJUKU_PROJECT_ROOT"] = str(ROOT)
    from backend.app import app

    api_config = uvicorn.Config(app, host="127.0.0.1", port=API_PORT, log_level="warning", access_log=False)
    api_server = uvicorn.Server(api_config)
    api_thread = threading.Thread(target=api_server.run, name="shujuku-api", daemon=True)
    api_thread.start()
    for _ in range(40):
        try:
            with socket.create_connection(("127.0.0.1", API_PORT), timeout=0.2):
                break
        except OSError:
            time.sleep(0.25)
    else:
        api_server.should_exit = True
        raise RuntimeError("后端服务启动超时，请查看运行日志。")

    from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            return

    web_server = ThreadingHTTPServer(("127.0.0.1", WEB_PORT), lambda *args, **kwargs: QuietHandler(*args, directory=str(ROOT / "frontend"), **kwargs))
    web_thread = threading.Thread(target=web_server.serve_forever, name="shujuku-web", daemon=True)
    web_thread.start()
    log("服务已启动。")
    return api_server, web_server


def shutdown(api_server, web_server, mysql_process, log):
    if web_server:
        web_server.shutdown()
        web_server.server_close()
    if api_server:
        api_server.should_exit = True
    if mysql_process and mysql_process.poll() is None:
        try:
            config = load_config()
            with mysql_connect(config, admin=True, database=False) as connection:
                verify_owned(connection)
                with connection.cursor() as cursor:
                    cursor.execute("SHUTDOWN")
        except Exception as error:  # best effort during application close
            log(f"数据库正在由系统回收：{error}")


def user_message(title: str, message: str, error: bool = True) -> None:
    """Show a native Windows message without requiring tkinter or a console."""
    if os.name == "nt":
        flags = 0x10 if error else 0x40
        ctypes.windll.user32.MessageBoxW(0, message, title, flags)


def write_launcher_log(message: str) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / "launcher.log").open("a", encoding="utf-8") as stream:
        stream.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + message + "\n")


def ports_ready() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", API_PORT), timeout=1):
            pass
        with socket.create_connection(("127.0.0.1", WEB_PORT), timeout=1):
            pass
        return True
    except OSError:
        return False


def main():
    api_server = web_server = mysql_process = None
    try:
        write_launcher_log("正在准备项目数据库…")
        mysql_process = ensure_database(write_launcher_log)
        if ports_ready():
            write_launcher_log("项目服务已经运行，直接打开浏览器。")
            webbrowser.open(f"http://127.0.0.1:{WEB_PORT}")
            while True:
                time.sleep(60)
        write_launcher_log("正在启动应用服务…")
        api_server, web_server = start_services(write_launcher_log)
        webbrowser.open(f"http://127.0.0.1:{WEB_PORT}")
        write_launcher_log("项目已启动。关闭此进程即可停止本项目服务。")
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        write_launcher_log(f"启动失败：{error}")
        user_message("屿账启动提示", f"屿账没有启动完成：\n\n{error}\n\n详细日志：{RUNTIME / 'launcher.log'}")
    finally:
        if api_server or web_server or mysql_process:
            shutdown(api_server, web_server, mysql_process, write_launcher_log)


if __name__ == "__main__":
    main()
