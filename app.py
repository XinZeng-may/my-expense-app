import streamlit as st
import pandas as pd

st.set_page_config(page_title="记账小工具", layout="wide")

st.title("记账小工具")

if "records" not in st.session_state:
    st.session_state.records = []

with st.form("expense_form"):
    date = st.date_input("日期")
    amount = st.number_input("金额", min_value=0.0, step=1.0)
    category = st.selectbox("分类", ["餐饮", "交通", "购物", "房租", "娱乐", "其他"])
    note = st.text_input("备注")

    submitted = st.form_submit_button("添加记录")

    if submitted:
        st.session_state.records.append({
            "日期": str(date),
            "金额": amount,
            "分类": category,
            "备注": note
        })
        st.success("已添加")

st.subheader("记录")

if st.session_state.records:
    df = pd.DataFrame(st.session_state.records)
    st.dataframe(df, use_container_width=True)
    st.metric("总金额", f"${df['金额'].sum():.2f}")
else:
    st.info("还没有记录")
