"""Real MySQL + HTTP integration checks. Creates and removes only a unique scratch DB."""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.dev import connect
import pymysql

report = {'checks': [], 'queries': {}}


def record(name, detail=None):
    report['checks'].append({'name': name, 'passed': True, 'detail': detail})
    print('PASS', name)


def request(path, method='GET', body=None, expected=200):
    req = urllib.request.Request('http://127.0.0.1:8000/api' + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status, result = response.status, json.load(response)
    except urllib.error.HTTPError as response:
        status, result = response.code, json.load(response)
    assert status == expected, (method, path, status, result)
    return result


def check_database():
    scratch = 'subscription_verify_' + uuid.uuid4().hex[:12]
    conn = connect(admin=True, database=False)
    created = False
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE `{scratch}` CHARACTER SET utf8mb4')
            created = True
            conn.select_db(scratch)
            for filename in ['001_schema.sql', '002_seed.sql']:
                for statement in (ROOT / 'database' / filename).read_text(encoding='utf-8').split(';'):
                    if statement.strip():
                        cur.execute(statement)
            conn.commit()
            cur.execute('SHOW TABLES')
            assert len(cur.fetchall()) == 8
            record('空开发库重建 8 表和种子数据')
            cur.execute('SELECT VERSION() AS version')
            report['mysql_version'] = cur.fetchone()['version']
            negative = [
                ('非法外键拒绝', "INSERT INTO subscription(payment_id,name,category,amount,cycle_months,next_billing_date) VALUES(99999,'bad','other',1,1,'2026-11-10')"),
                ('同用户支付名唯一', "INSERT INTO payment_method(user_id,label,channel) VALUES(1,'日常支付','other')"),
                ('非空约束拒绝', "INSERT INTO payment_method(user_id,label,channel) VALUES(1,NULL,'other')"),
                ('负金额拒绝', "UPDATE subscription SET amount=-1 WHERE id=1"),
                ('非法周期拒绝', "UPDATE subscription SET cycle_months=2 WHERE id=1"),
                ('非法预算月首拒绝', "INSERT INTO budget_control(user_id,month_start,amount) VALUES(1,'2026-12-02',100)"),
                ('取消事件不得记正支出', "INSERT INTO billing_history(subscription_id,payment_id,event_type,amount,occurred_on,event_key) VALUES(1,NULL,'CANCEL',1,'2026-11-10','invalid-cancel')"),
                ('历史引用保护删除', 'DELETE FROM subscription WHERE id=1'),
            ]
            for name, sql in negative:
                try:
                    cur.execute(sql)
                except pymysql.MySQLError as exc:
                    assert exc.args[0] in (1048, 1062, 1451, 1452, 3819), exc.args
                    conn.rollback()
                    record(name, {'mysql_error': exc.args[0]})
                else:
                    conn.rollback()
                    raise AssertionError(name + ' unexpectedly accepted')
            source = (ROOT / 'database/003_queries.sql').read_text(encoding='utf-8')
            queries = [q for q in source.split(';') if q.strip()]
            for i, query in enumerate(queries, 1):
                cur.execute(query)
                report['queries'][f'Q{i}'] = cur.fetchall()
            assert len(report['queries']['Q1']) == 5
            assert [r['total'] for r in report['queries']['Q2']] == [Decimal('46'), Decimal('129')]
            assert [r['id'] for r in report['queries']['Q3']] == [3, 4]
            assert sum(r['total'] for r in report['queries']['Q4']) == Decimal('175')
            record('JOIN / GROUP BY / EXISTS 查询结果', 'Q2=46/129；Q3=资产3/4；Q4总额175')
            cur.execute('SELECT amount FROM subscription WHERE id=1')
            old = cur.fetchone()['amount']
            cur.execute('UPDATE subscription SET amount=88 WHERE id=1')
            conn.rollback()
            cur.execute('SELECT amount FROM subscription WHERE id=1')
            assert cur.fetchone()['amount'] == old
            record('基础连接事务回滚', '仅连接回滚验证，不是取消业务事务')
            cur.execute("SELECT COUNT(*) AS n FROM information_schema.triggers WHERE trigger_schema=%s", (scratch,))
            assert cur.fetchone()['n'] == 0
            record('阶段范围核实', '0个触发器；高级功能只有设计')
    finally:
        if created:
            conn.select_db('mysql')
            with conn.cursor() as cur:
                cur.execute(f'DROP DATABASE `{scratch}`')
        conn.close()


def check_http():
    health = request('/health')
    assert health['database'] == 'MySQL'
    baseline = request('/dashboard')
    assert Decimal(baseline['spending']) == Decimal('175')
    assert Decimal(baseline['budget']) == Decimal('200')
    assert baseline['active_count'] == 4
    assert len([a for a in baseline['assets'] if a['usage_state'] == 'idle']) == 2
    assert len(request('/calendar')) == 4
    record('真实 API 种子统计', '175元/200元；4活跃；2闲置；4续费日程')
    empty = request('/dashboard?month=2027-01')
    assert Decimal(empty['spending']) == 0 and empty['budget'] is None
    assert request('/calendar?month=2027-01') == []
    record('无流水/无预算/空日历月份')
    request('/dashboard?month=2026-13', expected=422)
    request('/dashboard?month=0001-01', expected=422)
    request('/subscriptions/1', 'PATCH', {}, expected=422)
    request('/subscriptions/1', 'PATCH', {'amount':None}, expected=422)
    request('/subscriptions/1', 'PATCH', {'status':'cancelled'}, expected=422)
    request('/subscriptions/999999', 'PATCH', {'amount':'2.00'}, expected=404)
    request('/subscriptions/5', 'PATCH', {'amount':'2.00'}, expected=409)
    request('/subscriptions/1', 'DELETE', expected=409)
    request('/payments/1', 'DELETE', expected=409)
    record('非法请求、越界月份、取消状态及引用保护')
    payment = sub = None
    try:
        token = uuid.uuid4().hex[:8]
        payment = request('/payments', 'POST', {'label':'集成验证-'+token,'channel':'other'}, 201)
        request('/payments', 'POST', {'label':payment['label'],'channel':'other'}, 409)
        body = {'payment_id':payment['id'],'name':"验证' OR 1=1 -- <script>",'category':'other',
                'amount':'12.34','cycle_months':1,'next_billing_date':'2026-11-20','auto_renew':True}
        request('/subscriptions', 'POST', {**body,'payment_id':999999}, 422)
        request('/subscriptions', 'POST', {**body,'amount':'1.001'}, 422)
        sub = request('/subscriptions', 'POST', body, 201)
        saved = next(s for s in request('/subscriptions') if s['id'] == sub['id'])
        assert saved['name'] == body['name']
        assert any(e['id'] == sub['id'] for e in request('/calendar'))
        request(f"/subscriptions/{sub['id']}", 'PATCH', {'amount':'15.50','auto_renew':False})
        saved = next(s for s in request('/subscriptions') if s['id'] == sub['id'])
        assert Decimal(saved['amount']) == Decimal('15.50') and not saved['auto_renew']
        assert not any(e['id'] == sub['id'] for e in request('/calendar'))
        record('支付创建→订阅创建→修改→日历变化', '特殊名称按字面保存；小数精度校验')
    finally:
        if sub:
            request(f"/subscriptions/{sub['id']}", 'DELETE')
        if payment:
            request(f"/payments/{payment['id']}", 'DELETE')
    assert request('/dashboard')['active_count'] == baseline['active_count']
    record('清理测试记录后恢复基线')


if __name__ == '__main__':
    check_database()
    check_http()
    target = ROOT / 'docs/evidence'
    target.mkdir(exist_ok=True)
    (target / 'week8-integration.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(f'{len(report["checks"])} checks passed; evidence saved.')
