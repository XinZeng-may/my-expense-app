import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import date

st.set_page_config(
    page_title="情侣记账本",
    page_icon="💸",
    layout="wide"
)

# -----------------------------
# 自定义样式
# -----------------------------
st.markdown("""
<style>
.main {
    background-color: #f7f8fc;
}
.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
}
h1, h2, h3 {
    color: #1f2937;
}
.stMetric {
    background: white;
    border-radius: 16px;
    padding: 16px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.06);
}
.card {
    background: white;
    padding: 18px;
    border-radius: 18px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.06);
    margin-bottom: 16px;
}
.small-title {
    font-size: 15px;
    font-weight: 600;
    color: #6b7280;
    margin-bottom: 10px;
}
.big-title {
    font-size: 28px;
    font-weight: 800;
    color: #111827;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Supabase 初始化
# -----------------------------
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# -----------------------------
# 数据读取函数
# -----------------------------
def load_users():
    response = supabase.table("users").select("*").order("created_at").execute()
    data = response.data if response.data else []
    return pd.DataFrame(data)

def load_categories():
    response = supabase.table("categories").select("*").order("parent_category").execute()
    data = response.data if response.data else []
    return pd.DataFrame(data)

def load_expenses():
    response = (
        supabase.table("expenses")
        .select("*")
        .order("expense_date", desc=True)
        .execute()
    )
    data = response.data if response.data else []
    return pd.DataFrame(data)

# -----------------------------
# 新增函数
# -----------------------------
def add_user(name):
    if not name.strip():
        return
    supabase.table("users").insert({
        "name": name.strip()
    }).execute()

def add_category(parent_category, sub_category):
    if not parent_category.strip() or not sub_category.strip():
        return
    supabase.table("categories").insert({
        "parent_category": parent_category.strip(),
        "sub_category": sub_category.strip()
    }).execute()

def add_expense(expense_date, amount, user_name, bill_type, parent_category, sub_category, note):
    supabase.table("expenses").insert({
        "expense_date": str(expense_date),
        "amount": float(amount),
        "user_name": user_name,
        "bill_type": bill_type,
        "parent_category": parent_category,
        "sub_category": sub_category,
        "note": note
    }).execute()

# -----------------------------
# 初始化基础数据
# -----------------------------
users_df = load_users()
categories_df = load_categories()
expenses_df = load_expenses()

# -----------------------------
# 标题区
# -----------------------------
st.markdown('<div class="big-title">💸 情侣记账本</div>', unsafe_allow_html=True)
st.caption("支持自定义用户、自定义二级分类、个人/共同账单管理")

# -----------------------------
# 侧边栏：基础设置
# -----------------------------
with st.sidebar:
    st.header("⚙️ 基础设置")

    with st.expander("添加用户", expanded=False):
        new_user = st.text_input("用户名称", placeholder="例如：Xin / 添翼")
        if st.button("添加用户"):
            add_user(new_user)
            st.success("用户已添加")
            st.rerun()

    with st.expander("添加分类", expanded=False):
        parent = st.text_input("一级分类", placeholder="例如：交通")
        sub = st.text_input("二级分类", placeholder="例如：油费")
        if st.button("添加分类"):
            add_category(parent, sub)
            st.success("分类已添加")
            st.rerun()

    st.markdown("---")
    st.subheader("筛选记录")

    all_users = ["全部"] + (users_df["name"].tolist() if not users_df.empty else [])
    selected_user_filter = st.selectbox("按用户筛选", all_users)

    all_bill_types = ["全部", "个人", "共同"]
    selected_bill_filter = st.selectbox("按账单类型筛选", all_bill_types)

# -----------------------------
# 没有基础数据时的提示
# -----------------------------
if users_df.empty:
    st.warning("请先在左侧添加用户后再开始记账。")
    st.stop()

if categories_df.empty:
    st.warning("请先在左侧添加分类后再开始记账。")
    st.stop()

# -----------------------------
# 记账表单
# -----------------------------
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("➕ 添加一笔记录")

col1, col2, col3 = st.columns(3)
with col1:
    selected_date = st.date_input("日期", value=date.today())
with col2:
    amount = st.number_input("金额", min_value=0.0, step=1.0, format="%.2f")
with col3:
    user_name = st.selectbox("记账用户", users_df["name"].tolist())

col4, col5, col6 = st.columns(3)
with col4:
    bill_type = st.selectbox("账单类型", ["个人", "共同"])
with col5:
    parent_options = sorted(categories_df["parent_category"].dropna().unique().tolist())
    selected_parent = st.selectbox("一级分类", parent_options)

filtered_sub_df = categories_df[categories_df["parent_category"] == selected_parent]
sub_options = filtered_sub_df["sub_category"].dropna().unique().tolist()

with col6:
    selected_sub = st.selectbox("二级分类", sub_options)

note = st.text_input("备注", placeholder="例如：牛夫卫 / Costco / 407")

if st.button("保存这笔记录", use_container_width=True):
    add_expense(
        selected_date,
        amount,
        user_name,
        bill_type,
        selected_parent,
        selected_sub,
        note
    )
    st.success("已添加到数据库")
    st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------
# 数据处理
# -----------------------------
df = load_expenses()

if not df.empty:
    df["amount"] = df["amount"].astype(float)

    filtered_df = df.copy()

    if selected_user_filter != "全部":
        filtered_df = filtered_df[filtered_df["user_name"] == selected_user_filter]

    if selected_bill_filter != "全部":
        filtered_df = filtered_df[filtered_df["bill_type"] == selected_bill_filter]

    # 统计区
    total_amount = filtered_df["amount"].sum() if not filtered_df.empty else 0
    personal_amount = filtered_df[filtered_df["bill_type"] == "个人"]["amount"].sum() if not filtered_df.empty else 0
    common_amount = filtered_df[filtered_df["bill_type"] == "共同"]["amount"].sum() if not filtered_df.empty else 0
    record_count = len(filtered_df)

    st.subheader("📊 本页统计")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("总支出", f"${total_amount:,.2f}")
    m2.metric("个人支出", f"${personal_amount:,.2f}")
    m3.metric("共同支出", f"${common_amount:,.2f}")
    m4.metric("记录数", f"{record_count}")

    # 分类汇总
    st.subheader("📁 分类汇总")
    category_summary = (
        filtered_df.groupby(["parent_category", "sub_category"], as_index=False)["amount"]
        .sum()
        .sort_values("amount", ascending=False)
    )
    st.dataframe(category_summary, use_container_width=True, hide_index=True)

    # 记录表
    st.subheader("🧾 记账记录")
    show_df = filtered_df[[
        "expense_date", "user_name", "bill_type",
        "parent_category", "sub_category", "amount", "note", "created_at"
    ]].copy()

    show_df = show_df.rename(columns={
        "expense_date": "日期",
        "user_name": "用户",
        "bill_type": "类型",
        "parent_category": "一级分类",
        "sub_category": "二级分类",
        "amount": "金额",
        "note": "备注",
        "created_at": "创建时间"
    })

    st.dataframe(show_df, use_container_width=True, hide_index=True)

else:
    st.info("还没有记录，先添加第一笔吧。")
