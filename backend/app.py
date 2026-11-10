"""Week-8 API: parameterized native MySQL SQL only; no ORM."""
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
import logging
from pathlib import Path
import sys
from typing import Annotated, Literal

import pymysql
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.dev import connect

app = FastAPI(title='订阅与数字资产 · 第 8 周 API', version='0.8.0')
app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:5173', 'http://localhost:5173'],
                   allow_methods=['GET', 'POST', 'PATCH', 'DELETE'], allow_headers=['Content-Type'])
DEMO_TODAY = date(2026, 11, 10)
USER_ID = 1  # Local, single-user demonstration only. Authentication is not implemented.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Money = Annotated[Decimal, Field(gt=0, le=Decimal('99999999.99'), max_digits=10, decimal_places=2)]
Category = Literal['productivity', 'entertainment', 'storage', 'learning', 'other']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PaymentInput(StrictModel):
    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    channel: Literal['bank', 'alipay', 'wechat', 'other']
    last_four: Annotated[str, StringConstraints(pattern=r'^\d{4}$')] | None = None


class SubscriptionInput(StrictModel):
    payment_id: int = Field(gt=0)
    name: Name
    category: Category
    amount: Money
    cycle_months: Literal[1, 3, 6, 12] = 1
    next_billing_date: date
    auto_renew: bool = True


class SubscriptionPatch(StrictModel):
    name: Name | None = None
    amount: Money | None = None
    next_billing_date: date | None = None
    auto_renew: bool | None = None

    @model_validator(mode='after')
    def require_changes(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('至少提供一个有效修改字段，不接受 null')
        return self


@contextmanager
def transaction():
    conn = connect()
    try:
        conn.begin()
        with conn.cursor() as cursor:
            yield cursor
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.exception_handler(pymysql.MySQLError)
async def db_error(_request, exc):
    if isinstance(exc, pymysql.err.IntegrityError):
        return JSONResponse(status_code=409, content={'detail': '名称重复或记录仍被引用，请检查后重试'})
    logging.exception('MySQL operation failed', exc_info=exc)
    return JSONResponse(status_code=503, content={'detail': '数据库暂不可用，请检查项目数据库是否启动'})


@app.get('/api/health')
def health():
    with transaction() as cur:
        cur.execute('SELECT VERSION() AS version')
        row = cur.fetchone()
    return {'status': 'ok', 'database': 'MySQL', 'version': row['version'], 'stage': 'week-8',
            'demo_today': DEMO_TODAY}


@app.get('/api/payments')
def payments():
    with transaction() as cur:
        cur.execute('SELECT id,label,channel,last_four FROM payment_method WHERE user_id=%s ORDER BY id', (USER_ID,))
        return cur.fetchall()


@app.post('/api/payments', status_code=201)
def create_payment(data: PaymentInput):
    with transaction() as cur:
        cur.execute('INSERT INTO payment_method(user_id,label,channel,last_four) VALUES (%s,%s,%s,%s)',
                    (USER_ID, data.label, data.channel, data.last_four))
        return {'id': cur.lastrowid, **data.model_dump()}


@app.delete('/api/payments/{payment_id}')
def delete_payment(payment_id: int):
    with transaction() as cur:
        cur.execute('DELETE FROM payment_method WHERE id=%s AND user_id=%s', (payment_id, USER_ID))
        if not cur.rowcount:
            raise HTTPException(404, '支付方式不存在')
    return {'deleted': payment_id}


@app.get('/api/subscriptions')
def subscriptions():
    with transaction() as cur:
        cur.execute('''SELECT s.id,s.name,s.category,s.amount,s.cycle_months,s.next_billing_date,
                       s.status,s.auto_renew,s.payment_id,p.label AS payment_label
                       FROM subscription s JOIN payment_method p ON p.id=s.payment_id
                       WHERE p.user_id=%s ORDER BY s.id''', (USER_ID,))
        return cur.fetchall()


@app.post('/api/subscriptions', status_code=201)
def create_subscription(data: SubscriptionInput):
    with transaction() as cur:
        cur.execute('SELECT id FROM payment_method WHERE id=%s AND user_id=%s FOR SHARE', (data.payment_id, USER_ID))
        if not cur.fetchone():
            raise HTTPException(422, '支付方式不存在或不可使用')
        cur.execute('''INSERT INTO subscription(payment_id,name,category,amount,cycle_months,next_billing_date,auto_renew)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                    (data.payment_id, data.name, data.category, data.amount, data.cycle_months,
                     data.next_billing_date, data.auto_renew))
        return {'id': cur.lastrowid, **data.model_dump(), 'status': 'active'}


@app.patch('/api/subscriptions/{subscription_id}')
def update_subscription(subscription_id: int, data: SubscriptionPatch):
    # Column names come only from the Pydantic allowlist, values always use parameters.
    changes = data.model_dump(exclude_unset=True)
    with transaction() as cur:
        cur.execute('''SELECT s.id,s.status FROM subscription s JOIN payment_method p ON p.id=s.payment_id
                       WHERE s.id=%s AND p.user_id=%s FOR UPDATE''', (subscription_id, USER_ID))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, '订阅不存在')
        if row['status'] != 'active':
            raise HTTPException(409, '已取消的订阅不可直接修改')
        columns = ','.join(f'{key}=%s' for key in changes)
        cur.execute(f'UPDATE subscription SET {columns} WHERE id=%s', (*changes.values(), subscription_id))
    return {'id': subscription_id, 'updated': changes}


@app.delete('/api/subscriptions/{subscription_id}')
def delete_subscription(subscription_id: int):
    # For erroneous, unused entries only. This is NOT the future cancellation transaction.
    with transaction() as cur:
        cur.execute('''DELETE s FROM subscription s JOIN payment_method p ON p.id=s.payment_id
                       WHERE s.id=%s AND p.user_id=%s''', (subscription_id, USER_ID))
        if not cur.rowcount:
            raise HTTPException(404, '订阅不存在')
    return {'deleted': subscription_id}


def month_bounds(month: str):
    try:
        start = date.fromisoformat(month + '-01')
        if start.year < 1900 or start.year > 9998:
            raise ValueError()
        end = date(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)
        return start, end
    except ValueError:
        raise HTTPException(422, '月份应为 1900-01 至 9998-12 之间的 YYYY-MM')


Month = Annotated[str, Query(pattern=r'^\d{4}-\d{2}$')]


@app.get('/api/dashboard')
def dashboard(month: Month = '2026-11', as_of: date = DEMO_TODAY):
    start, end = month_bounds(month)
    with transaction() as cur:
        cur.execute('''SELECT COALESCE(SUM(b.amount),0) AS spending FROM billing_history b
                       JOIN subscription s ON s.id=b.subscription_id JOIN payment_method p ON p.id=s.payment_id
                       WHERE p.user_id=%s AND b.event_type='CHARGE' AND b.occurred_on >= %s AND b.occurred_on < %s''',
                    (USER_ID, start, end))
        spending = cur.fetchone()['spending']
        cur.execute('SELECT amount FROM budget_control WHERE user_id=%s AND month_start=%s', (USER_ID, start))
        budget = cur.fetchone()
        cur.execute('''SELECT COUNT(*) AS count,COALESCE(SUM(s.amount/s.cycle_months),0) AS monthly_estimate
                       FROM subscription s JOIN payment_method p ON p.id=s.payment_id
                       WHERE p.user_id=%s AND s.status='active' ''', (USER_ID,))
        active = cur.fetchone()
        cur.execute('''SELECT s.category, SUM(b.amount) AS total FROM billing_history b
                       JOIN subscription s ON s.id=b.subscription_id JOIN payment_method p ON p.id=s.payment_id
                       WHERE p.user_id=%s AND b.event_type='CHARGE' AND b.occurred_on >= %s AND b.occurred_on < %s
                       GROUP BY s.category ORDER BY total DESC''', (USER_ID, start, end))
        categories = cur.fetchall()
        cur.execute('''SELECT a.id,a.name,s.name AS subscription_name,
                       COALESCE(a.last_used_on,a.acquired_on) AS effective_last_used,
                       CASE WHEN s.status <> 'active' OR s.auto_renew=0 THEN 'inactive'
                            WHEN COALESCE(a.last_used_on,a.acquired_on)<DATE_SUB(%s,INTERVAL 3 MONTH)
                            THEN 'idle' ELSE 'used' END AS usage_state
                       FROM digital_asset a JOIN subscription s ON s.id=a.subscription_id
                       JOIN payment_method p ON p.id=s.payment_id WHERE p.user_id=%s ORDER BY a.id''', (as_of, USER_ID))
        assets = cur.fetchall()
        cur.execute('''SELECT r.id,r.message,r.due_on FROM reminder r
                       JOIN subscription s ON s.id=r.subscription_id JOIN payment_method p ON p.id=s.payment_id
                       WHERE p.user_id=%s AND r.status='pending' ORDER BY r.due_on,r.id''', (USER_ID,))
        reminders = cur.fetchall()
    return {'month': month, 'as_of': as_of, 'spending': spending,
            'budget': budget['amount'] if budget else None, 'active_count': active['count'],
            'monthly_estimate': round(active['monthly_estimate'], 2),
            'categories': categories, 'assets': assets, 'reminders': reminders}


@app.get('/api/calendar')
def calendar(month: Month = '2026-11'):
    start, end = month_bounds(month)
    with transaction() as cur:
        cur.execute('''SELECT s.id,s.name,s.amount,s.next_billing_date FROM subscription s
                       JOIN payment_method p ON p.id=s.payment_id
                       WHERE p.user_id=%s AND s.status='active' AND s.auto_renew=1
                       AND s.next_billing_date >= %s AND s.next_billing_date < %s
                       ORDER BY s.next_billing_date,s.id''', (USER_ID, start, end))
        return cur.fetchall()
