-- All names, account references and financial records are fictional.
INSERT INTO app_user (id,display_name,email) VALUES (1,'林同学','student@example.invalid');
INSERT INTO payment_method (id,user_id,label,channel,last_four) VALUES
(1,1,'日常支付','alipay',NULL),(2,1,'学习银行卡','bank','2048');
INSERT INTO subscription (id,payment_id,name,category,amount,cycle_months,next_billing_date,status,auto_renew) VALUES
(1,1,'云笺笔记','productivity',28.00,1,'2026-11-18','active',1),
(2,1,'星河音乐','entertainment',18.00,1,'2026-11-12','active',1),
(3,2,'云屿存储','storage',30.00,1,'2026-11-22','active',1),
(4,2,'知行课堂','learning',99.00,1,'2026-11-25','active',1),
(5,1,'光影剧场','entertainment',25.00,1,'2026-11-28','cancelled',0);
INSERT INTO billing_history (subscription_id,payment_id,event_type,amount,occurred_on,event_key) VALUES
(1,1,'CHARGE',28,'2026-11-02','seed:1:2026-11'),
(2,1,'CHARGE',18,'2026-11-03','seed:2:2026-11'),
(3,2,'CHARGE',30,'2026-11-05','seed:3:2026-11'),
(4,2,'CHARGE',99,'2026-11-08','seed:4:2026-11'),
(5,1,'CHARGE',25,'2026-10-28','seed:5:2026-10'),
(5,NULL,'CANCEL',0,'2026-11-01','cancel:5');
INSERT INTO digital_asset (subscription_id,name,acquired_on,last_used_on) VALUES
(1,'云笺工作区','2026-01-01','2026-11-09'),
(2,'星河乐库','2026-01-01','2026-11-08'),
(3,'云屿 2TB 空间','2026-01-01','2026-06-01'),
(4,'知行课程包','2026-02-01',NULL),
(5,'光影账号','2026-01-01','2026-07-10');
-- A placeholder byte string, not a real or decryptable password. Vault UI is deferred.
INSERT INTO vault (asset_id,login_name,secret_ciphertext) VALUES (1,'demo@example.invalid',X'44454D4F5F4F4E4C59');
INSERT INTO reminder (subscription_id,kind,message,due_on,status,dedup_key) VALUES
(2,'renewal','星河音乐将于 11 月 12 日续费','2026-11-10','pending','renewal:2:2026-11-12'),
(3,'renewal','云屿存储长期未使用，可检查续费设置','2026-11-10','pending','renewal:3:2026-11-22'),
(5,'renewal','光影剧场续费提醒','2026-11-26','revoked','renewal:5:2026-11-28');
INSERT INTO budget_control (user_id,month_start,amount) VALUES (1,'2026-11-01',200),(1,'2026-10-01',200);
