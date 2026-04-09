import streamlit as st
import pandas as pd
from supabase import create_client, Client

st.set_page_config(page_title="记账小工具", layout="wide")

@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

def load_expenses():
    response = (
        supabase.table("expenses")
        .select("*")
        .order("expense_date", desc=True)
        .execute()
    )
    return pd.DataFrame(response.data)

def add_expense(expense_date, amount, category, note):
    (
        supabase.table("expenses")
        .insert({
            "expense_date": str(expense_date),
            "amount": amount,
            "category": category,
            "note": note
        })
        .execute()
    )

st.title("记账小工具")

with st.form("expense_form"):
    date = st.date_input("日期")
    amount = st.number_input("金额", min_value=0.0, step=1.0)
    category = st.selectbox("分类", ["餐饮", "交通", "购物", "房租", "娱乐", "其他"])
    note = st.text_input("备注")

    submitted = st.form_submit_button("添加记录")

    if submitted:
        add_expense(date, amount, category, note)
        st.success("已添加到数据库")
        st.rerun()

st.subheader("记录")

df = load_expenses()

if not df.empty:
    st.dataframe(df, use_container_width=True)
    st.metric("总金额", f"${df['amount'].astype(float).sum():.2f}")
else:
    st.info("还没有记录")
