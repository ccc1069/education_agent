-- =============================================================================
-- Lumen 全流程演示种子数据 (PostgreSQL)
-- 用法:
--   cd code/python && python -m scripts.seed_demo_data
--   或: psql "$DATABASE_URL" -f scripts/seed_demo_data.sql
-- 约定:
--   - 幂等: 按唯一键 NOT EXISTS / ON CONFLICT 跳过
--   - 统一租户: tenant_id = 1 (迁移 0009 默认租户)
--   - 演示密码: demo123456
--   - bcrypt: $2b$12$2uXOl28emrnvsN73g9Vwou9XK4sd2Jh.iYgcXtP11dV0PS1dPWZ6C
-- =============================================================================

BEGIN;

-- 校准序列(迁移曾显式插入 id=1 的默认租户,序列可能仍停在 1)
SELECT setval(pg_get_serial_sequence('tenants', 'id'), COALESCE((SELECT MAX(id) FROM tenants), 1));
SELECT setval(pg_get_serial_sequence('tenant_quotas', 'id'), COALESCE((SELECT MAX(id) FROM tenant_quotas), 1));
SELECT setval(pg_get_serial_sequence('learners', 'id'), COALESCE((SELECT MAX(id) FROM learners), 1));
SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE((SELECT MAX(id) FROM users), 1));
SELECT setval(pg_get_serial_sequence('knowledge_nodes', 'id'), COALESCE((SELECT MAX(id) FROM knowledge_nodes), 1));
SELECT setval(pg_get_serial_sequence('knowledge_states', 'id'), COALESCE((SELECT MAX(id) FROM knowledge_states), 1));
SELECT setval(pg_get_serial_sequence('submissions', 'id'), COALESCE((SELECT MAX(id) FROM submissions), 1));
SELECT setval(pg_get_serial_sequence('review_schedules', 'id'), COALESCE((SELECT MAX(id) FROM review_schedules), 1));
SELECT setval(pg_get_serial_sequence('questions', 'id'), COALESCE((SELECT MAX(id) FROM questions), 1));
SELECT setval(pg_get_serial_sequence('classes', 'id'), COALESCE((SELECT MAX(id) FROM classes), 1));
SELECT setval(pg_get_serial_sequence('class_members', 'id'), COALESCE((SELECT MAX(id) FROM class_members), 1));
SELECT setval(pg_get_serial_sequence('assignments', 'id'), COALESCE((SELECT MAX(id) FROM assignments), 1));
SELECT setval(pg_get_serial_sequence('documents', 'id'), COALESCE((SELECT MAX(id) FROM documents), 1));
SELECT setval(pg_get_serial_sequence('document_chunks', 'id'), COALESCE((SELECT MAX(id) FROM document_chunks), 1));
SELECT setval(pg_get_serial_sequence('notifications', 'id'), COALESCE((SELECT MAX(id) FROM notifications), 1));
SELECT setval(pg_get_serial_sequence('notification_preferences', 'id'), COALESCE((SELECT MAX(id) FROM notification_preferences), 1));
SELECT setval(pg_get_serial_sequence('privacy_consents', 'id'), COALESCE((SELECT MAX(id) FROM privacy_consents), 1));
SELECT setval(pg_get_serial_sequence('data_export_jobs', 'id'), COALESCE((SELECT MAX(id) FROM data_export_jobs), 1));
SELECT setval(pg_get_serial_sequence('task_executions', 'id'), COALESCE((SELECT MAX(id) FROM task_executions), 1));
SELECT setval(pg_get_serial_sequence('events', 'id'), COALESCE((SELECT MAX(id) FROM events), 1));
SELECT setval(pg_get_serial_sequence('audit_logs', 'id'), COALESCE((SELECT MAX(id) FROM audit_logs), 1));

-- ---------- 0. 额外演示租户(管理员租户页有内容) ----------
INSERT INTO tenants (name, slug, plan, is_active, settings)
SELECT '演示中学', 'demo-school', 'pro', true, '{}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE slug = 'demo-school');

INSERT INTO tenant_quotas (tenant_id, max_users, max_llm_tokens_per_month, current_llm_tokens, period_start)
SELECT t.id, 200, 2000000, 280000, date_trunc('month', now() AT TIME ZONE 'UTC')
FROM tenants t
WHERE t.slug = 'demo-school'
  AND NOT EXISTS (SELECT 1 FROM tenant_quotas q WHERE q.tenant_id = t.id);

INSERT INTO tenants (name, slug, plan, is_active, settings)
SELECT '实验小学', 'exp-primary', 'free', true, '{}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE slug = 'exp-primary');

INSERT INTO tenant_quotas (tenant_id, max_users, max_llm_tokens_per_month, current_llm_tokens, period_start)
SELECT t.id, 50, 200000, 12000, date_trunc('month', now() AT TIME ZONE 'UTC')
FROM tenants t
WHERE t.slug = 'exp-primary'
  AND NOT EXISTS (SELECT 1 FROM tenant_quotas q WHERE q.tenant_id = t.id);

-- ---------- 1. 知识图谱(与 build_sample_math_graph 对齐) ----------
INSERT INTO knowledge_nodes (public_id, name, subject, difficulty, description, tags, version)
VALUES
  ('arithmetic', '四则运算', 'math', 0.1, '加减乘除基础运算', '["基础"]'::jsonb, 1),
  ('fractions', '分数运算', 'math', 0.2, '分数加减乘除', '["基础"]'::jsonb, 1),
  ('negative_numbers', '负数', 'math', 0.15, '负数概念与运算', '["基础"]'::jsonb, 1),
  ('algebraic_expr', '代数式', 'math', 0.3, '代数式化简', '["代数"]'::jsonb, 1),
  ('linear_eq_1', '一元一次方程', 'math', 0.35, '一元一次方程求解', '["方程"]'::jsonb, 1),
  ('linear_eq_2', '二元一次方程组', 'math', 0.45, '二元一次方程组', '["方程"]'::jsonb, 1),
  ('factoring', '因式分解', 'math', 0.4, '多项式因式分解', '["代数"]'::jsonb, 1),
  ('quadratic_eq', '一元二次方程', 'math', 0.55, '一元二次方程', '["方程"]'::jsonb, 1),
  ('quadratic_func', '二次函数', 'math', 0.6, '二次函数图像与性质', '["函数"]'::jsonb, 1),
  ('inequality', '不等式', 'math', 0.4, '一元一次不等式', '["不等式"]'::jsonb, 1),
  ('coordinate', '平面直角坐标系', 'math', 0.3, '坐标平面', '["几何"]'::jsonb, 1),
  ('linear_func', '一次函数', 'math', 0.45, '一次函数', '["函数"]'::jsonb, 1),
  ('pythagorean', '勾股定理', 'math', 0.35, '勾股定理及应用', '["几何"]'::jsonb, 1),
  ('similar_triangle', '相似三角形', 'math', 0.5, '相似三角形判定', '["几何"]'::jsonb, 1),
  ('trig_basic', '三角函数基础', 'math', 0.55, '锐角三角函数', '["三角"]'::jsonb, 1),
  ('probability', '概率初步', 'math', 0.4, '古典概型', '["统计"]'::jsonb, 1),
  ('statistics', '数据统计', 'math', 0.35, '平均数中位数', '["统计"]'::jsonb, 1),
  ('sequence', '数列', 'math', 0.5, '等差等比数列入门', '["代数"]'::jsonb, 1),
  ('sets', '集合', 'math', 0.25, '集合基本概念', '["基础"]'::jsonb, 1),
  ('logic', '简易逻辑', 'math', 0.3, '命题与推理', '["基础"]'::jsonb, 1)
ON CONFLICT (public_id) DO NOTHING;

-- 前置依赖(按 public_id 解析内部 id)
INSERT INTO knowledge_prerequisites (node_id, prerequisite_id)
SELECT n.id, p.id FROM knowledge_nodes n, knowledge_nodes p
WHERE (n.public_id, p.public_id) IN (
  ('fractions', 'arithmetic'),
  ('negative_numbers', 'arithmetic'),
  ('algebraic_expr', 'arithmetic'),
  ('algebraic_expr', 'negative_numbers'),
  ('linear_eq_1', 'algebraic_expr'),
  ('linear_eq_2', 'linear_eq_1'),
  ('factoring', 'algebraic_expr'),
  ('quadratic_eq', 'factoring'),
  ('quadratic_eq', 'linear_eq_1'),
  ('quadratic_func', 'quadratic_eq'),
  ('inequality', 'linear_eq_1'),
  ('coordinate', 'negative_numbers'),
  ('linear_func', 'linear_eq_1'),
  ('linear_func', 'coordinate'),
  ('pythagorean', 'arithmetic'),
  ('similar_triangle', 'pythagorean'),
  ('similar_triangle', 'fractions'),
  ('trig_basic', 'pythagorean'),
  ('trig_basic', 'fractions'),
  ('probability', 'fractions'),
  ('statistics', 'arithmetic'),
  ('statistics', 'fractions'),
  ('sequence', 'algebraic_expr'),
  ('sets', 'arithmetic'),
  ('logic', 'sets')
)
ON CONFLICT DO NOTHING;

-- ---------- 2. Learners ----------
INSERT INTO learners (public_id, name, profile, tenant_id)
SELECT 'lrn_demo_student', '李同学', '{"grade":"初二","school":"演示中学"}'::jsonb, 1
WHERE NOT EXISTS (SELECT 1 FROM learners WHERE public_id = 'lrn_demo_student');

INSERT INTO learners (public_id, name, profile, tenant_id)
SELECT 'lrn_demo_classmate_a', '张同学', '{"grade":"初二"}'::jsonb, 1
WHERE NOT EXISTS (SELECT 1 FROM learners WHERE public_id = 'lrn_demo_classmate_a');

INSERT INTO learners (public_id, name, profile, tenant_id)
SELECT 'lrn_demo_classmate_b', '王同学', '{"grade":"初二"}'::jsonb, 1
WHERE NOT EXISTS (SELECT 1 FROM learners WHERE public_id = 'lrn_demo_classmate_b');

INSERT INTO learners (public_id, name, profile, tenant_id)
SELECT 'lrn_demo_teacher', '王老师', '{"role":"teacher_preview"}'::jsonb, 1
WHERE NOT EXISTS (SELECT 1 FROM learners WHERE public_id = 'lrn_demo_teacher');

INSERT INTO learners (public_id, name, profile, tenant_id)
SELECT 'lrn_demo_admin', '管理员', '{"role":"admin_preview"}'::jsonb, 1
WHERE NOT EXISTS (SELECT 1 FROM learners WHERE public_id = 'lrn_demo_admin');

-- ---------- 3. Users (密码均为 demo123456) ----------
INSERT INTO users (email, password_hash, role, is_active, is_verified, tenant_id, learner_id, failed_login_count)
SELECT
  'student@demo.com',
  '$2b$12$2uXOl28emrnvsN73g9Vwou9XK4sd2Jh.iYgcXtP11dV0PS1dPWZ6C',
  'student', true, true, 1,
  (SELECT id FROM learners WHERE public_id = 'lrn_demo_student'),
  0
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'student@demo.com');

INSERT INTO users (email, password_hash, role, is_active, is_verified, tenant_id, learner_id, failed_login_count)
SELECT
  'teacher@demo.com',
  '$2b$12$2uXOl28emrnvsN73g9Vwou9XK4sd2Jh.iYgcXtP11dV0PS1dPWZ6C',
  'teacher', true, true, 1,
  (SELECT id FROM learners WHERE public_id = 'lrn_demo_teacher'),
  0
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'teacher@demo.com');

INSERT INTO users (email, password_hash, role, is_active, is_verified, tenant_id, learner_id, failed_login_count)
SELECT
  'admin@demo.com',
  '$2b$12$2uXOl28emrnvsN73g9Vwou9XK4sd2Jh.iYgcXtP11dV0PS1dPWZ6C',
  'admin', true, true, 1,
  (SELECT id FROM learners WHERE public_id = 'lrn_demo_admin'),
  0
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'admin@demo.com');

-- 演示账号强制绑定到种子 learner(避免旧 UUID learner 与班级成员不一致)
UPDATE users u
SET learner_id = l.id, is_verified = true, is_active = true
FROM learners l
WHERE u.email = 'student@demo.com' AND l.public_id = 'lrn_demo_student'
  AND (u.learner_id IS DISTINCT FROM l.id);

UPDATE users u
SET learner_id = l.id, is_verified = true, is_active = true
FROM learners l
WHERE u.email = 'teacher@demo.com' AND l.public_id = 'lrn_demo_teacher'
  AND (u.learner_id IS DISTINCT FROM l.id);

UPDATE users u
SET learner_id = l.id, is_verified = true, is_active = true
FROM learners l
WHERE u.email = 'admin@demo.com' AND l.public_id = 'lrn_demo_admin'
  AND (u.learner_id IS DISTINCT FROM l.id);

-- ---------- 4. 学习进度 / 答题 / 复习 ----------
INSERT INTO knowledge_states (
  learner_id, knowledge_id, mastery, alpha, beta, attempts, correct_count, streak, version, tenant_id, last_attempt
)
SELECT l.id, v.kid, v.mastery, v.alpha, v.beta, v.attempts, v.correct, v.streak, 1, 1, now() - (v.days || ' days')::interval
FROM learners l
CROSS JOIN (VALUES
  ('arithmetic', 0.92, 18.0, 2.0, 20, 18, 5, 1),
  ('fractions', 0.78, 12.0, 4.0, 14, 10, 3, 2),
  ('linear_eq_1', 0.55, 8.0, 6.0, 10, 6, 1, 3),
  ('quadratic_func', 0.28, 3.0, 8.0, 6, 2, 0, 5),
  ('pythagorean', 0.65, 9.0, 5.0, 8, 5, 2, 4)
) AS v(kid, mastery, alpha, beta, attempts, correct, streak, days)
WHERE l.public_id = 'lrn_demo_student'
ON CONFLICT (learner_id, knowledge_id) DO NOTHING;

INSERT INTO knowledge_states (
  learner_id, knowledge_id, mastery, alpha, beta, attempts, correct_count, streak, version, tenant_id
)
SELECT l.id, v.kid, v.mastery, 5.0, 5.0, 4, 2, 0, 1, 1
FROM learners l
CROSS JOIN (VALUES
  ('arithmetic', 0.70),
  ('fractions', 0.40),
  ('linear_eq_1', 0.35)
) AS v(kid, mastery)
WHERE l.public_id IN ('lrn_demo_classmate_a', 'lrn_demo_classmate_b')
ON CONFLICT (learner_id, knowledge_id) DO NOTHING;

INSERT INTO submissions (learner_id, knowledge_id, is_correct, time_spent_seconds, tenant_id, created_at)
SELECT l.id, v.kid, v.ok, v.sec, 1, now() - (v.hrs || ' hours')::interval
FROM learners l
CROSS JOIN (VALUES
  ('arithmetic', true, 42.0, 30),
  ('arithmetic', true, 35.0, 28),
  ('fractions', false, 80.0, 20),
  ('fractions', true, 55.0, 18),
  ('linear_eq_1', true, 90.0, 10),
  ('quadratic_func', false, 120.0, 5)
) AS v(kid, ok, sec, hrs)
WHERE l.public_id = 'lrn_demo_student'
  AND NOT EXISTS (
    SELECT 1 FROM submissions s
    WHERE s.learner_id = l.id AND s.knowledge_id = v.kid AND s.time_spent_seconds = v.sec
  );

INSERT INTO review_schedules (
  learner_id, knowledge_id, easiness_factor, interval_days, repetition, total_reviews,
  next_review, last_review, tenant_id
)
SELECT l.id, v.kid, v.ef, v.interval, v.rep, v.total, now() + (v.next_days || ' days')::interval, now() - interval '1 day', 1
FROM learners l
CROSS JOIN (VALUES
  ('fractions', 2.4, 1.0, 1, 3, 0),
  ('linear_eq_1', 2.2, 2.0, 2, 4, 1),
  ('quadratic_func', 1.9, 1.0, 0, 2, -1)
) AS v(kid, ef, interval, rep, total, next_days)
WHERE l.public_id = 'lrn_demo_student'
ON CONFLICT (learner_id, knowledge_id) DO NOTHING;

-- ---------- 5. 题库 ----------
INSERT INTO questions (
  knowledge_id, question_type, difficulty, content, answer, analysis, status, created_by, tenant_id, metadata
)
SELECT
  v.kid, v.qtype, v.diff, v.content::jsonb, v.answer, v.analysis, v.status,
  (SELECT id FROM users WHERE email = 'teacher@demo.com'),
  1, '{"seed":"demo"}'::jsonb
FROM (VALUES
  (
    'arithmetic', 'multiple_choice', 1,
    '{"stem":"计算 12 + 8 × 3 的值是多少?","options":["36","60","44","24"]}',
    '44',
    '先乘后加: 8×3=24, 12+24=44。',
    'published'
  ),
  (
    'fractions', 'multiple_choice', 2,
    '{"stem":"化简 6/8 的结果是?","options":["3/4","2/3","4/6","1/2"]}',
    '3/4',
    '分子分母同除以 2 得 3/4。',
    'published'
  ),
  (
    'linear_eq_1', 'fill_blank', 3,
    '{"stem":"解方程: 2x + 6 = 14, x = ____"}',
    '4',
    '2x = 8, x = 4。',
    'published'
  ),
  (
    'quadratic_func', 'true_false', 3,
    '{"stem":"二次函数 y = x² 的图像开口向上。"}',
    'true',
    '二次项系数 a=1>0,开口向上。',
    'published'
  ),
  (
    'pythagorean', 'open_ended', 3,
    '{"stem":"直角三角形两直角边分别为 3 和 4,求斜边长度,并简述依据。"}',
    '5',
    '由勾股定理: √(3²+4²)=5。',
    'published'
  ),
  (
    'probability', 'multiple_choice', 2,
    '{"stem":"掷一枚公平硬币,正面朝上的概率是?","options":["0","1/2","1","1/4"]}',
    '1/2',
    '两种等可能结果,正面占 1/2。',
    'review'
  ),
  (
    'statistics', 'multiple_choice', 2,
    '{"stem":"数据 2,4,6 的平均数是?","options":["3","4","5","6"]}',
    '4',
    '(2+4+6)/3=4。',
    'draft'
  )
) AS v(kid, qtype, diff, content, answer, analysis, status)
WHERE NOT EXISTS (
  SELECT 1 FROM questions q
  WHERE q.knowledge_id = v.kid AND q.answer = v.answer AND q.metadata->>'seed' = 'demo'
);

-- ---------- 6. 班级 / 成员 / 作业 ----------
-- 班级 A: 综合数学强化
INSERT INTO classes (name, description, teacher_id, invite_code, is_active, tenant_id, metadata)
SELECT
  '初二(1)班 · 数学强化',
  '演示班级:覆盖学习路径、作业与学情看板',
  (SELECT id FROM users WHERE email = 'teacher@demo.com'),
  'DEMOCLS01',
  true,
  1,
  '{"seed":"demo","grade":"初二","subject":"math"}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM classes WHERE invite_code = 'DEMOCLS01');

-- 班级 B: 几何专题
INSERT INTO classes (name, description, teacher_id, invite_code, is_active, tenant_id, metadata)
SELECT
  '初二几何专题班',
  '勾股定理 / 相似三角形专题冲刺',
  (SELECT id FROM users WHERE email = 'teacher@demo.com'),
  'DEMOGEO02',
  true,
  1,
  '{"seed":"demo","grade":"初二","subject":"geometry"}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM classes WHERE invite_code = 'DEMOGEO02');

-- 班级 C: 管理员名下空班(方便 admin 账号也能看到班级列表)
INSERT INTO classes (name, description, teacher_id, invite_code, is_active, tenant_id, metadata)
SELECT
  '教务演示班',
  '管理员视角的演示班级(可空成员)',
  (SELECT id FROM users WHERE email = 'admin@demo.com'),
  'DEMOADM03',
  true,
  1,
  '{"seed":"demo","owner":"admin"}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM classes WHERE invite_code = 'DEMOADM03');

-- 成员: 1 班三人; 几何班两人(学生+张同学)
INSERT INTO class_members (class_id, learner_id, tenant_id)
SELECT c.id, l.id, 1
FROM classes c
CROSS JOIN learners l
WHERE c.invite_code = 'DEMOCLS01'
  AND l.public_id IN ('lrn_demo_student', 'lrn_demo_classmate_a', 'lrn_demo_classmate_b')
ON CONFLICT (class_id, learner_id) DO NOTHING;

INSERT INTO class_members (class_id, learner_id, tenant_id)
SELECT c.id, l.id, 1
FROM classes c
CROSS JOIN learners l
WHERE c.invite_code = 'DEMOGEO02'
  AND l.public_id IN ('lrn_demo_student', 'lrn_demo_classmate_a')
ON CONFLICT (class_id, learner_id) DO NOTHING;

-- 作业: 1 班 · 第1周(已发布)
INSERT INTO assignments (title, description, class_id, teacher_id, question_ids, status, due_at, tenant_id, metadata)
SELECT
  '第1周 · 方程与函数基础练',
  '覆盖一元一次方程与二次函数入门',
  c.id,
  (SELECT id FROM users WHERE email = 'teacher@demo.com'),
  (
    SELECT COALESCE(jsonb_agg(q.id ORDER BY q.id), '[]'::jsonb)
    FROM questions q
    WHERE q.metadata->>'seed' = 'demo'
      AND q.status = 'published'
      AND q.knowledge_id IN ('linear_eq_1', 'quadratic_func', 'arithmetic')
  ),
  'published',
  now() + interval '7 days',
  1,
  '{"seed":"demo","week":1}'::jsonb
FROM classes c
WHERE c.invite_code = 'DEMOCLS01'
  AND NOT EXISTS (
    SELECT 1 FROM assignments a WHERE a.class_id = c.id AND a.metadata->>'seed' = 'demo' AND a.title LIKE '第1周%'
  );

-- 作业: 1 班 · 第2周(已发布,分数+四则)
INSERT INTO assignments (title, description, class_id, teacher_id, question_ids, status, due_at, tenant_id, metadata)
SELECT
  '第2周 · 分数与运算巩固',
  '分数化简与四则运算综合练习',
  c.id,
  (SELECT id FROM users WHERE email = 'teacher@demo.com'),
  (
    SELECT COALESCE(jsonb_agg(q.id ORDER BY q.id), '[]'::jsonb)
    FROM questions q
    WHERE q.metadata->>'seed' = 'demo'
      AND q.status = 'published'
      AND q.knowledge_id IN ('fractions', 'arithmetic')
  ),
  'published',
  now() + interval '14 days',
  1,
  '{"seed":"demo","week":2}'::jsonb
FROM classes c
WHERE c.invite_code = 'DEMOCLS01'
  AND NOT EXISTS (
    SELECT 1 FROM assignments a WHERE a.class_id = c.id AND a.metadata->>'seed' = 'demo' AND a.title LIKE '第2周%'
  );

-- 作业: 1 班 · 入学摸底(已关闭)
INSERT INTO assignments (title, description, class_id, teacher_id, question_ids, status, due_at, tenant_id, metadata)
SELECT
  '入学摸底 · 基础运算',
  '开课前摸底,已截止批改',
  c.id,
  (SELECT id FROM users WHERE email = 'teacher@demo.com'),
  (
    SELECT COALESCE(jsonb_agg(q.id ORDER BY q.id), '[]'::jsonb)
    FROM questions q
    WHERE q.metadata->>'seed' = 'demo'
      AND q.status = 'published'
      AND q.knowledge_id = 'arithmetic'
  ),
  'closed',
  now() - interval '3 days',
  1,
  '{"seed":"demo","week":0}'::jsonb
FROM classes c
WHERE c.invite_code = 'DEMOCLS01'
  AND NOT EXISTS (
    SELECT 1 FROM assignments a WHERE a.class_id = c.id AND a.metadata->>'seed' = 'demo' AND a.title LIKE '入学摸底%'
  );

-- 作业: 1 班 · 草稿
INSERT INTO assignments (title, description, class_id, teacher_id, question_ids, status, due_at, tenant_id, metadata)
SELECT
  '草稿 · 概率与统计预习',
  '尚未发布的作业草稿',
  c.id,
  (SELECT id FROM users WHERE email = 'teacher@demo.com'),
  (
    SELECT COALESCE(jsonb_agg(q.id ORDER BY q.id), '[]'::jsonb)
    FROM questions q
    WHERE q.metadata->>'seed' = 'demo'
      AND q.knowledge_id IN ('probability', 'statistics')
  ),
  'draft',
  now() + interval '21 days',
  1,
  '{"seed":"demo","week":3}'::jsonb
FROM classes c
WHERE c.invite_code = 'DEMOCLS01'
  AND NOT EXISTS (
    SELECT 1 FROM assignments a WHERE a.class_id = c.id AND a.metadata->>'seed' = 'demo' AND a.title LIKE '草稿%'
  );

-- 作业: 几何班 · 已发布
INSERT INTO assignments (title, description, class_id, teacher_id, question_ids, status, due_at, tenant_id, metadata)
SELECT
  '几何冲刺 · 勾股定理应用',
  '结合图形计算斜边与面积',
  c.id,
  (SELECT id FROM users WHERE email = 'teacher@demo.com'),
  (
    SELECT COALESCE(jsonb_agg(q.id ORDER BY q.id), '[]'::jsonb)
    FROM questions q
    WHERE q.metadata->>'seed' = 'demo'
      AND q.status = 'published'
      AND q.knowledge_id IN ('pythagorean')
  ),
  'published',
  now() + interval '10 days',
  1,
  '{"seed":"demo","topic":"pythagorean"}'::jsonb
FROM classes c
WHERE c.invite_code = 'DEMOGEO02'
  AND NOT EXISTS (
    SELECT 1 FROM assignments a WHERE a.class_id = c.id AND a.metadata->>'seed' = 'demo' AND a.title LIKE '几何冲刺%'
  );

-- 作业: 几何班 · 草稿
INSERT INTO assignments (title, description, class_id, teacher_id, question_ids, status, due_at, tenant_id, metadata)
SELECT
  '草稿 · 相似三角形判定',
  '待补充题目后发布',
  c.id,
  (SELECT id FROM users WHERE email = 'teacher@demo.com'),
  '[]'::jsonb,
  'draft',
  now() + interval '20 days',
  1,
  '{"seed":"demo","topic":"similar"}'::jsonb
FROM classes c
WHERE c.invite_code = 'DEMOGEO02'
  AND NOT EXISTS (
    SELECT 1 FROM assignments a WHERE a.class_id = c.id AND a.metadata->>'seed' = 'demo' AND a.title LIKE '草稿 · 相似%'
  );

-- ---------- 7. RAG 文档(分块由 Python 脚本补 embedding) ----------
INSERT INTO documents (
  title, source_type, source_url, content_hash, status, error_message, total_chunks, tenant_id, metadata
)
SELECT
  '初中数学 · 方程专题讲义',
  'markdown',
  NULL,
  'seed_doc_eq_001_' || repeat('a', 48),
  'indexed',
  NULL,
  2,
  1,
  '{"seed":"demo","topic":"equation"}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM documents WHERE metadata->>'seed' = 'demo' AND title = '初中数学 · 方程专题讲义');

INSERT INTO documents (
  title, source_type, source_url, content_hash, status, error_message, total_chunks, tenant_id, metadata
)
SELECT
  '二次函数图像速查',
  'text',
  NULL,
  'seed_doc_qf_002_' || repeat('b', 48),
  'indexed',
  NULL,
  1,
  1,
  '{"seed":"demo","topic":"quadratic_func"}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM documents WHERE metadata->>'seed' = 'demo' AND title = '二次函数图像速查');

INSERT INTO documents (
  title, source_type, source_url, content_hash, status, error_message, total_chunks, tenant_id, metadata
)
SELECT
  '概率入门笔记',
  'markdown',
  NULL,
  'seed_doc_pr_003_' || repeat('c', 48),
  'indexed',
  NULL,
  1,
  1,
  '{"seed":"demo","topic":"probability"}'::jsonb
WHERE NOT EXISTS (
  SELECT 1 FROM documents
  WHERE metadata->>'seed' = 'demo'
    AND title IN ('概率入门笔记', '待索引 · 概率入门笔记')
);

-- 旧种子标题迁移
UPDATE documents
SET title = '概率入门笔记', status = 'indexed'
WHERE metadata->>'seed' = 'demo' AND title = '待索引 · 概率入门笔记';

-- ---------- 8. 通知 / 偏好 ----------
INSERT INTO notification_preferences (
  user_id, tenant_id, ws_enabled, email_enabled, push_enabled,
  quiet_hours_start, quiet_hours_end, min_priority
)
SELECT u.id, 1, true, false, true, 22, 8, 0
FROM users u
WHERE u.email IN ('student@demo.com', 'teacher@demo.com', 'admin@demo.com')
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO notifications (user_id, type, channel, status, title, body, priority, tenant_id, created_at, read_at, payload)
SELECT
  (SELECT id FROM users WHERE email = 'student@demo.com'),
  v.type, 'ws', v.status, v.title, v.body, v.priority, 1,
  now() - (v.hrs || ' hours')::interval,
  CASE WHEN v.status = 'read' THEN now() - (v.hrs || ' hours')::interval ELSE NULL END,
  '{"seed":"demo"}'::jsonb
FROM (VALUES
  ('review_reminder', 'delivered', '复习提醒 · 分数运算', '「分数运算」已到复习时间,建议花 10 分钟巩固。', 2, 2),
  ('class_event', 'delivered', '新作业发布', '王老师发布了「第1周 · 方程与函数基础练」。', 1, 5),
  ('teacher_feedback', 'read', '练习点评', '一元一次方程练习完成不错,注意检验步骤。', 1, 26),
  ('system', 'delivered', '系统公告', '演示环境已就绪,可体验学习 / 教学 / 管理全流程。', 0, 1)
) AS v(type, status, title, body, priority, hrs)
WHERE NOT EXISTS (
  SELECT 1 FROM notifications n
  WHERE n.user_id = (SELECT id FROM users WHERE email = 'student@demo.com')
    AND n.title = v.title
    AND n.payload->>'seed' = 'demo'
);

INSERT INTO notifications (user_id, type, channel, status, title, body, priority, tenant_id, payload)
SELECT
  (SELECT id FROM users WHERE email = 'teacher@demo.com'),
  'class_event', 'ws', 'delivered', '班级动态', '李同学加入了「初二(1)班 · 数学强化」。', 1, 1,
  '{"seed":"demo"}'::jsonb
WHERE NOT EXISTS (
  SELECT 1 FROM notifications n
  WHERE n.user_id = (SELECT id FROM users WHERE email = 'teacher@demo.com')
    AND n.title = '班级动态'
    AND n.payload->>'seed' = 'demo'
);

-- ---------- 9. 隐私同意 / 导出任务 ----------
INSERT INTO privacy_consents (user_id, consent_type, granted, consent_version, tenant_id)
SELECT u.id, v.ctype, v.granted, '1.0', 1
FROM users u
CROSS JOIN (VALUES
  ('analytics', true),
  ('llm_training', false),
  ('marketing', false),
  ('third_party_share', false)
) AS v(ctype, granted)
WHERE u.email = 'student@demo.com'
  AND NOT EXISTS (
    SELECT 1 FROM privacy_consents pc
    WHERE pc.user_id = u.id AND pc.consent_type = v.ctype
  );

INSERT INTO data_export_jobs (user_id, status, requested_at, completed_at, file_size_bytes, tenant_id)
SELECT
  (SELECT id FROM users WHERE email = 'student@demo.com'),
  'completed',
  now() - interval '3 days',
  now() - interval '3 days' + interval '4 minutes',
  245678,
  1
WHERE NOT EXISTS (
  SELECT 1 FROM data_export_jobs j
  WHERE j.user_id = (SELECT id FROM users WHERE email = 'student@demo.com')
    AND j.status = 'completed'
    AND j.file_size_bytes = 245678
);

-- ---------- 10. 任务执行历史 ----------
INSERT INTO task_executions (
  task_name, status, started_at, completed_at, duration_ms, error_message, metadata, triggered_by, tenant_id
)
SELECT v.name, v.status, now() - (v.hrs || ' hours')::interval,
       now() - (v.hrs || ' hours')::interval + (v.ms || ' milliseconds')::interval,
       v.ms, v.err, v.meta::jsonb, v.by, 1
FROM (VALUES
  ('execute_pending_deletions', 'success', 6, NULL, '{"processed":0}', 'scheduler', 1),
  ('send_review_reminders', 'success', 120, NULL, '{"sent":1}', 'scheduler', 8),
  ('cleanup_expired_tokens', 'success', 45, NULL, '{"deleted":0}', 'scheduler', 20),
  ('generate_daily_stats', 'failed', 800, 'demo seed simulated failure', '{"error":"simulated"}', 'scheduler', 30),
  ('send_review_reminders', 'success', 95, NULL, '{"sent":2}', 'admin@demo.com', 2)
) AS v(name, status, ms, err, meta, by, hrs)
WHERE NOT EXISTS (
  SELECT 1 FROM task_executions t
  WHERE t.task_name = v.name AND t.triggered_by = v.by AND t.duration_ms = v.ms
    AND t.metadata = v.meta::jsonb
);

-- ---------- 11. 事件溯源样例 ----------
INSERT INTO events (public_id, type, source, learner_public_id, data, tenant_id, timestamp)
SELECT
  'evt_seed_demo_001',
  'student.submission',
  'api',
  'lrn_demo_student',
  '{"knowledge_id":"fractions","is_correct":true,"seed":"demo"}'::jsonb,
  1,
  now() - interval '18 hours'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE public_id = 'evt_seed_demo_001');

INSERT INTO events (public_id, type, source, learner_public_id, data, tenant_id, timestamp)
SELECT
  'evt_seed_demo_002',
  'tutor.teaching_response',
  'TutorAgent',
  'lrn_demo_student',
  '{"knowledge_id":"linear_eq_1","response":"让我们一步步拆方程。","seed":"demo"}'::jsonb,
  1,
  now() - interval '10 hours'
WHERE NOT EXISTS (SELECT 1 FROM events WHERE public_id = 'evt_seed_demo_002');

COMMIT;

-- 审计 HMAC 链依赖运行时 secret,由 scripts/seed_demo_data.py 追加写入。
