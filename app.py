from datetime import date

import pandas as pd
import streamlit as st
from supabase import Client, create_client

st.set_page_config(page_title="情侣记账本", page_icon="💸", layout="wide")

# 固定一级分类（业务规则）
FIXED_PARENT_CATEGORIES = ["餐饮", "交通", "居家", "购物", "娱乐", "医疗", "学习", "其他"]

st.markdown(
    """
<style>
.main { background: #f6f8fc; }
.block-container { padding-top: 1.2rem; padding-bottom: 1.4rem; }
.top-banner {
    background: linear-gradient(135deg, #ffffff 0%, #f1f7ff 100%);
    border: 1px solid #e3eaf5;
    border-radius: 16px;
    padding: 18px;
    margin-bottom: 14px;
}
.top-title { margin: 0; color: #0f172a; font-size: 30px; font-weight: 800; }
.top-subtitle { margin: 6px 0 0 0; color: #475569; font-size: 14px; }
.panel {
    background: #ffffff;
    border: 1px solid #e5eaf3;
    border-radius: 16px;
    padding: 16px;
    box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
    margin-bottom: 14px;
}
.stat-card {
    background: #ffffff;
    border: 1px solid #e5eaf3;
    border-radius: 14px;
    padding: 12px 14px;
    box-shadow: 0 6px 16px rgba(15, 23, 42, 0.05);
}
.stat-label { color: #64748b; font-size: 12px; }
.stat-value { color: #0f172a; font-size: 23px; font-weight: 700; }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def init_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


supabase = init_supabase()


def load_users() -> pd.DataFrame:
    response = supabase.table("users").select("*").order("created_at").execute()
    return pd.DataFrame(response.data or [])


def load_categories() -> pd.DataFrame:
    response = (
        supabase.table("categories")
        .select("*")
        .order("parent_category")
        .order("sub_category")
        .execute()
    )
    return pd.DataFrame(response.data or [])


def load_expenses() -> pd.DataFrame:
    response = (
        supabase.table("expenses")
        .select("*")
        .order("expense_date", desc=True)
        .order("created_at", desc=True)
        .execute()
    )
    return pd.DataFrame(response.data or [])


def add_user(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        return "用户名称不能为空。"

    existing = supabase.table("users").select("id").eq("name", cleaned).limit(1).execute()
    if existing.data:
        return "该用户已存在。"

    supabase.table("users").insert({"name": cleaned}).execute()
    return "ok"


def add_sub_category(parent_category: str, sub_category: str) -> str:
    parent = parent_category.strip()
    sub = sub_category.strip()

    if parent not in FIXED_PARENT_CATEGORIES:
        return "一级分类不合法。"
    if not sub:
        return "二级分类名称不能为空。"

    existing = (
        supabase.table("categories")
        .select("id")
        .eq("parent_category", parent)
        .eq("sub_category", sub)
        .limit(1)
        .execute()
    )
    if existing.data:
        return "该二级分类已存在。"

    supabase.table("categories").insert({"parent_category": parent, "sub_category": sub}).execute()
    return "ok"




def ensure_expense_columns(df: pd.DataFrame) -> pd.DataFrame:
    expected_defaults = {
        "expense_date": pd.NaT,
        "amount": 0.0,
        "user_name": "",
        "bill_type": "个人",
        "parent_category": "其他",
        "sub_category": "未分类",
        "note": "",
        "created_at": "",
    }

    normalized = df.copy()
    for col, default in expected_defaults.items():
        if col not in normalized.columns:
            normalized[col] = default

    normalized["bill_type"] = normalized["bill_type"].fillna("个人").astype(str)
    normalized.loc[~normalized["bill_type"].isin(["个人", "共同"]), "bill_type"] = "个人"

    normalized["parent_category"] = normalized["parent_category"].fillna("其他").astype(str)
    normalized.loc[~normalized["parent_category"].isin(FIXED_PARENT_CATEGORIES), "parent_category"] = "其他"

    normalized["sub_category"] = normalized["sub_category"].fillna("未分类").astype(str)
    normalized["user_name"] = normalized["user_name"].fillna("").astype(str)
    normalized["note"] = normalized["note"].fillna("").astype(str)

    normalized["amount"] = pd.to_numeric(normalized["amount"], errors="coerce").fillna(0.0)
    normalized["expense_date"] = pd.to_datetime(normalized["expense_date"], errors="coerce")

    return normalized


def add_expense_record(
    expense_date: date,
    amount: float,
    user_name: str,
    bill_type: str,
    parent_category: str,
    sub_category: str,
    note: str,
) -> str:
    if amount < 0:
        return "金额必须大于等于 0。"
    if bill_type not in ["个人", "共同"]:
        return "账单类型不合法。"
    if parent_category not in FIXED_PARENT_CATEGORIES:
        return "一级分类不合法。"
    if not sub_category.strip():
        return "请先选择二级分类。"

    supabase.table("expenses").insert(
        {
            "expense_date": str(expense_date),
            "amount": float(amount),
            "user_name": user_name,
            "bill_type": bill_type,
            "parent_category": parent_category,
            "sub_category": sub_category.strip(),
            "note": note.strip(),
        }
    ).execute()
    return "ok"


users_df = load_users()
categories_df = load_categories()
expenses_df = load_expenses()

# 顶部标题区
st.markdown(
    """
<div class='top-banner'>
  <p class='top-title'>💸 情侣记账本</p>
  <p class='top-subtitle'>帮助情侣/小家庭快速记账，查看共同与个人支出。</p>
</div>
""",
    unsafe_allow_html=True,
)

# 左侧设置区
with st.sidebar:
    st.header("⚙️ 设置区")

    with st.expander("添加用户", expanded=False):
        with st.form("add_user_form", clear_on_submit=True):
            new_user = st.text_input("用户名称", placeholder="例如：小林 / 小雨")
            submitted_user = st.form_submit_button("保存用户", use_container_width=True)
        if submitted_user:
            result = add_user(new_user)
            if result == "ok":
                st.success("用户已添加。")
                st.rerun()
            else:
                st.warning(result)

    with st.expander("添加二级分类", expanded=False):
        with st.form("add_sub_category_form", clear_on_submit=True):
            parent_for_new = st.selectbox("一级分类（固定）", FIXED_PARENT_CATEGORIES)
            sub_for_new = st.text_input("二级分类名称", placeholder="例如：奶茶 / 地铁 / 电费")
            submitted_sub = st.form_submit_button("保存二级分类", use_container_width=True)
        if submitted_sub:
            result = add_sub_category(parent_for_new, sub_for_new)
            if result == "ok":
                st.success("二级分类已添加。")
                st.rerun()
            else:
                st.warning(result)

    st.divider()
    st.subheader("筛选记录")

    user_filter_options = ["全部"] + users_df["name"].tolist() if not users_df.empty else ["全部"]
    selected_user_filter = st.selectbox("按用户", user_filter_options)
    selected_bill_filter = st.selectbox("按账单类型", ["全部", "个人", "共同"])

    min_day = date(2020, 1, 1)
    max_day = date.today()
    date_range = st.date_input("按日期区间", value=(max_day.replace(day=1), max_day), min_value=min_day, max_value=max_day)

    if st.button("🔄 刷新最新数据", use_container_width=True):
        st.rerun()

# 基础数据校验
if users_df.empty:
    st.warning("请先在左侧添加用户。")
    st.stop()

if categories_df.empty:
    st.warning("请先在左侧添加至少一个二级分类。")
    st.stop()

# 中间添加记录表单
st.markdown("<div class='panel'>", unsafe_allow_html=True)
st.subheader("➕ 添加记录")
st.caption("金额必须 ≥ 0；二级分类会随一级分类联动。保存后自动写入 Supabase 并刷新。")

with st.form("add_expense_form", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        selected_date = st.date_input("日期", value=date.today())
    with col2:
        amount = st.number_input("金额", min_value=0.0, step=1.0, format="%.2f")
    with col3:
        selected_user = st.selectbox("记账用户", users_df["name"].tolist())

    col4, col5, col6 = st.columns(3)
    with col4:
        selected_bill_type = st.selectbox("账单类型", ["个人", "共同"])
    with col5:
        selected_parent = st.selectbox("一级分类（固定）", FIXED_PARENT_CATEGORIES)

    sub_options_df = categories_df[categories_df["parent_category"] == selected_parent]
    sub_options = sub_options_df["sub_category"].dropna().tolist()
    sub_options = sorted(list(dict.fromkeys(sub_options)))

    with col6:
        if sub_options:
            selected_sub = st.selectbox("二级分类", sub_options)
        else:
            selected_sub = ""
            st.warning("该一级分类下没有二级分类，请先在左侧添加。")

    note = st.text_input("备注", placeholder="例如：午餐AA / Costco补货")
    submitted_expense = st.form_submit_button("保存记录", use_container_width=True)

if submitted_expense:
    result = add_expense_record(
        expense_date=selected_date,
        amount=amount,
        user_name=selected_user,
        bill_type=selected_bill_type,
        parent_category=selected_parent,
        sub_category=selected_sub,
        note=note,
    )
    if result == "ok":
        st.success("已写入 Supabase，页面已刷新最新数据。")
        st.rerun()
    else:
        st.error(result)

st.markdown("</div>", unsafe_allow_html=True)

# 下方统计卡片 / 分类汇总区 / 记录表格区
if expenses_df.empty:
    st.info("还没有记录，先添加第一笔吧。")
    st.stop()

df = ensure_expense_columns(expenses_df)
filtered_df = df.copy()

if selected_user_filter != "全部":
    filtered_df = filtered_df[filtered_df["user_name"] == selected_user_filter]
if selected_bill_filter != "全部":
    filtered_df = filtered_df[filtered_df["bill_type"] == selected_bill_filter]

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_day, end_day = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    filtered_df = filtered_df[
        (filtered_df["expense_date"] >= start_day)
        & (filtered_df["expense_date"] <= end_day)
    ]

st.subheader("📊 统计卡片")
total_amount = filtered_df["amount"].sum() if not filtered_df.empty else 0.0
personal_amount = (
    filtered_df[filtered_df["bill_type"] == "个人"]["amount"].sum() if not filtered_df.empty else 0.0
)
shared_amount = (
    filtered_df[filtered_df["bill_type"] == "共同"]["amount"].sum() if not filtered_df.empty else 0.0
)
record_count = len(filtered_df)

s1, s2, s3, s4 = st.columns(4)
s1.markdown(
    f"<div class='stat-card'><div class='stat-label'>总支出</div><div class='stat-value'>¥{total_amount:,.2f}</div></div>",
    unsafe_allow_html=True,
)
s2.markdown(
    f"<div class='stat-card'><div class='stat-label'>个人支出</div><div class='stat-value'>¥{personal_amount:,.2f}</div></div>",
    unsafe_allow_html=True,
)
s3.markdown(
    f"<div class='stat-card'><div class='stat-label'>共同支出</div><div class='stat-value'>¥{shared_amount:,.2f}</div></div>",
    unsafe_allow_html=True,
)
s4.markdown(
    f"<div class='stat-card'><div class='stat-label'>记录数</div><div class='stat-value'>{record_count}</div></div>",
    unsafe_allow_html=True,
)

st.subheader("📁 分类汇总区")
if filtered_df.empty:
    st.info("当前筛选条件下暂无数据。")
else:
    category_summary = (
        filtered_df.groupby(["parent_category", "sub_category"], as_index=False)["amount"]
        .sum()
        .sort_values("amount", ascending=False)
        .rename(columns={"parent_category": "一级分类", "sub_category": "二级分类", "amount": "金额"})
    )
    st.dataframe(category_summary, use_container_width=True, hide_index=True)

st.subheader("🧾 记录表格区")
if filtered_df.empty:
    st.info("当前筛选条件下暂无记录。")
else:
    show_df = filtered_df[
        [
            "expense_date",
            "user_name",
            "bill_type",
            "parent_category",
            "sub_category",
            "amount",
            "note",
            "created_at",
        ]
    ].copy()

    show_df["expense_date"] = show_df["expense_date"].dt.strftime("%Y-%m-%d")
    show_df = show_df.rename(
        columns={
            "expense_date": "日期",
            "user_name": "用户",
            "bill_type": "类型",
            "parent_category": "一级分类",
            "sub_category": "二级分类",
            "amount": "金额",
            "note": "备注",
            "created_at": "创建时间",
        }
    )
    st.dataframe(show_df, use_container_width=True, hide_index=True)
