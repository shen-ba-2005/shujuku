"""Manage the project-owned MySQL and HTTP processes. No existing service is changed."""
import argparse
import configparser
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
CONFIG = RUNTIME / 'db.json'
PORT = 3307
DB_NAME = 'subscription_lab'


def hidden():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def connect(config=None, admin=False, database=True):
    import pymysql
    config = config or json.loads(CONFIG.read_text(encoding='utf-8'))
    return pymysql.connect(host='127.0.0.1', port=config['port'],
                           user='root' if admin else 'lab_app',
                           password=config['root_password'] if admin else config['password'],
                           database=DB_NAME if database else None, charset='utf8mb4',
                           autocommit=False, connect_timeout=3,
                           cursorclass=pymysql.cursors.DictCursor)


def verify_owned(conn):
    identity = configparser.ConfigParser()
    identity.read(RUNTIME / 'mysql' / 'auto.cnf', encoding='utf-8')
    expected = identity.get('auto', 'server-uuid', fallback='')
    with conn.cursor() as cur:
        cur.execute('SELECT @@server_uuid AS server_uuid')
        actual = cur.fetchone()['server_uuid']
    if not expected or actual != expected:
        raise SystemExit('Database identity mismatch; operation refused.')


def init_db():
    RUNTIME.mkdir(exist_ok=True)
    executable = shutil.which('mysqld')
    if not executable:
        raise SystemExit('mysqld not found. Install MySQL 8.0.16+ and add its bin directory to PATH.')
    if not CONFIG.exists():
        cfg = {'port': PORT, 'password': secrets.token_urlsafe(24),
               'root_password': secrets.token_urlsafe(24)}
        CONFIG.write_text(json.dumps(cfg), encoding='utf-8')
    cfg = json.loads(CONFIG.read_text(encoding='utf-8'))
    data = RUNTIME / 'mysql'
    if not (data / 'mysql').exists():
        result = subprocess.run([executable, '--no-defaults', '--initialize-insecure',
                                 f'--datadir={data.as_posix()}', '--console'], cwd=ROOT, **hidden(),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (RUNTIME / 'mysql-init.log').write_bytes(result.stdout)
        if result.returncode:
            raise SystemExit('MySQL initialization failed: see .runtime/mysql-init.log')
    # Never attach to another server on the configured port.
    with socket.socket() as probe:
        occupied = probe.connect_ex(('127.0.0.1', cfg['port'])) == 0
    if occupied:
        with connect(cfg, admin=True, database=False) as conn:
            verify_owned(conn)
    else:
        log = open(RUNTIME / 'mysql-console.log', 'ab')
        proc = subprocess.Popen([executable, '--no-defaults', '--datadir=.',
                                 '--log-error=server.err', '--pid-file=server.pid', '--tmpdir=.',
                                 '--bind-address=127.0.0.1', f"--port={cfg['port']}",
                                 '--mysqlx=0', '--character-set-server=utf8mb4',
                                 '--collation-server=utf8mb4_0900_ai_ci', '--console'],
                                cwd=data, stdout=log, stderr=log, **hidden())
        (RUNTIME / 'mysql.pid').write_text(str(proc.pid))
        import pymysql
        for _ in range(60):
            if proc.poll() is not None:
                raise SystemExit('MySQL stopped: see .runtime/mysql-console.log')
            try:
                with connect(cfg, admin=True, database=False):
                    break
            except pymysql.err.OperationalError:
                try:
                    with pymysql.connect(host='127.0.0.1', port=cfg['port'], user='root',
                                         password='', connect_timeout=1) as fresh:
                        with fresh.cursor() as cur:
                            cur.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s",
                                        (cfg['root_password'],))
                    break
                except pymysql.err.OperationalError:
                    time.sleep(0.5)
        else:
            raise SystemExit('MySQL readiness timed out.')
    with connect(cfg, admin=True, database=False) as conn:
        verify_owned(conn)
        with conn.cursor() as cur:
            cur.execute('CREATE DATABASE IF NOT EXISTS subscription_lab CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
            cur.execute("CREATE USER IF NOT EXISTS 'lab_app'@'localhost' IDENTIFIED BY %s", (cfg['password'],))
            cur.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON subscription_lab.* TO 'lab_app'@'localhost'")
        conn.commit()
    print(f'Project MySQL ready at 127.0.0.1:{cfg["port"]} ({DB_NAME})')


def seed():
    # Deliberately refuse to erase or overwrite existing coursework data.
    with connect(admin=True) as conn:
        verify_owned(conn)
        with conn.cursor() as cur:
            cur.execute('SHOW TABLES')
            if cur.fetchall():
                raise SystemExit('Database is not empty. Seed refused; no existing data was changed.')
            for file in ['001_schema.sql', '002_seed.sql']:
                source = (ROOT / 'database' / file).read_text(encoding='utf-8')
                for statement in source.split(';'):
                    if statement.strip():
                        cur.execute(statement)
                print(f'Applied {file}')
        conn.commit()


def serve():
    RUNTIME.mkdir(exist_ok=True)
    processes = [
        ('api', [sys.executable, '-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1', '--port', '8000']),
        ('web', [sys.executable, '-m', 'http.server', '5173', '--bind', '127.0.0.1', '--directory', str(ROOT / 'frontend')]),
    ]
    for name, command in processes:
        port = 8000 if name == 'api' else 5173
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                raise SystemExit(f'Port {port} is occupied; refusing to start a duplicate {name}.')
        log = open(RUNTIME / f'{name}.log', 'ab')
        proc = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=log, **hidden())
        (RUNTIME / f'{name}.pid').write_text(str(proc.pid))
        time.sleep(0.5)
        if proc.poll() is not None:
            raise SystemExit(f'{name} failed: see .runtime/{name}.log')
    print('Frontend: http://127.0.0.1:5173  API docs: http://127.0.0.1:8000/docs')


def stop():
    # Verify command ownership before stopping only the two project-owned HTTP processes.
    if os.name != 'nt':
        raise SystemExit('Use process manager on non-Windows hosts; no process was stopped.')
    for name, marker in [('api', 'backend.app:app'), ('web', str(ROOT / 'frontend'))]:
        path = RUNTIME / f'{name}.pid'
        if not path.exists():
            continue
        pid = int(path.read_text())
        query = subprocess.run(['powershell', '-NoProfile', '-Command',
                                f'(Get-CimInstance Win32_Process -Filter "ProcessId = {pid}").CommandLine'],
                               capture_output=True, text=True, **hidden())
        if marker in query.stdout:
            subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], check=True, **hidden())
    try:
        with connect(admin=True, database=False) as conn:
            verify_owned(conn)
            with conn.cursor() as cur:
                cur.execute('SHUTDOWN')
    except OSError:
        pass
    print('Project processes stopped.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init-db', 'seed', 'serve', 'stop'])
    action = parser.parse_args().action
    {'init-db': init_db, 'seed': seed, 'serve': serve, 'stop': stop}[action]()
