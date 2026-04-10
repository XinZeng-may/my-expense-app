from datetime import date

import altair as alt
import pandas as pd
import streamlit as st
from supabase import Client, create_client

st.set_page_config(page_title="情侣记账本", page_icon="💸", layout="wide")

FIXED_PARENT_CATEGORIES = ["餐饮", "交通", "居家", "购物", "娱乐", "医疗", "学习", "其他"]
PAYMENT_METHODS = ["现金/借记卡", "信用卡", "转账", "其他"]

st.markdown(
    """
<style>
.main { background: #f6f8fc; }
.block-container { padding-top: 1.2rem; padding-bottom: 1.4rem; }
.card { background: #fff; border: 1px solid #e5eaf3; border-radius: 14px; padding: 14px; margin-bottom: 12px; }
.top-banner { background: #fff; border: 1px solid #e3eaf5; border-radius: 16px; padding: 16px; margin-bottom: 14px; }
.top-title { margin: 0; font-size: 28px; font-weight: 800; color: #0f172a; }
.top-subtitle { margin: 6px 0 0 0; color: #475569; }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def init_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


supabase = init_supabase()


def load_table_df(table_name: str, order_col: str | None = None, desc: bool = False) -> pd.DataFrame:
    q = supabase.table(table_name).select("*")
    if order_col:
        q = q.order(order_col, desc=desc)
    res = q.execute()
    return pd.DataFrame(res.data or [])


def add_user(name: str) -> str:
    name = name.strip()
    if not name:
        return "用户名不能为空"
    try:
        exists = supabase.table("users").select("id").eq("name", name).limit(1).execute()
        if exists.data:
            return "该用户已存在"
        supabase.table("users").insert({"name": name}).execute()
        return "ok"
    except Exception as e:
        return f"添加用户失败：{e}"


def add_sub_category(parent: str, sub: str) -> str:
    parent, sub = parent.strip(), sub.strip()
    if parent not in FIXED_PARENT_CATEGORIES:
        return "一级分类不合法"
    if not sub:
        return "二级分类不能为空"
    try:
        exists = (
            supabase.table("categories")
            .select("id")
            .eq("parent_category", parent)
            .eq("sub_category", sub)
            .limit(1)
            .execute()
        )
        if exists.data:
            return "该二级分类已存在"
        supabase.table("categories").insert({"parent_category": parent, "sub_category": sub}).execute()
        return "ok"
    except Exception as e:
        return f"添加分类失败：{e}"


def get_sub_options(categories_df: pd.DataFrame, parent: str) -> list[str]:
    if categories_df.empty:
        return []
    return sorted(categories_df[categories_df["parent_category"] == parent]["sub_category"].dropna().unique().tolist())


def add_expense_record(payload: dict) -> str:
    try:
        supabase.table("expenses").insert(payload).execute()
        return "ok"
    except Exception as e:
        return f"保存消费失败：{e}"


def add_cashflow_record(payload: dict) -> str:
    try:
        supabase.table("cashflows").insert(payload).execute()
        return "ok"
    except Exception as e:
        return f"保存现金流失败：{e}"


def add_credit_card(payload: dict) -> str:
    try:
        exists = supabase.table("credit_cards").select("id").eq("card_name", payload["card_name"]).limit(1).execute()
        if exists.data:
            return "该信用卡已存在"
        supabase.table("credit_cards").insert(payload).execute()
        return "ok"
    except Exception as e:
        return f"添加信用卡失败：{e}"


users_df = load_table_df("users", "created_at")
categories_df = load_table_df("categories", "parent_category")
expenses_df = load_table_df("expenses", "expense_date", desc=True)
cashflows_df = load_table_df("cashflows", "flow_date", desc=True)
cards_df = load_table_df("credit_cards", "created_at", desc=True)

st.markdown("""
<div class='top-banner'>
  <p class='top-title'>💸 情侣记账本</p>
  <p class='top-subtitle'>三大模块：记账页 / 现金流页 / 信用卡模块</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 设置")
    with st.expander("添加用户"):
        with st.form("f_user", clear_on_submit=True):
            u = st.text_input("用户名")
            s = st.form_submit_button("保存用户", use_container_width=True)
        if s:
            r = add_user(u)
            st.success("已保存") if r == "ok" else st.error(r)
            if r == "ok":
                st.rerun()

    with st.expander("添加二级分类"):
        with st.form("f_cat", clear_on_submit=True):
            p = st.selectbox("一级分类", FIXED_PARENT_CATEGORIES)
            sub = st.text_input("二级分类")
            sc = st.form_submit_button("保存分类", use_container_width=True)
        if sc:
            r = add_sub_category(p, sub)
            st.success("已保存") if r == "ok" else st.error(r)
            if r == "ok":
                st.rerun()

page1, page2, page3 = st.tabs(["🧾 记账页", "💵 现金流页", "💳 信用卡模块"])

with page1:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("记录消费")
    if users_df.empty:
        st.warning("请先在左侧添加用户")
    elif categories_df.empty:
        st.warning("请先在左侧添加二级分类")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            expense_date = st.date_input("日期", value=date.today(), key="p1_date")
        with c2:
            amount = st.number_input("金额", min_value=0.0, step=1.0, format="%.2f", key="p1_amt")
        with c3:
            user_name = st.selectbox("记账用户", users_df["name"].tolist(), key="p1_user")

        c4, c5, c6 = st.columns(3)
        with c4:
            bill_type = st.selectbox("账单类型", ["个人", "共同"], key="p1_bill")
        with c5:
            parent = st.selectbox("一级分类（固定）", FIXED_PARENT_CATEGORIES, key="p1_parent")

        sub_options = get_sub_options(categories_df, parent)
        sub_key = f"p1_sub_{parent}"
        if st.session_state.get(sub_key) not in sub_options and sub_options:
            st.session_state[sub_key] = sub_options[0]
        with c6:
            if sub_options:
                sub = st.selectbox("二级分类", sub_options, key=sub_key)
            else:
                sub = ""
                st.warning("该一级分类下暂无二级分类")

        c7, c8, c9 = st.columns(3)
        with c7:
            payment_method = st.selectbox("支付方式", PAYMENT_METHODS, key="p1_pay")
        with c8:
            if payment_method == "信用卡":
                card_options = cards_df["card_name"].tolist() if not cards_df.empty else []
                card_name = st.selectbox("信用卡名称", card_options, key="p1_card") if card_options else ""
                if not card_options:
                    st.info("请先在信用卡模块添加卡片")
            else:
                card_name = ""
                st.text_input("信用卡名称", value="非信用卡支付", disabled=True, key="p1_card_disabled")
        with c9:
            note = st.text_input("备注", key="p1_note")

        if st.button("保存消费原始数据", use_container_width=True, key="p1_save"):
            if payment_method == "信用卡" and not card_name:
                st.error("信用卡支付必须选择卡片")
            elif not sub:
                st.error("请先选择二级分类")
            else:
                payload = {
                    "expense_date": str(expense_date),
                    "amount": float(amount),
                    "user_name": user_name,
                    "bill_type": bill_type,
                    "parent_category": parent,
                    "sub_category": sub,
                    "payment_method": payment_method,
                    "card_name": card_name,
                    "note": note.strip(),
                }
                r = add_expense_record(payload)
                st.success("已保存") if r == "ok" else st.error(r)
                if r == "ok":
                    st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

with page2:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("现金流记录")
    flow_types = ["paycheck流入", "直接支付支出流出", "信用卡到期还款流出"]
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        flow_date = st.date_input("日期", value=date.today(), key="p2_date")
    with f2:
        flow_type = st.selectbox("类型", flow_types, key="p2_type")
    with f3:
        flow_amount = st.number_input("金额", min_value=0.0, step=1.0, format="%.2f", key="p2_amt")
    with f4:
        flow_user = st.selectbox("用户", users_df["name"].tolist() if not users_df.empty else [""], key="p2_user")
    flow_note = st.text_input("备注", key="p2_note")

    if st.button("保存现金流", use_container_width=True, key="p2_save"):
        payload = {
            "flow_date": str(flow_date),
            "flow_type": flow_type,
            "amount": float(flow_amount),
            "user_name": flow_user,
            "note": flow_note.strip(),
        }
        r = add_cashflow_record(payload)
        st.success("已保存") if r == "ok" else st.error(r)
        if r == "ok":
            st.rerun()

    if not cashflows_df.empty:
        cashflows_df["amount"] = pd.to_numeric(cashflows_df["amount"], errors="coerce").fillna(0.0)
        cashflows_df["flow_date"] = pd.to_datetime(cashflows_df["flow_date"], errors="coerce")
        month_start = pd.Timestamp(date.today().replace(day=1))
        month_df = cashflows_df[cashflows_df["flow_date"] >= month_start].copy()

        inflow = month_df[month_df["flow_type"] == "paycheck流入"]["amount"].sum()
        out_direct = month_df[month_df["flow_type"] == "直接支付支出流出"]["amount"].sum()
        out_card = month_df[month_df["flow_type"] == "信用卡到期还款流出"]["amount"].sum()
        net_cashflow = inflow - out_direct - out_card

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("本月paycheck流入", f"¥{inflow:,.2f}")
        m2.metric("本月直接支出流出", f"¥{out_direct:,.2f}")
        m3.metric("本月信用卡还款流出", f"¥{out_card:,.2f}")
        m4.metric("本月净现金流", f"¥{net_cashflow:,.2f}")
    st.markdown("</div>", unsafe_allow_html=True)

with page3:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("信用卡管理")

    with st.form("f_card", clear_on_submit=True):
        a, b, c, d = st.columns(4)
        with a:
            card_name = st.text_input("卡名（唯一）", placeholder="例如：CIBC Visa")
        with b:
            bill_day = st.number_input("账单日", min_value=1, max_value=31, step=1)
        with c:
            due_day = st.number_input("还款日", min_value=1, max_value=31, step=1)
        with d:
            cashback_rate = st.number_input("返现比例(%)", min_value=0.0, step=0.1, format="%.2f")
        cashback_rule = st.text_input("返现规则说明", placeholder="例如：餐饮3%，其他1%")
        save_card = st.form_submit_button("保存信用卡", use_container_width=True)

    if save_card:
        payload = {
            "card_name": card_name.strip(),
            "bill_day": int(bill_day),
            "due_day": int(due_day),
            "cashback_rate": float(cashback_rate),
            "cashback_rule": cashback_rule.strip(),
        }
        r = add_credit_card(payload)
        st.success("已保存") if r == "ok" else st.error(r)
        if r == "ok":
            st.rerun()

    if cards_df.empty:
        st.info("还没有信用卡，先添加一张。")
    else:
        st.dataframe(cards_df[["card_name", "bill_day", "due_day", "cashback_rate", "cashback_rule"]], use_container_width=True, hide_index=True)

        if not expenses_df.empty and "payment_method" in expenses_df.columns:
            expenses_df["amount"] = pd.to_numeric(expenses_df["amount"], errors="coerce").fillna(0.0)
            credit_df = expenses_df[expenses_df["payment_method"] == "信用卡"].copy()
            if not credit_df.empty:
                st.subheader("本期信用卡消费归集")
                card_pick = st.selectbox("选择信用卡", cards_df["card_name"].tolist(), key="p3_card_pick")
                card_expenses = credit_df[credit_df["card_name"] == card_pick].copy() if "card_name" in credit_df.columns else pd.DataFrame()

                if card_expenses.empty:
                    st.info("该卡目前没有已记录消费")
                else:
                    estimated_due = card_expenses["amount"].sum()
                    rate_series = cards_df[cards_df["card_name"] == card_pick]["cashback_rate"]
                    rate = float(rate_series.iloc[0]) if not rate_series.empty else 0.0
                    est_cashback = estimated_due * (rate / 100)

                    x1, x2 = st.columns(2)
                    x1.metric("预计待还金额", f"¥{estimated_due:,.2f}")
                    x2.metric("预计返现", f"¥{est_cashback:,.2f}")

                    summary = (
                        card_expenses.groupby(["parent_category", "sub_category"], as_index=False)["amount"]
                        .sum()
                        .sort_values("amount", ascending=False)
                    )
                    st.dataframe(summary, use_container_width=True, hide_index=True)

                    chart = (
                        alt.Chart(summary)
                        .mark_arc(innerRadius=40)
                        .encode(
                            theta=alt.Theta("amount:Q"),
                            color=alt.Color("parent_category:N", title="一级分类"),
                            tooltip=["parent_category", "sub_category", alt.Tooltip("amount:Q", format=".2f")],
                        )
                        .properties(height=300)
                    )
                    st.altair_chart(chart, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)
