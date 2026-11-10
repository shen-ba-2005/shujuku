-- Q1: JOIN, current subscription and payment channels.
SELECT s.id,s.name,s.amount,s.next_billing_date,p.label AS payment_label
FROM subscription s JOIN payment_method p ON p.id=s.payment_id
WHERE p.user_id=1 ORDER BY s.id;

-- Q2: GROUP BY, actual November spending by historical payment channel.
SELECT p.label,SUM(b.amount) AS total
FROM billing_history b JOIN payment_method p ON p.id=b.payment_id
WHERE p.user_id=1 AND b.event_type='CHARGE'
AND b.occurred_on >= '2026-11-01' AND b.occurred_on < '2026-12-01'
GROUP BY p.id,p.label ORDER BY p.id;

-- Q3: correlated subquery, idle assets belonging to active auto-renew subscriptions.
SELECT a.id,a.name,COALESCE(a.last_used_on,a.acquired_on) AS effective_last_used
FROM digital_asset a
WHERE COALESCE(a.last_used_on,a.acquired_on) < DATE_SUB('2026-11-10',INTERVAL 3 MONTH)
AND EXISTS (SELECT 1 FROM subscription s JOIN payment_method p ON p.id=s.payment_id
 WHERE s.id=a.subscription_id AND s.status='active' AND s.auto_renew=1 AND p.user_id=1)
ORDER BY a.id;

-- Q4: monthly service-type aggregation. CANCEL is explicitly excluded.
SELECT s.category,SUM(b.amount) AS total
FROM billing_history b JOIN subscription s ON s.id=b.subscription_id
JOIN payment_method p ON p.id=s.payment_id
WHERE p.user_id=1 AND b.event_type='CHARGE'
AND b.occurred_on >= '2026-11-01' AND b.occurred_on < '2026-12-01'
GROUP BY s.category ORDER BY s.category;
