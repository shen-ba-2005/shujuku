"""Run against live services; exercise forms, month states, escaping, and mobile layout."""
import json
from pathlib import Path
import uuid
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/evidence'
OUTPUT.mkdir(exist_ok=True)


with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page(viewport={'width':1440,'height':1080}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:5173')
    expect(page.locator('#active-count')).to_have_text('4')
    expect(page.locator('#spending')).to_have_text('¥175.00')
    expect(page.locator('#subscription-rows tr')).to_have_count(5)
    expect(page.locator('.day.has-events')).to_have_count(4)
    page.locator('#budget-progress').evaluate('(el) => Promise.all(el.getAnimations().map(a => a.finished))')
    assert abs(page.locator('#budget-progress').evaluate('el => el.offsetWidth / el.parentElement.offsetWidth') - 0.875) < 0.01
    page.locator('[data-day="2026-11-12"]').click()
    expect(page.locator('#calendar-detail')).to_contain_text('星河音乐')
    page.screenshot(path=str(OUTPUT / 'desktop.png'), full_page=True)
    token = uuid.uuid4().hex[:6]
    label = '浏览器支付-'+token
    name = '浏览器验证 <img src=x onerror=alert(1)> '+token
    payment_id = sub_id = None
    try:
        page.locator('#open-payment').click()
        form = page.locator('#payment-form')
        form.locator('[name=label]').fill(label)
        form.locator('[name=channel]').select_option('other')
        with page.expect_response(lambda response: response.url.endswith('/api/payments') and response.request.method=='POST') as result:
            form.locator('[type=submit]').click()
        payment_id = result.value.json()['id']
        expect(page.locator('#payment-list')).to_contain_text(label)
        page.locator('#open-subscription').click()
        form = page.locator('#subscription-form')
        form.locator('[name=name]').fill(name)
        form.locator('[name=amount]').fill('9.90')
        form.locator('[name=payment_id]').select_option(str(payment_id))
        with page.expect_response(lambda response: response.url.endswith('/api/subscriptions') and response.request.method=='POST') as result:
            form.locator('[type=submit]').click()
        sub_id = result.value.json()['id']
        expect(page.locator('#active-count')).to_have_text('5')
        expect(page.locator('#subscription-rows')).to_contain_text(name)
        expect(page.locator('#subscription-rows img')).to_have_count(0)
        page.locator(f'[data-edit="{sub_id}"]').click()
        form.locator('[name=amount]').fill('11.20')
        form.locator('[name=auto_renew]').uncheck()
        form.locator('[type=submit]').click()
        expect(page.locator(f'tr:has([data-edit="{sub_id}"])')).to_contain_text('¥11.20')
        expect(page.locator(f'tr:has([data-edit="{sub_id}"])')).to_contain_text('不自动续费')
    finally:
        page.on('dialog', lambda dialog: dialog.accept())
        if sub_id:
            page.locator(f'[data-delete="{sub_id}"]').click()
            expect(page.locator('#active-count')).to_have_text('4')
        if payment_id:
            page.locator(f'[data-delete-payment="{payment_id}"]').click()
            expect(page.locator('#payment-list')).not_to_contain_text(label)
    page.locator('#search').fill('不存在的服务')
    expect(page.locator('#subscription-rows')).to_contain_text('没有匹配')
    page.locator('#search').fill('')
    page.locator('#month').fill('2027-01')
    expect(page.locator('#spending')).to_have_text('¥0.00')
    expect(page.locator('#budget-limit')).to_contain_text('未设置预算')
    expect(page.locator('#categories')).to_contain_text('本月尚无扣费')
    page.locator('#month').fill('2026-11')
    expect(page.locator('#spending')).to_have_text('¥175.00')
    page.route('**/api/**', lambda route: route.abort())
    page.reload()
    expect(page.locator('#notice')).to_contain_text('加载失败')
    page.unroute('**/api/**')
    page.get_by_role('button', name='重新加载').click()
    expect(page.locator('#spending')).to_have_text('¥175.00')
    expect(page.locator('#notice')).to_be_hidden()
    page.set_viewport_size({'width':390,'height':844})
    expect(page.locator('#spending')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile page overflow'
    page.locator('#budget-progress').evaluate('(el) => Promise.all(el.getAnimations().map(a => a.finished))')
    page.screenshot(path=str(OUTPUT / 'mobile.png'), full_page=True)
    assert not errors, errors
    (OUTPUT / 'week8-browser.json').write_text(json.dumps({
        'browser':browser.version, 'checks':[
            '真实接口加载与4类展示','日历点击明细','支付新增与表单选择','订阅新增与指标刷新',
            'HTML名称转义','修改金额和自动续费','通过页面删除测试数据','搜索空状态',
            '无预算与无流水月份','网络失败提示和重试','390px布局无全页横向溢出',
            '预算进度实际宽度为87.5%','无JavaScript运行错误'], 'passed':True, 'javascript_errors':errors,
        'screenshots':['desktop.png','mobile.png']}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    browser.close()
    print('13 browser checks passed, screenshots saved.')
