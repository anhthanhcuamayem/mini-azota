-- Schema Supabase cho Azota Mini / Olympia PRO
-- Chạy 1 lần trong Supabase Dashboard -> SQL Editor -> New query -> Run.
-- Server dùng service-role key nên bỏ qua RLS; RLS bật + không policy = chặn anon key.

-- ------------------------------------------------------------------ tài khoản
create table if not exists accounts (
    id            text primary key,
    email         text not null unique,
    name          text not null,
    role          text not null check (role in ('teacher', 'student')),
    password_hash text not null,
    created_at    text not null
);

create table if not exists auth_sessions (
    token      text primary key,
    user_id    text not null,
    created_at text not null
);

-- ------------------------------------------------------------------ lớp & tổ
-- roles    : vai trò TỰ TẠO của lớp [{id, name, permissions[], created_at}]
-- members[].role : id vai trò tùy chỉnh hoặc 1 trong các giá trị hệ thống:
--                  student | vice_class_monitor | class_monitor | team_leader
create table if not exists classes (
    id         text primary key,
    name       text not null,
    grade      text default '',
    teacher_id text not null,
    join_code  text not null unique,
    teams      jsonb not null default '[]'::jsonb,
    members    jsonb not null default '[]'::jsonb,
    roles      jsonb not null default '[]'::jsonb,
    created_at text not null
);

-- Nâng cấp database đã chạy từ trước (an toàn, chạy lại nhiều lần vẫn được):
alter table classes add column if not exists roles jsonb not null default '[]'::jsonb;

-- ------------------------------------------- kho bộ đề (nhiều môn/chủ đề)
-- Dùng cho phòng thi ẩn danh: học sinh tự chọn bộ đề để làm.
create table if not exists quizzes (
    id          text primary key,
    title       text not null,
    subject     text default '',
    mode        text not null default 'shared' check (mode in ('shared', 'random')),
    questions   jsonb not null default '[]'::jsonb,
    source_text text default '',
    filename    text default '',
    created_at  text not null,
    updated_at  text
);

-- -------------------------------------------------- đề thi gán cho lớp (portal)
create table if not exists exams (
    id               text primary key,
    title            text not null,
    subject          text default '',
    created_by       text not null,
    quiz_id          text,
    mode             text not null default 'shared',
    duration_minutes integer not null default 60,
    questions        jsonb not null default '[]'::jsonb,
    source_text      text default '',
    filename         text default '',
    class_ids        jsonb not null default '[]'::jsonb,
    published        boolean not null default false,
    start_at         text,
    end_at           text,
    created_at       text not null
);

-- ------------------------------------------------ phiên làm bài (đang thi)
create table if not exists exam_sessions (
    session_id         text primary key,
    name               text default '',
    user_id            text,
    exam_id            text,
    quiz_id            text,
    start_time         text not null,
    shuffled_questions jsonb not null default '[]'::jsonb
);

-- ------------------------------------------------------------------ bài nộp
create table if not exists attempts (
    id           text primary key,
    source       text not null default 'portal' check (source in ('portal', 'anonymous')),
    exam_id      text,
    quiz_id      text,
    exam_title   text default '',
    user_id      text,
    user_name    text default '',
    score        integer not null default 0,
    total        integer not null default 0,
    duration_sec integer not null default 0,
    started_at   text,
    submitted_at text default '',
    answers      jsonb not null default '[]'::jsonb
);

create index if not exists idx_exam_sessions_user on exam_sessions (user_id);
create index if not exists idx_attempts_exam on attempts (exam_id);
create index if not exists idx_attempts_quiz on attempts (quiz_id);
create index if not exists idx_attempts_user on attempts (user_id);

-- Bật RLS nhưng không tạo policy: anon key không đọc/ghi được.
-- Server dùng service-role key nên vẫn hoạt động bình thường.
alter table accounts enable row level security;
alter table auth_sessions enable row level security;
alter table classes enable row level security;
alter table quizzes enable row level security;
alter table exams enable row level security;
alter table exam_sessions enable row level security;
alter table attempts enable row level security;
