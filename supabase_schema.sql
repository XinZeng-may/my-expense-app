-- 适用于 Supabase PostgreSQL
-- 作用：重建 users / categories / expenses 三张表，支持：
-- 1) 固定一级分类 + 可扩展二级分类
-- 2) 个人/共同账单
-- 3) 分人存储（user_id）
-- 4) 金额 >= 0

begin;

-- 如果你要彻底重建，先删旧表（注意会清空数据）
drop table if exists public.expenses cascade;
drop table if exists public.categories cascade;
drop table if exists public.users cascade;

create table public.users (
  id bigint generated always as identity primary key,
  name text not null,
  created_at timestamptz not null default now(),
  constraint users_name_unique unique (name)
);

create table public.categories (
  id bigint generated always as identity primary key,
  parent_category text not null,
  sub_category text not null,
  created_at timestamptz not null default now(),
  constraint categories_parent_check check (
    parent_category in ('餐饮','交通','居家','购物','娱乐','医疗','学习','其他')
  ),
  constraint categories_parent_sub_unique unique (parent_category, sub_category)
);

create table public.expenses (
  id bigint generated always as identity primary key,
  expense_date date not null default current_date,
  amount numeric(12,2) not null,
  user_id bigint not null,
  user_name text not null,
  bill_type text not null default '个人',
  parent_category text not null,
  sub_category text not null,
  note text not null default '',
  created_at timestamptz not null default now(),

  constraint expenses_amount_nonnegative check (amount >= 0),
  constraint expenses_bill_type_check check (bill_type in ('个人', '共同')),
  constraint expenses_parent_check check (
    parent_category in ('餐饮','交通','居家','购物','娱乐','医疗','学习','其他')
  ),
  constraint expenses_user_fk
    foreign key (user_id) references public.users(id)
    on update cascade
    on delete restrict,
  constraint expenses_category_fk
    foreign key (parent_category, sub_category)
    references public.categories(parent_category, sub_category)
    on update cascade
    on delete restrict
);

create index idx_expenses_expense_date on public.expenses(expense_date desc);
create index idx_expenses_user_id on public.expenses(user_id);
create index idx_expenses_bill_type on public.expenses(bill_type);
create index idx_expenses_parent_sub on public.expenses(parent_category, sub_category);

commit;

-- 可选：初始化几个常用二级分类
insert into public.categories (parent_category, sub_category)
values
  ('餐饮', '早餐'),
  ('餐饮', '午餐'),
  ('餐饮', '晚餐'),
  ('交通', '地铁'),
  ('交通', '打车'),
  ('居家', '水电燃气'),
  ('购物', '日用品'),
  ('娱乐', '电影'),
  ('医疗', '药品'),
  ('学习', '课程'),
  ('其他', '未分类')
on conflict do nothing;
