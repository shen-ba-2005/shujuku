-- MySQL 8.0.16+ / InnoDB / native SQL. Run only in an empty development database.
CREATE TABLE app_user (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  display_name VARCHAR(60) NOT NULL,
  email VARCHAR(120) NOT NULL UNIQUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE payment_method (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  label VARCHAR(60) NOT NULL,
  channel VARCHAR(20) NOT NULL,
  last_four CHAR(4) NULL,
  UNIQUE KEY uq_payment_label (user_id, label),
  CONSTRAINT fk_payment_user FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE RESTRICT,
  CONSTRAINT ck_payment_channel CHECK (channel IN ('bank','alipay','wechat','other')),
  CONSTRAINT ck_last_four CHECK (last_four IS NULL OR last_four REGEXP '^[0-9]{4}$')
) ENGINE=InnoDB;

CREATE TABLE subscription (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  payment_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(100) NOT NULL,
  category VARCHAR(20) NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  cycle_months SMALLINT NOT NULL DEFAULT 1,
  next_billing_date DATE NOT NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'active',
  auto_renew BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_sub_payment FOREIGN KEY (payment_id) REFERENCES payment_method(id) ON DELETE RESTRICT,
  CONSTRAINT ck_sub_amount CHECK (amount > 0 AND amount <= 99999999.99),
  CONSTRAINT ck_sub_cycle CHECK (cycle_months IN (1,3,6,12)),
  CONSTRAINT ck_sub_category CHECK (category IN ('productivity','entertainment','storage','learning','other')),
  CONSTRAINT ck_sub_status CHECK (status IN ('active','cancelled')),
  CONSTRAINT ck_sub_cancel CHECK (status <> 'cancelled' OR auto_renew = FALSE),
  KEY ix_sub_status_due (status, next_billing_date)
) ENGINE=InnoDB;

CREATE TABLE billing_history (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  subscription_id BIGINT UNSIGNED NOT NULL,
  payment_id BIGINT UNSIGNED NULL,
  event_type VARCHAR(10) NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  occurred_on DATE NOT NULL,
  event_key VARCHAR(100) NOT NULL UNIQUE,
  CONSTRAINT fk_billing_sub FOREIGN KEY (subscription_id) REFERENCES subscription(id) ON DELETE RESTRICT,
  CONSTRAINT fk_billing_payment FOREIGN KEY (payment_id) REFERENCES payment_method(id) ON DELETE RESTRICT,
  CONSTRAINT ck_billing_event CHECK (
    (event_type = 'CHARGE' AND amount > 0 AND payment_id IS NOT NULL) OR
    (event_type = 'CANCEL' AND amount = 0 AND payment_id IS NULL)
  ),
  KEY ix_billing_type_date (event_type, occurred_on)
) ENGINE=InnoDB;

CREATE TABLE digital_asset (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  subscription_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(100) NOT NULL,
  acquired_on DATE NOT NULL,
  last_used_on DATE NULL,
  CONSTRAINT fk_asset_sub FOREIGN KEY (subscription_id) REFERENCES subscription(id) ON DELETE RESTRICT,
  CONSTRAINT ck_asset_dates CHECK (last_used_on IS NULL OR last_used_on >= acquired_on),
  KEY ix_asset_last_used (last_used_on)
) ENGINE=InnoDB;

CREATE TABLE vault (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  asset_id BIGINT UNSIGNED NOT NULL UNIQUE,
  login_name VARCHAR(100) NOT NULL,
  secret_ciphertext VARBINARY(1024) NOT NULL,
  CONSTRAINT fk_vault_asset FOREIGN KEY (asset_id) REFERENCES digital_asset(id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE reminder (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  subscription_id BIGINT UNSIGNED NOT NULL,
  kind VARCHAR(12) NOT NULL,
  message VARCHAR(200) NOT NULL,
  due_on DATE NOT NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'pending',
  dedup_key VARCHAR(100) NOT NULL UNIQUE,
  CONSTRAINT fk_reminder_sub FOREIGN KEY (subscription_id) REFERENCES subscription(id) ON DELETE RESTRICT,
  CONSTRAINT ck_reminder_kind CHECK (kind IN ('renewal','budget')),
  CONSTRAINT ck_reminder_status CHECK (status IN ('pending','done','revoked')),
  KEY ix_reminder_status_due (status, due_on)
) ENGINE=InnoDB;

CREATE TABLE budget_control (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  month_start DATE NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  UNIQUE KEY uq_budget_month (user_id, month_start),
  CONSTRAINT fk_budget_user FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE RESTRICT,
  CONSTRAINT ck_budget_month CHECK (DAY(month_start) = 1),
  CONSTRAINT ck_budget_amount CHECK (amount > 0)
) ENGINE=InnoDB;
