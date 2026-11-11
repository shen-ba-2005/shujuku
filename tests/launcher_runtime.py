"""Exercise the bundled MySQL executable in the real Chinese release path."""
import json
from pathlib import Path
import os
import sys
import uuid
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['SHUJUKU_DATA_DIR'] = str(ROOT / '.runtime' / ('启动验证-' + uuid.uuid4().hex[:8]))
os.environ['SHUJUKU_MYSQLD'] = str(ROOT / 'release/屿账/mysql/bin/mysqld.exe')
from desktop_runtime import Runtime

runtime = Runtime(print)
try:
    runtime.start()
    with urllib.request.urlopen('http://127.0.0.1:8000/api/dashboard') as response:
        result = json.load(response)
    assert float(result['spending']) == 175
    with urllib.request.urlopen('http://127.0.0.1:5173') as response:
        assert response.status == 200
    print('PASS: bundled MySQL path, first-run seed, real API and frontend')
finally:
    runtime.stop()
