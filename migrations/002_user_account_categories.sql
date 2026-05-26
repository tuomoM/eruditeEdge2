ALTER TABLE users ADD COLUMN account_category TEXT NOT NULL DEFAULT 'basic'
    CHECK (account_category IN ('basic', 'trusted', 'admin'));

UPDATE users
SET account_category = 'admin'
WHERE id = (
    SELECT MIN(id)
    FROM users
);
