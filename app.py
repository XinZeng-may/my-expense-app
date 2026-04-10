import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import date

st.set_page_config(page_title="情侣记账本", page_icon="💸", layout="wide")

FIXED_PARENT_CATEGORIES = ["餐饮", "交通", "居家", "购物", "娱乐", "医疗", "学习", "其他"]

# -----------------------------
# 自定义样式
# -----------------------------
st.markdown(
    """
<style>
.main {
    background: #f6f8fc;
}
.block-container {
    padding-top: 1.4rem;
    padding-bottom: 1.6rem;
}
.top-title {
    background: linear-gradient(135deg, #ffffff 0%, #f0f6ff 100%);
    border: 1px solid #e5eaf5;
    border-radius: 20px;
    padding: 20px;
    margin-bottom: 18px;
    box-shadow: 0 8px 20px rgba(67, 97, 238, 0.06);
}
.title-main {
    font-size: 31px;
    font-weight: 800;
    color: #0f172a;
    margin: 0;
}
.title-sub {
    color: #475569;
    margin-top: 8px;
    margin-bottom: 0;
    font-size: 15px;
}
.card {
    background: #ffffff;
    border-radius: 18px;
    border: 1px solid #e6eaf3;
    padding: 18px;
    box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
    margin-bottom: 16px;
}
.section-title {
    color: #1e293b;
    font-size: 20px;
    margin: 0 0 8px 0;
}
.helper-text {
    color: #64748b;
    font-size: 13px;
    margin-bottom: 10px;
}
.stat-card {
    background: #ffffff;
    border-radius: 16px;
    border: 1px solid #e6eaf3;
    padding: 12px 16px;
    box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
}
.stat-label {
    color: #64748b;
    font-size: 12px;
}
.stat-value {
    color: #0f172a;
    font-size: 24px;
    font-weight: 700;
}
</style>
""",
    unsafe_allow_html=True,
)


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
    return pd.DataFrame(response.data if response.data else [])


def load_categories():
    response = supabase.table("categories").select("*").order("parent_category").execute()
    return pd.DataFrame(response.data if response.data else [])


def load_expenses():
    response = (
        supabase.table("expenses")
        .select("*")
        .order("expense_date", desc=True)
        .order("created_at", desc=True)
        .execute()
    )
    return pd.DataFrame(response.data if response.data else [])


# -----------------------------
# 新增函数
# -----------------------------
def add_user(name: str):
    cleaned = name.strip()
    if not cleaned:
        return
    supabase.table("users").insert({"name": cleaned}).execute()


def add_category(parent_category: str, sub_category: str):
    parent = parent_category.strip()
    sub = sub_category.strip()
    if not parent or not sub:
        return
    if parent not in FIXED_PARENT_CATEGORIES:
        return
    supabase.table("categories").insert({"parent_category": parent, "sub_category": sub}).execute()


def add_expense(
    expense_date,
    amount,
    user_name,
    bill_type,
    parent_category,
    sub_category,
    note,
):
    if amount < 0:
        return

    supabase.table("expenses").insert(
        {
            "expense_date": str(expense_date),
            "amount": float(amount),
            "user_name": user_name,
            "bill_type": bill_type,
            "parent_category": parent_category,
            "sub_category": sub_category,
            "note": note.strip(),
        }
    ).execute()


# -----------------------------
# 初始化数据
# -----------------------------
users_df = load_users()
categories_df = load_categories()
expenses_df = load_expenses()


# -----------------------------
# 顶部标题区
# -----------------------------
st.markdown(
    """
<div class='top-title'>
  <p class='title-main'>💸 情侣/家庭记账助手</p>
  <p class='title-sub'>帮助情侣快速记账，清晰查看共同与个人支出，支持长期日常使用。</p>
</div>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# 左侧设置区
# -----------------------------
with st.sidebar:
    st.header("⚙️ 设置区")

    with st.expander("添加用户", expanded=False):
        new_user = st.text_input("用户名称", placeholder="例如：小林 / 小雨")
        if st.button("添加用户", use_container_width=True):
            add_user(new_user)
            st.success("用户已添加")
            st.rerun()

    with st.expander("添加二级分类", expanded=False):
        selected_parent_for_new = st.selectbox("一级分类（固定）", FIXED_PARENT_CATEGORIES)
        new_sub = st.text_input("二级分类名称", placeholder="例如：奶茶 / 地铁 / 宠物用品")

        if st.button("添加二级分类", use_container_width=True):
            existing_sub = categories_df[
                (categories_df["parent_category"] == selected_parent_for_new)
                & (categories_df["sub_category"] == new_sub.strip())
            ] if not categories_df.empty else pd.DataFrame()

            if not new_sub.strip():
                st.warning("请输入二级分类名称")
            elif not existing_sub.empty:
                st.warning("该二级分类已存在")
            else:
                add_category(selected_parent_for_new, new_sub)
                st.success("二级分类已添加")
                st.rerun()

    st.markdown("---")
    st.subheader("筛选记录")
    all_users = ["全部"] + (users_df["name"].tolist() if not users_df.empty else [])
    selected_user_filter = st.selectbox("按用户筛选", all_users)
    selected_bill_filter = st.selectbox("按账单类型筛选", ["全部", "个人", "共同"])

    if st.button("🔄 刷新最新数据", use_container_width=True):
        st.rerun()

# -----------------------------
# 空数据提示
# -----------------------------
if users_df.empty:
    st.warning("请先在左侧设置区添加用户，再开始记账。")
    st.stop()

if categories_df.empty:
    st.warning("请先在左侧设置区添加至少一个二级分类，再开始记账。")
    st.stop()

# -----------------------------
# 中间添加记录表单
# -----------------------------
st.markdown("<div class='card'>", unsafe_allow_html=True)
st.markdown("<p class='section-title'>➕ 添加记录</p>", unsafe_allow_html=True)
st.markdown(
    "<p class='helper-text'>金额必须 ≥ 0，二级分类会随一级分类自动变化。</p>",
    unsafe_allow_html=True,
)

row1_col1, row1_col2, row1_col3 = st.columns(3)
with row1_col1:
    selected_date = st.date_input("日期", value=date.today())
with row1_col2:
    amount = st.number_input("金额", min_value=0.0, step=1.0, format="%.2f")
with row1_col3:
    user_name = st.selectbox("记账用户", users_df["name"].tolist())

row2_col1, row2_col2, row2_col3 = st.columns(3)
with row2_col1:
    bill_type = st.selectbox("账单类型", ["个人", "共同"])
with row2_col2:
    selected_parent = st.selectbox("一级分类（固定）", FIXED_PARENT_CATEGORIES)

available_sub_df = categories_df[categories_df["parent_category"] == selected_parent]
available_sub_options = sorted(available_sub_df["sub_category"].dropna().unique().tolist())
with row2_col3:
    if available_sub_options:
        selected_sub = st.selectbox("二级分类", available_sub_options)
    else:
        selected_sub = ""
        st.warning("该一级分类下还没有二级分类，请先去左侧添加。")

note = st.text_input("备注", placeholder="例如：晚餐AA / Costco补货 / 高铁")

if st.button("保存记录", use_container_width=True):
    if not selected_sub:
        st.error("请先补充该一级分类下的二级分类。")
    elif amount < 0:
        st.error("金额必须大于等于 0。")
    else:
        add_expense(
            selected_date,
            amount,
            user_name,
            bill_type,
            selected_parent,
            selected_sub,
            note,
        )
        st.success("已写入 Supabase，并刷新最新数据。")
        st.rerun()

st.markdown("</div>", unsafe_allow_html=True)

# -----------------------------
# 下方统计卡片 + 分类汇总区 + 记录表格区
# -----------------------------
df = expenses_df.copy()

if not df.empty:
    df["amount"] = df["amount"].astype(float)
    filtered_df = df.copy()

    if selected_user_filter != "全部":
        filtered_df = filtered_df[filtered_df["user_name"] == selected_user_filter]
    if selected_bill_filter != "全部":
        filtered_df = filtered_df[filtered_df["bill_type"] == selected_bill_filter]

    total_amount = filtered_df["amount"].sum() if not filtered_df.empty else 0.0
    personal_amount = (
        filtered_df[filtered_df["bill_type"] == "个人"]["amount"].sum()
        if not filtered_df.empty
        else 0.0
    )
    common_amount = (
        filtered_df[filtered_df["bill_type"] == "共同"]["amount"].sum()
        if not filtered_df.empty
        else 0.0
    )
    record_count = len(filtered_df)

    st.subheader("📊 统计卡片")
    s1, s2, s3, s4 = st.columns(4)
    s1.markdown(
        f"<div class='stat-card'><div class='stat-label'>总支出</div><div class='stat-value'>${total_amount:,.2f}</div></div>",
        unsafe_allow_html=True,
    )
    s2.markdown(
        f"<div class='stat-card'><div class='stat-label'>个人支出</div><div class='stat-value'>${personal_amount:,.2f}</div></div>",
        unsafe_allow_html=True,
    )
    s3.markdown(
        f"<div class='stat-card'><div class='stat-label'>共同支出</div><div class='stat-value'>${common_amount:,.2f}</div></div>",
        unsafe_allow_html=True,
    )
    s4.markdown(
        f"<div class='stat-card'><div class='stat-label'>记录数</div><div class='stat-value'>{record_count}</div></div>",
        unsafe_allow_html=True,
    )

    st.subheader("📁 分类汇总区")
    category_summary = (
        filtered_df.groupby(["parent_category", "sub_category"], as_index=False)["amount"]
        .sum()
        .sort_values("amount", ascending=False)
    )
    category_summary = category_summary.rename(
        columns={"parent_category": "一级分类", "sub_category": "二级分类", "amount": "金额"}
    )
    st.dataframe(category_summary, use_container_width=True, hide_index=True)

    st.subheader("🧾 记录表格区")
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
else:
    st.info("还没有记录，先添加第一笔吧。")
