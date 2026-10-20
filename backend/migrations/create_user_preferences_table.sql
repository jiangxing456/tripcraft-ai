-- 用户长期偏好表：跨多次旅行记住的酒店/美食/节奏/预算等偏好。
-- 建表方式：psql -U postgres -d tripcraft_ai -f create_user_preferences_table.sql

CREATE TABLE IF NOT EXISTS user_preferences (
    id text NOT NULL,
    user_id text NOT NULL,
    category text NOT NULL,            -- hotel / dining / pace / budget / transport / general
    content text NOT NULL,              -- 偏好描述，如「偏好安静、靠近地铁的酒店」
    source_trip_id text NOT NULL DEFAULT '',
    created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT user_preferences_pkey PRIMARY KEY (id)
);

-- 并发写入依赖唯一索引；旧的普通索引由该索引替代。
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_preferences_user_category
    ON user_preferences(user_id, category);
DROP INDEX IF EXISTS idx_user_preferences_user_category;
