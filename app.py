import calendar
from datetime import date, timedelta
import altair as alt
import pandas as pd
import streamlit as st
from supabase import Client, create_client

st.set_page_config(page_title="情侣记账本", page_icon="💸", layout="wide")

FIXED_PARENT_CATEGORIES = ["餐饮", "交通", "居家", "购物", "娱乐", "医疗", "学习", "其他"]
PAYMENT_METHODS = ["现金/借记卡", "信用卡", "其他"]

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


def load_credit_cards() -> pd.DataFrame:
    try:
        response = supabase.table("credit_cards").select("*").order("card_name").execute()
        return pd.DataFrame(response.data or [])
    except Exception:
        return pd.DataFrame()
def load_paychecks() -> pd.DataFrame:
    try:
        response = (
            supabase.table("paychecks")
            .select("*")
            .order("user_name")
            .order("start_date")
            .execute()
        )
        return pd.DataFrame(response.data or [])
    except Exception:
        return pd.DataFrame()


def ensure_paycheck_columns(df: pd.DataFrame) -> pd.DataFrame:
    expected_defaults = {
        "id": 0,
        "user_name": "",
        "income_name": "工资",
        "amount": 0.0,
        "frequency": "biweekly",
        "start_date": pd.NaT,
        "second_day": None,
        "is_active": True,
        "created_at": "",
    }

    normalized = df.copy()
    for col, default in expected_defaults.items():
        if col not in normalized.columns:
            normalized[col] = default

    normalized["id"] = pd.to_numeric(normalized["id"], errors="coerce").fillna(0).astype(int)
    normalized["user_name"] = normalized["user_name"].fillna("").astype(str)
    normalized["income_name"] = normalized["income_name"].fillna("工资").astype(str)
    normalized["amount"] = pd.to_numeric(normalized["amount"], errors="coerce").fillna(0.0)
    normalized["frequency"] = normalized["frequency"].fillna("biweekly").astype(str)
    normalized["start_date"] = pd.to_datetime(normalized["start_date"], errors="coerce")
    normalized["second_day"] = pd.to_numeric(normalized["second_day"], errors="coerce")
    normalized["is_active"] = normalized["is_active"].fillna(True)

    return normalized


def add_paycheck_rule(
    user_name: str,
    income_name: str,
    amount: float,
    frequency: str,
    start_date_value: date,
    second_day: int | None,
) -> str:
    user_name = user_name.strip()
    income_name = income_name.strip()

    if not user_name:
        return "属于谁不能为空。"
    if not income_name:
        return "收入名称不能为空。"
    if amount <= 0:
        return "金额必须大于 0。"
    if frequency not in ["biweekly", "twice_a_month", "monthly"]:
        return "频率不合法。"
    if frequency == "twice_a_month":
        if second_day is None or second_day < 1 or second_day > 31:
            return "每月两次发薪时，第二个发薪日必须在 1 到 31 之间。"

    try:
        supabase.table("paychecks").insert(
            {
                "user_name": user_name,
                "income_name": income_name,
                "amount": float(amount),
                "frequency": frequency,
                "start_date": str(start_date_value),
                "second_day": int(second_day) if second_day is not None else None,
                "is_active": True,
            }
        ).execute()
        return "ok"
    except Exception as e:
        return f"保存 paycheck 规则失败：{e}"


def safe_day_in_month(year: int, month: int, day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(int(day), last_day))


def next_due_date_after(base_date: date, due_day: int) -> date:
    current_month_due = safe_day_in_month(base_date.year, base_date.month, due_day)

    # 同一天不算已经到期，推到下一个月
    if current_month_due > base_date:
        return current_month_due

    if base_date.month == 12:
        return safe_day_in_month(base_date.year + 1, 1, due_day)
    return safe_day_in_month(base_date.year, base_date.month + 1, due_day)


def generate_paycheck_events(paychecks_df: pd.DataFrame, range_start: date, range_end: date) -> pd.DataFrame:
    events = []

    if paychecks_df.empty:
        return pd.DataFrame(columns=["event_date", "user_name", "income_name", "amount", "event_type", "status"])

    for _, row in paychecks_df.iterrows():
        if not bool(row["is_active"]):
            continue

        user_name = str(row["user_name"])
        income_name = str(row["income_name"])
        amount = float(row["amount"])
        frequency = str(row["frequency"])

        if pd.isna(row["start_date"]):
            continue

        start_date_value = pd.to_datetime(row["start_date"]).date()

        if frequency == "biweekly":
            current = start_date_value
            while current < range_start:
                current += timedelta(days=14)

            while current <= range_end:
                events.append(
                    {
                        "event_date": current,
                        "user_name": user_name,
                        "income_name": income_name,
                        "amount": amount,
                        "event_type": "现金流入",
                        "status": "预计",
                    }
                )
                current += timedelta(days=14)

        elif frequency == "monthly":
            first_month = date(range_start.year, range_start.month, 1)
            last_month = date(range_end.year, range_end.month, 1)
            current_month = first_month

            while current_month <= last_month:
                pay_date = safe_day_in_month(current_month.year, current_month.month, start_date_value.day)
                if pay_date >= start_date_value and range_start <= pay_date <= range_end:
                    events.append(
                        {
                            "event_date": pay_date,
                            "user_name": user_name,
                            "income_name": income_name,
                            "amount": amount,
                            "event_type": "现金流入",
                            "status": "预计",
                        }
                    )

                if current_month.month == 12:
                    current_month = date(current_month.year + 1, 1, 1)
                else:
                    current_month = date(current_month.year, current_month.month + 1, 1)

        elif frequency == "twice_a_month":
            first_day = start_date_value.day
            second_pay_day = int(row["second_day"]) if pd.notna(row["second_day"]) else 30

            first_month = date(range_start.year, range_start.month, 1)
            last_month = date(range_end.year, range_end.month, 1)
            current_month = first_month

            while current_month <= last_month:
                for pay_day in sorted(set([first_day, second_pay_day])):
                    pay_date = safe_day_in_month(current_month.year, current_month.month, pay_day)
                    if pay_date >= start_date_value and range_start <= pay_date <= range_end:
                        events.append(
                            {
                                "event_date": pay_date,
                                "user_name": user_name,
                                "income_name": income_name,
                                "amount": amount,
                                "event_type": "现金流入",
                                "status": "预计",
                            }
                        )

                if current_month.month == 12:
                    current_month = date(current_month.year + 1, 1, 1)
                else:
                    current_month = date(current_month.year, current_month.month + 1, 1)

    return pd.DataFrame(events)


def generate_credit_due_schedule(source_df: pd.DataFrame, cards_df: pd.DataFrame) -> pd.DataFrame:
    if source_df.empty:
        return pd.DataFrame()

    credit_df = source_df[
        (source_df["payment_method"] == "信用卡")
        & (source_df["card_name"].fillna("") != "")
    ].copy()

    if credit_df.empty:
        return pd.DataFrame()

    if cards_df.empty:
        credit_df["owner_name"] = ""
        credit_df["payment_due_day"] = 1
        credit_df["cashback_rate"] = 0.0
    else:
        credit_df = credit_df.merge(
            cards_df[["card_name", "owner_name", "payment_due_day", "cashback_rate"]],
            on="card_name",
            how="left",
        )
        credit_df["payment_due_day"] = pd.to_numeric(
            credit_df["payment_due_day"], errors="coerce"
        ).fillna(1).astype(int)
        credit_df["cashback_rate"] = pd.to_numeric(
            credit_df["cashback_rate"], errors="coerce"
        ).fillna(0.0)

    credit_df["due_date"] = credit_df.apply(
        lambda row: next_due_date_after(
            pd.to_datetime(row["expense_date"]).date(),
            int(row["payment_due_day"]),
        ),
        axis=1,
    )

    credit_df["estimated_cashback"] = credit_df["adjusted_amount"] * credit_df["cashback_rate"]

    return credit_df
def load_cashback_rules() -> pd.DataFrame:
    try:
        response = (
            supabase.table("credit_card_cashback_rules")
            .select("*")
            .order("card_name")
            .order("category_name")
            .execute()
        )
        return pd.DataFrame(response.data or [])
    except Exception:
        return pd.DataFrame()

def apply_cashback_rules(
    credit_df: pd.DataFrame,
    cards_df: pd.DataFrame,
    cashback_rules_df: pd.DataFrame,
) -> pd.DataFrame:
    result = credit_df.copy()

    # 默认返现：来自信用卡主表
    default_rate_map = {}
    if not cards_df.empty and "card_name" in cards_df.columns and "cashback_rate" in cards_df.columns:
        for _, row in cards_df.iterrows():
            default_rate_map[str(row["card_name"])] = float(row["cashback_rate"] or 0)

    # 分类返现：来自规则表
    rule_map = {}
    if not cashback_rules_df.empty:
        for _, row in cashback_rules_df.iterrows():
            key = (str(row["card_name"]), str(row["category_name"]))
            rule_map[key] = float(row["cashback_rate"] or 0)
def load_credit_card_payments() -> pd.DataFrame:
    try:
        response = (
            supabase.table("credit_card_payments")
            .select("*")
            .order("payment_date", desc=True)
            .execute()
        )
        return pd.DataFrame(response.data or [])
    except Exception:
        return pd.DataFrame()


def ensure_credit_card_payment_columns(df: pd.DataFrame) -> pd.DataFrame:
    expected_defaults = {
        "id": 0,
        "payment_date": pd.NaT,
        "card_name": "",
        "amount": 0.0,
        "payer_name": "",
        "note": "",
        "created_at": "",
    }

    normalized = df.copy()
    for col, default in expected_defaults.items():
        if col not in normalized.columns:
            normalized[col] = default

    normalized["id"] = pd.to_numeric(normalized["id"], errors="coerce").fillna(0).astype(int)
    normalized["payment_date"] = pd.to_datetime(normalized["payment_date"], errors="coerce")
    normalized["card_name"] = normalized["card_name"].fillna("").astype(str)
    normalized["amount"] = pd.to_numeric(normalized["amount"], errors="coerce").fillna(0.0)
    normalized["payer_name"] = normalized["payer_name"].fillna("").astype(str)
    normalized["note"] = normalized["note"].fillna("").astype(str)

    return normalized


def add_credit_card_payment(
    payment_date_value: date,
    card_name: str,
    amount: float,
    payer_name: str,
    note: str,
) -> str:
    card_name = card_name.strip()
    payer_name = payer_name.strip()
    note = note.strip()

    if not card_name:
        return "信用卡不能为空。"
    if amount <= 0:
        return "还款金额必须大于 0。"

    try:
        supabase.table("credit_card_payments").insert(
            {
                "payment_date": str(payment_date_value),
                "card_name": card_name,
                "amount": float(amount),
                "payer_name": payer_name,
                "note": note,
            }
        ).execute()
        return "ok"
    except Exception as e:
        return f"保存信用卡还款失败：{e}"
        
    def get_effective_rate(row):
        key = (str(row["card_name"]), str(row["parent_category"]))
        if key in rule_map:
            return rule_map[key]
        return default_rate_map.get(str(row["card_name"]), 0.0)

    result["effective_cashback_rate"] = result.apply(get_effective_rate, axis=1)
    result["estimated_cashback"] = result["adjusted_amount"] * result["effective_cashback_rate"]

    return result
def ensure_cashback_rule_columns(df: pd.DataFrame) -> pd.DataFrame:
    expected_defaults = {
        "id": 0,
        "card_name": "",
        "category_name": "",
        "cashback_rate": 0.0,
        "created_at": "",
    }

    normalized = df.copy()
    for col, default in expected_defaults.items():
        if col not in normalized.columns:
            normalized[col] = default

    normalized["id"] = pd.to_numeric(normalized["id"], errors="coerce").fillna(0).astype(int)
    normalized["card_name"] = normalized["card_name"].fillna("").astype(str)
    normalized["category_name"] = normalized["category_name"].fillna("").astype(str)
    normalized["cashback_rate"] = pd.to_numeric(normalized["cashback_rate"], errors="coerce").fillna(0.0)

    return normalized


def save_cashback_rule(card_name: str, category_name: str, cashback_rate: float) -> str:
    card_name = card_name.strip()
    category_name = category_name.strip()

    if not card_name:
        return "信用卡不能为空。"
    if not category_name:
        return "分类不能为空。"
    if cashback_rate < 0:
        return "cashback 不能小于 0。"

    try:
        existing = (
            supabase.table("credit_card_cashback_rules")
            .select("id")
            .eq("card_name", card_name)
            .eq("category_name", category_name)
            .limit(1)
            .execute()
        )

        if existing.data:
            supabase.table("credit_card_cashback_rules").update(
                {"cashback_rate": float(cashback_rate)}
            ).eq("card_name", card_name).eq("category_name", category_name).execute()
            return "updated"
        else:
            supabase.table("credit_card_cashback_rules").insert(
                {
                    "card_name": card_name,
                    "category_name": category_name,
                    "cashback_rate": float(cashback_rate),
                }
            ).execute()
            return "ok"
    except Exception as e:
        return f"保存返现规则失败：{e}"

def add_user(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        return "用户名称不能为空。"

    try:
        existing = supabase.table("users").select("id").eq("name", cleaned).limit(1).execute()
        if existing.data:
            return "该用户已存在。"

        supabase.table("users").insert({"name": cleaned}).execute()
        return "ok"
    except Exception as e:
        return f"保存用户失败：{e}"


def add_sub_category(parent_category: str, sub_category: str) -> str:
    parent = parent_category.strip()
    sub = sub_category.strip()

    if parent not in FIXED_PARENT_CATEGORIES:
        return "一级分类不合法。"
    if not sub:
        return "二级分类名称不能为空。"

    try:
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
    except Exception as e:
        return f"保存二级分类失败：{e}"


def add_credit_card(card_name: str, owner_name: str, cashback_rate: float, payment_due_day: int) -> str:
    card_name = card_name.strip()
    owner_name = owner_name.strip()

    if not card_name:
        return "信用卡名称不能为空。"
    if not owner_name:
        return "持有人不能为空。"
    if cashback_rate < 0:
        return "cashback 不能小于 0。"
    if payment_due_day < 1 or payment_due_day > 31:
        return "还款日必须在 1 到 31 之间。"

    try:
        existing = (
            supabase.table("credit_cards")
            .select("id")
            .eq("card_name", card_name)
            .limit(1)
            .execute()
        )
        if existing.data:
            return "这张信用卡已存在。"

        supabase.table("credit_cards").insert(
            {
                "card_name": card_name,
                "owner_name": owner_name,
                "cashback_rate": float(cashback_rate),
                "payment_due_day": int(payment_due_day),
                "is_active": True,
            }
        ).execute()
        return "ok"
    except Exception as e:
        return f"保存信用卡失败：{e}"


def update_credit_card(
    old_card_name: str,
    new_card_name: str,
    owner_name: str,
    cashback_rate: float,
    payment_due_day: int,
    is_active: bool,
) -> str:
    old_card_name = old_card_name.strip()
    new_card_name = new_card_name.strip()
    owner_name = owner_name.strip()

    if not old_card_name:
        return "原信用卡名称不能为空。"
    if not new_card_name:
        return "新信用卡名称不能为空。"
    if not owner_name:
        return "属于谁不能为空。"
    if cashback_rate < 0:
        return "cashback 不能小于 0。"
    if payment_due_day < 1 or payment_due_day > 31:
        return "每月还款日必须在 1 到 31 之间。"

    try:
        # 如果改了卡名，先检查新卡名是否已存在
        if old_card_name != new_card_name:
            existing = (
                supabase.table("credit_cards")
                .select("id")
                .eq("card_name", new_card_name)
                .limit(1)
                .execute()
            )
            if existing.data:
                return "新的信用卡名称已存在。"

        # 更新信用卡主表
        supabase.table("credit_cards").update(
            {
                "card_name": new_card_name,
                "owner_name": owner_name,
                "cashback_rate": float(cashback_rate),
                "payment_due_day": int(payment_due_day),
                "is_active": bool(is_active),
            }
        ).eq("card_name", old_card_name).execute()

        # 如果改了卡名，同步更新 expenses 和 cashback 规则表
        if old_card_name != new_card_name:
            supabase.table("expenses").update(
                {"card_name": new_card_name}
            ).eq("card_name", old_card_name).execute()

            supabase.table("credit_card_cashback_rules").update(
                {"card_name": new_card_name}
            ).eq("card_name", old_card_name).execute()

        return "ok"

    except Exception as e:
        return f"修改信用卡失败：{e}"

def deactivate_credit_card(card_name: str) -> str:
    card_name = card_name.strip()
    if not card_name:
        return "信用卡名称不能为空。"

    try:
        supabase.table("credit_cards").update(
            {"is_active": False}
        ).eq("card_name", card_name).execute()
        return "ok"
    except Exception as e:
        return f"停用信用卡失败：{e}"

def ensure_expense_columns(df: pd.DataFrame) -> pd.DataFrame:
    expected_defaults = {
        "id": 0,
        "expense_date": pd.NaT,
        "amount": 0.0,
        "user_id": 0,
        "user_name": "",
        "bill_type": "个人",
        "parent_category": "其他",
        "sub_category": "未分类",
        "payment_method": "现金/借记卡",
        "card_name": "",
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

    normalized["payment_method"] = normalized["payment_method"].fillna("现金/借记卡").astype(str)
    normalized.loc[~normalized["payment_method"].isin(PAYMENT_METHODS), "payment_method"] = "现金/借记卡"

    normalized["sub_category"] = normalized["sub_category"].fillna("未分类").astype(str)
    normalized["card_name"] = normalized["card_name"].fillna("").astype(str)
    normalized["id"] = pd.to_numeric(normalized["id"], errors="coerce").fillna(0).astype(int)
    normalized["user_id"] = pd.to_numeric(normalized["user_id"], errors="coerce").fillna(0).astype(int)
    normalized["user_name"] = normalized["user_name"].fillna("").astype(str)
    normalized["note"] = normalized["note"].fillna("").astype(str)

    normalized["amount"] = pd.to_numeric(normalized["amount"], errors="coerce").fillna(0.0)
    normalized["expense_date"] = pd.to_datetime(normalized["expense_date"], errors="coerce")
    return normalized


def ensure_credit_card_columns(df: pd.DataFrame) -> pd.DataFrame:
    expected_defaults = {
        "card_name": "",
        "owner_name": "",
        "cashback_rate": 0.0,
        "payment_due_day": None,
        "is_active": True,
        "created_at": "",
    }

    normalized = df.copy()
    for col, default in expected_defaults.items():
        if col not in normalized.columns:
            normalized[col] = default

    normalized["card_name"] = normalized["card_name"].fillna("").astype(str)
    normalized["owner_name"] = normalized["owner_name"].fillna("").astype(str)
    normalized["cashback_rate"] = pd.to_numeric(normalized["cashback_rate"], errors="coerce").fillna(0.0)
    normalized["is_active"] = normalized["is_active"].fillna(True)
    return normalized


def delete_expense_record(expense_id: int) -> str:
    if expense_id <= 0:
        return "删除失败：无效的记录ID。"
    try:
        supabase.table("expenses").delete().eq("id", int(expense_id)).execute()
        return "ok"
    except Exception as e:
        return f"删除失败：{e}"


def get_sub_options_for_parent(df: pd.DataFrame, parent_category: str) -> list[str]:
    if df.empty:
        return []
    sub_df = df[df["parent_category"] == parent_category]
    return sorted(sub_df["sub_category"].dropna().unique().tolist())


def add_expense_record(
    expense_date: date,
    amount: float,
    user_id: int,
    user_name: str,
    bill_type: str,
    parent_category: str,
    sub_category: str,
    payment_method: str,
    card_name: str,
    note: str,
) -> str:
    if amount < 0:
        return "金额必须大于等于 0。"
    if user_id <= 0:
        return "用户ID无效，请重新选择用户。"
    if bill_type not in ["个人", "共同"]:
        return "账单类型不合法。"
    if parent_category not in FIXED_PARENT_CATEGORIES:
        return "一级分类不合法。"
    if not sub_category.strip():
        return "请先选择二级分类。"
    if payment_method not in PAYMENT_METHODS:
        return "支付方式不合法。"
    if payment_method == "信用卡" and not card_name.strip():
        return "信用卡支付必须选择卡片。"

    try:
        user_check = (
            supabase.table("users")
            .select("id")
            .eq("id", int(user_id))
            .limit(1)
            .execute()
        )
        if not user_check.data:
            return "保存失败：用户不存在（可能数据库里已删除该用户）。"

        category_check = (
            supabase.table("categories")
            .select("id")
            .eq("parent_category", parent_category)
            .eq("sub_category", sub_category.strip())
            .limit(1)
            .execute()
        )
        if not category_check.data:
            return "保存失败：该一级/二级分类组合不存在，请先添加二级分类。"

        supabase.table("expenses").insert(
            {
                "expense_date": str(expense_date),
                "amount": float(amount),
                "user_id": int(user_id),
                "user_name": user_name,
                "bill_type": bill_type,
                "parent_category": parent_category,
                "sub_category": sub_category.strip(),
                "payment_method": payment_method,
                "card_name": card_name.strip() if payment_method == "信用卡" else "",
                "note": note.strip(),
            }
        ).execute()
        return "ok"
    except Exception as e:
        error_text = str(e)
        if "row-level security policy" in error_text.lower():
            return "保存失败：Supabase RLS 拦截了写入。请在 Supabase 为 users/categories/expenses 添加 INSERT/SELECT 策略，或改用 service_role key。"
        return f"保存失败：{error_text}"

#加载数据
users_df = load_users()
categories_df = load_categories()
expenses_df = load_expenses()
cards_df = ensure_credit_card_columns(load_credit_cards())
cashback_rules_df = ensure_cashback_rule_columns(load_cashback_rules())
paychecks_df = ensure_paycheck_columns(load_paychecks())
credit_card_payments_df = ensure_credit_card_payment_columns(load_credit_card_payments())

st.markdown(
    """
<div class='top-banner'>
  <p class='top-title'>💸 情侣记账本</p>
  <p class='top-subtitle'>帮助情侣/小家庭快速记账，查看共同与个人支出。</p>
</div>
""",
    unsafe_allow_html=True,
)

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

    user_filter_options = ["全部"] + users_df["name"].dropna().unique().tolist() if not users_df.empty else ["全部"]
    selected_user_filter = st.selectbox("按用户", user_filter_options, index=0, key="user_filter")
    selected_bill_filter = st.selectbox("按账单类型", ["全部", "个人", "共同"], key="bill_filter")
    selected_parent_filter = st.selectbox("按一级分类", ["全部"] + FIXED_PARENT_CATEGORIES, key="filter_parent")

    if selected_parent_filter == "全部":
        sub_filter_options = ["全部"]
        if not categories_df.empty:
            sub_filter_options += sorted(categories_df["sub_category"].dropna().unique().tolist())
    else:
        sub_filter_options = ["全部"] + get_sub_options_for_parent(categories_df, selected_parent_filter)

    filter_sub_key = f"filter_sub_{selected_parent_filter}"
    if st.session_state.get(filter_sub_key) not in sub_filter_options:
        st.session_state[filter_sub_key] = "全部"

    selected_sub_filter = st.selectbox("按二级分类", sub_filter_options, key=filter_sub_key)

    min_day = date(2020, 1, 1)
    max_day = date.today()
    date_range = st.date_input(
        "按日期区间",
        value=(max_day.replace(day=1), max_day),
        min_value=min_day,
        max_value=max_day,
    )

    if st.button("🔄 刷新最新数据", use_container_width=True):
        st.rerun()

st.markdown("<div class='panel'>", unsafe_allow_html=True)
st.subheader("➕ 添加记录")

if users_df.empty:
    st.warning("请先在左侧添加用户。")
elif categories_df.empty:
    st.warning("请先在左侧添加至少一个二级分类。")
else:
    st.caption("金额必须 ≥ 0；二级分类会随一级分类实时联动。保存后自动写入 Supabase 并刷新。")

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_date = st.date_input("日期", value=date.today(), key="main_date")
    with col2:
        amount = st.number_input("金额", min_value=0.0, step=1.0, format="%.2f", key="main_amount")
    with col3:
        user_options = users_df[["id", "name"]].dropna().copy()
        user_options["id"] = pd.to_numeric(user_options["id"], errors="coerce").fillna(0).astype(int)
        user_options = user_options[user_options["id"] > 0]
        selected_user_name = st.selectbox("记账用户", user_options["name"].tolist(), key="main_user_name")
        selected_user_id = int(user_options[user_options["name"] == selected_user_name]["id"].iloc[0])

    col4, col5, col6 = st.columns(3)
    with col4:
        selected_bill_type = st.selectbox("账单类型", ["个人", "共同"], key="main_bill_type")
    with col5:
        selected_parent = st.selectbox("一级分类（固定）", FIXED_PARENT_CATEGORIES, key="main_parent")

    sub_options = get_sub_options_for_parent(categories_df, selected_parent)
    main_sub_key = f"main_sub_{selected_parent}"
    if st.session_state.get(main_sub_key) not in sub_options and sub_options:
        st.session_state[main_sub_key] = sub_options[0]

    with col6:
        if sub_options:
            selected_sub = st.selectbox("二级分类", sub_options, key=main_sub_key)
        else:
            selected_sub = ""
            st.warning("该一级分类下没有二级分类，请先在左侧添加。")

    col7, col8 = st.columns(2)
    with col7:
        selected_payment_method = st.selectbox("支付方式", PAYMENT_METHODS, key="main_payment_method")
    with col8:
        if selected_payment_method == "信用卡":
            active_cards_df = cards_df[cards_df["is_active"] == True] if not cards_df.empty else cards_df
            card_options = (
                active_cards_df["card_name"].dropna().unique().tolist()
                if not active_cards_df.empty and "card_name" in active_cards_df.columns
                else []
            )
            selected_card_name = st.selectbox("信用卡名称", card_options, key="main_card_name") if card_options else ""
            if not card_options:
                st.info("没有可选信用卡，请先到 Tab3 添加。")
        else:
            selected_card_name = ""
            st.text_input("信用卡名称", value="非信用卡支付", disabled=True, key="main_card_name_disabled")

    note = st.text_input("备注", placeholder="例如：午餐AA / Costco补货", key="main_note")
    submitted_expense = st.button("保存记录", use_container_width=True)

    if submitted_expense:
        result = add_expense_record(
            expense_date=selected_date,
            amount=amount,
            user_id=selected_user_id,
            user_name=selected_user_name,
            bill_type=selected_bill_type,
            parent_category=selected_parent,
            sub_category=selected_sub,
            payment_method=selected_payment_method,
            card_name=selected_card_name,
            note=note,
        )
        if result == "ok":
            st.success("已写入 Supabase，页面已刷新最新数据。")
            st.rerun()
        else:
            st.error(result)

st.markdown("</div>", unsafe_allow_html=True)

df = ensure_expense_columns(expenses_df)
filtered_df = df.copy()

if selected_user_filter != "全部":
    filtered_df = filtered_df[
        (filtered_df["user_name"] == selected_user_filter)
        | (filtered_df["bill_type"] == "共同")
    ]

if selected_bill_filter != "全部":
    filtered_df = filtered_df[filtered_df["bill_type"] == selected_bill_filter]
if selected_parent_filter != "全部":
    filtered_df = filtered_df[filtered_df["parent_category"] == selected_parent_filter]
if selected_sub_filter != "全部":
    filtered_df = filtered_df[filtered_df["sub_category"] == selected_sub_filter]

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_day, end_day = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    filtered_df = filtered_df[
        (filtered_df["expense_date"] >= start_day)
        & (filtered_df["expense_date"] <= end_day)
    ]

tab1, tab2, tab3 = st.tabs(["📒 记账总览", "💵 现金流统计", "💳 信用卡管理"])

with tab1:
    st.subheader("📊 统计卡片")

    if filtered_df.empty:
        shared_amount = 0.0
        personal_amount = 0.0
        total_amount = 0.0
        total_label = "总支出"
    else:
        shared_amount = filtered_df[filtered_df["bill_type"] == "共同"]["amount"].sum()

        if selected_user_filter == "全部":
            personal_amount = filtered_df[filtered_df["bill_type"] == "个人"]["amount"].sum()
            total_amount = personal_amount + shared_amount
            total_label = "总支出(全部个人+全部共同)"
        else:
            personal_amount = filtered_df[
                (filtered_df["user_name"] == selected_user_filter)
                & (filtered_df["bill_type"] == "个人")
            ]["amount"].sum()
            total_amount = personal_amount + (shared_amount / 2)
            total_label = "总支出(个人+共同/2)"

    record_count = len(filtered_df)

    s1, s2, s3, s4 = st.columns(4)
    s1.markdown(
        f"<div class='stat-card'><div class='stat-label'>{total_label}</div><div class='stat-value'>¥{total_amount:,.2f}</div></div>",
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

    st.subheader("📈 可视化统计（总支出分类饼图）")
    if filtered_df.empty:
        st.info("当前筛选条件下暂无可视化数据。")
    else:
        chart_df = filtered_df.copy()

        if selected_user_filter == "全部":
            chart_df["chart_amount"] = chart_df["amount"]
        else:
            chart_df["chart_amount"] = chart_df["amount"]
            chart_df.loc[chart_df["bill_type"] == "共同", "chart_amount"] = (
                chart_df.loc[chart_df["bill_type"] == "共同", "amount"] / 2
            )

        chart_summary = (
            chart_df.groupby("parent_category", as_index=False)["chart_amount"]
            .sum()
            .sort_values("chart_amount", ascending=False)
            .rename(columns={"parent_category": "一级分类", "chart_amount": "总支出"})
        )

        if chart_summary.empty:
            st.info("当前筛选条件下暂无可视化数据。")
        else:
            total_chart_amount = chart_summary["总支出"].sum()
            chart_summary["占比"] = chart_summary["总支出"] / total_chart_amount
            chart_summary["标签"] = (
                chart_summary["一级分类"] + " " + chart_summary["占比"].map(lambda x: f"{x:.0%}")
            )

            pie = (
                alt.Chart(chart_summary)
                .mark_arc(innerRadius=40)
                .encode(
                    theta=alt.Theta("总支出:Q", title="总支出"),
                    color=alt.Color("一级分类:N", title="一级分类"),
                    tooltip=[
                        alt.Tooltip("一级分类:N", title="一级分类"),
                        alt.Tooltip("总支出:Q", title="总支出", format=".2f"),
                        alt.Tooltip("占比:Q", title="占比", format=".1%"),
                    ],
                )
                .properties(height=380)
            )

            labels = (
                alt.Chart(chart_summary)
                .mark_text(radius=145, size=12)
                .encode(
                    theta=alt.Theta("总支出:Q"),
                    text=alt.Text("标签:N"),
                    color=alt.value("#334155"),
                )
            )

            st.altair_chart(pie + labels, use_container_width=True)

    st.subheader("🧾 记录表格区")
    if filtered_df.empty:
        st.info("当前筛选条件下暂无记录。")
    else:
        show_df = filtered_df[
            [
                "expense_date",
                "id",
                "user_name",
                "bill_type",
                "parent_category",
                "sub_category",
                "payment_method",
                "card_name",
                "amount",
                "note",
                "created_at",
            ]
        ].copy()

        show_df["expense_date"] = show_df["expense_date"].dt.strftime("%Y-%m-%d")
        show_df = show_df.rename(
            columns={
                "expense_date": "日期",
                "id": "ID",
                "user_name": "用户",
                "bill_type": "类型",
                "parent_category": "一级分类",
                "sub_category": "二级分类",
                "payment_method": "支付方式",
                "card_name": "信用卡",
                "amount": "金额",
                "note": "备注",
                "created_at": "创建时间",
            }
        )
        st.dataframe(show_df, use_container_width=True, hide_index=True)

        with st.expander("🗑️ 删除记录（可选）", expanded=False):
            delete_options_df = filtered_df.sort_values(["expense_date", "id"], ascending=[False, False]).copy()
            delete_options_df["expense_date_str"] = delete_options_df["expense_date"].dt.strftime("%Y-%m-%d")
            delete_options_df["delete_label"] = (
                "ID:"
                + delete_options_df["id"].astype(str)
                + " | "
                + delete_options_df["expense_date_str"].astype(str)
                + " | "
                + delete_options_df["user_name"].astype(str)
                + " | "
                + delete_options_df["parent_category"].astype(str)
                + "-"
                + delete_options_df["sub_category"].astype(str)
                + " | ¥"
                + delete_options_df["amount"].map(lambda x: f"{x:,.2f}")
            )

            selected_delete_label = st.selectbox(
                "选择要删除的记录",
                delete_options_df["delete_label"].tolist(),
                key="delete_pick",
            )
            selected_delete_id = int(
                delete_options_df.loc[delete_options_df["delete_label"] == selected_delete_label, "id"].iloc[0]
            )
            confirm_delete = st.checkbox(
                "我确认要删除这条记录（不可恢复）",
                value=False,
                key="confirm_delete",
            )
            if st.button("删除选中记录", use_container_width=True, key="delete_btn"):
                if not confirm_delete:
                    st.warning("请先勾选确认删除。")
                else:
                    delete_result = delete_expense_record(selected_delete_id)
                    if delete_result == "ok":
                        st.success("记录已删除。")
                        st.rerun()
                    else:
                        st.error(delete_result)

        with st.expander("✏️ 修改记录（可选）", expanded=False):
            edit_options_df = filtered_df.sort_values(["expense_date", "id"], ascending=[False, False]).copy()
            if edit_options_df.empty:
                st.info("当前没有可修改的记录。")
            else:
                edit_options_df["expense_date_str"] = edit_options_df["expense_date"].dt.strftime("%Y-%m-%d")
                edit_options_df["edit_label"] = (
                    "ID:"
                    + edit_options_df["id"].astype(str)
                    + " | "
                    + edit_options_df["expense_date_str"].astype(str)
                    + " | "
                    + edit_options_df["user_name"].astype(str)
                    + " | "
                    + edit_options_df["parent_category"].astype(str)
                    + "-"
                    + edit_options_df["sub_category"].astype(str)
                    + " | ¥"
                    + edit_options_df["amount"].map(lambda x: f"{x:,.2f}")
                )

                selected_edit_label = st.selectbox(
                    "选择要修改的记录",
                    edit_options_df["edit_label"].tolist(),
                    key="edit_pick",
                )
                edit_row = edit_options_df.loc[edit_options_df["edit_label"] == selected_edit_label].iloc[0]

                e1, e2, e3 = st.columns(3)
                with e1:
                    edit_date = st.date_input(
                        "新日期",
                        value=pd.to_datetime(edit_row["expense_date"]).date(),
                        key="edit_date",
                    )
                with e2:
                    edit_amount = st.number_input(
                        "新金额",
                        min_value=0.0,
                        value=float(edit_row["amount"]),
                        step=1.0,
                        format="%.2f",
                        key="edit_amount",
                    )
                with e3:
                    old_bill_type = str(edit_row["bill_type"]) if pd.notna(edit_row["bill_type"]) else "个人"
                    edit_bill_type = st.selectbox(
                        "新账单类型",
                        ["个人", "共同"],
                        index=0 if old_bill_type == "个人" else 1,
                        key="edit_bill_type",
                    )

                e4, e5, e6 = st.columns(3)
                with e4:
                    old_parent = str(edit_row["parent_category"]) if pd.notna(edit_row["parent_category"]) else "其他"
                    parent_idx = FIXED_PARENT_CATEGORIES.index(old_parent) if old_parent in FIXED_PARENT_CATEGORIES else 0
                    edit_parent = st.selectbox(
                        "新一级分类",
                        FIXED_PARENT_CATEGORIES,
                        index=parent_idx,
                        key="edit_parent",
                    )

                sub_opts = get_sub_options_for_parent(categories_df, edit_parent)
                with e5:
                    old_sub = str(edit_row["sub_category"]) if pd.notna(edit_row["sub_category"]) else ""
                    sub_idx = sub_opts.index(old_sub) if (old_sub in sub_opts) else 0
                    edit_sub = st.selectbox(
                        "新二级分类",
                        sub_opts if sub_opts else [""],
                        index=sub_idx,
                        key="edit_sub",
                    )

                with e6:
                    old_pay = (
                        str(edit_row["payment_method"])
                        if ("payment_method" in edit_row and pd.notna(edit_row["payment_method"]))
                        else "现金/借记卡"
                    )
                    pay_idx = PAYMENT_METHODS.index(old_pay) if old_pay in PAYMENT_METHODS else 0
                    edit_payment_method = st.selectbox(
                        "新支付方式",
                        PAYMENT_METHODS,
                        index=pay_idx,
                        key="edit_payment_method",
                    )

                e7, e8 = st.columns(2)
                with e7:
                    if edit_payment_method == "信用卡":
                        edit_card_options = (
                            cards_df["card_name"].dropna().unique().tolist()
                            if not cards_df.empty and "card_name" in cards_df.columns
                            else []
                        )
                        old_card = (
                            str(edit_row["card_name"])
                            if ("card_name" in edit_row and pd.notna(edit_row["card_name"]))
                            else ""
                        )
                        card_idx = edit_card_options.index(old_card) if (old_card in edit_card_options) else 0
                        edit_card_name = (
                            st.selectbox("新信用卡", edit_card_options, index=card_idx, key="edit_card_name")
                            if edit_card_options
                            else ""
                        )
                        if not edit_card_options:
                            st.info("没有可选信用卡，请先在 Tab3 添加。")
                    else:
                        edit_card_name = ""
                        st.text_input("新信用卡", value="非信用卡支付", disabled=True, key="edit_card_disabled")

                with e8:
                    old_note = str(edit_row["note"]) if pd.notna(edit_row["note"]) else ""
                    edit_note = st.text_input("新备注", value=old_note, key="edit_note")

                confirm_edit = st.checkbox("我确认要修改这条记录", value=False, key="confirm_edit")
                if st.button("保存修改", use_container_width=True, key="save_edit_btn"):
                    if not confirm_edit:
                        st.warning("请先勾选确认修改。")
                    elif edit_payment_method == "信用卡" and not edit_card_name:
                        st.warning("信用卡支付必须选择卡片。")
                    elif not edit_sub:
                        st.warning("请先选择二级分类。")
                    else:
                        update_payload = {
                            "expense_date": str(edit_date),
                            "amount": float(edit_amount),
                            "bill_type": edit_bill_type,
                            "parent_category": edit_parent,
                            "sub_category": edit_sub,
                            "payment_method": edit_payment_method,
                            "card_name": edit_card_name if edit_payment_method == "信用卡" else "",
                            "note": edit_note.strip(),
                        }
                        try:
                            supabase.table("expenses").update(update_payload).eq("id", int(edit_row["id"])).execute()
                            st.success("记录已修改。")
                            st.rerun()
                        except Exception as e:
                            st.error(f"修改失败：{e}")
with tab2:
    if isinstance(date_range, tuple) and len(date_range) == 2:
    range_start = pd.to_datetime(date_range[0]).date()
    range_end = pd.to_datetime(date_range[1]).date()
    else:
    today = date.today()
    range_start = today.replace(day=1)
    range_end = today
    st.markdown("### 💳 手动记录信用卡还款")
    
    active_card_names = cards_df[cards_df["is_active"] == True]["card_name"].dropna().unique().tolist() if not cards_df.empty else []
    payer_options = ["共同"] + users_df["name"].dropna().unique().tolist() if not users_df.empty else ["共同"]
    
    with st.form("add_credit_card_payment_form", clear_on_submit=True):
        rp1, rp2, rp3 = st.columns(3)
        with rp1:
            payment_date_value = st.date_input("还款日期", value=date.today(), key="repayment_date")
        with rp2:
            repayment_card_name = st.selectbox("信用卡", active_card_names, key="repayment_card")
        with rp3:
            repayment_amount = st.number_input("还款金额", min_value=0.0, step=10.0, format="%.2f", key="repayment_amount")
    
        rp4, rp5 = st.columns(2)
        with rp4:
            repayment_payer = st.selectbox("还款人", payer_options, key="repayment_payer")
        with rp5:
            repayment_note = st.text_input("备注", key="repayment_note")
    
        submitted_repayment = st.form_submit_button("保存还款记录", use_container_width=True)
    
    if submitted_repayment:
        result = add_credit_card_payment(
            payment_date_value,
            repayment_card_name,
            float(repayment_amount),
            repayment_payer,
            repayment_note,
        )
        if result == "ok":
            st.success("信用卡还款记录已保存。")
            st.rerun()
        else:
            st.error(result)
            
        st.subheader("💵 现金流统计")
        st.caption("逻辑：现金/借记卡当天流出；信用卡按还款日自动计入现金流；paycheck 按规则自动生成。")
    
        # 日期区间
        if isinstance(date_range, tuple) and len(date_range) == 2:
            range_start = pd.to_datetime(date_range[0]).date()
            range_end = pd.to_datetime(date_range[1]).date()
        else:
            today = date.today()
            range_start = today.replace(day=1)
            range_end = today

    # ===== 现金流入规则管理 =====
    st.markdown("### 💰 现金流入规则（Paycheck）")

    paycheck_owner_options = ["共同"] + users_df["name"].dropna().unique().tolist() if not users_df.empty else ["共同"]

    with st.form("add_paycheck_form", clear_on_submit=True):
        p1, p2, p3 = st.columns(3)
        with p1:
            paycheck_user = st.selectbox("属于谁", paycheck_owner_options)
        with p2:
            income_name = st.text_input("收入名称", value="工资")
        with p3:
            paycheck_amount = st.number_input("每次金额", min_value=0.0, step=100.0, format="%.2f")

        p4, p5, p6 = st.columns(3)
        with p4:
            paycheck_frequency = st.selectbox(
                "频率",
                ["biweekly", "twice_a_month", "monthly"],
                format_func=lambda x: {
                    "biweekly": "每两周",
                    "twice_a_month": "每月两次",
                    "monthly": "每月一次",
                }[x],
            )
        with p5:
            paycheck_start_date = st.date_input("起始发薪日", value=date.today(), key="paycheck_start_date")
        with p6:
            paycheck_second_day = st.number_input(
                "第二个发薪日（仅每月两次）",
                min_value=1,
                max_value=31,
                value=30,
                step=1,
            )

        submitted_paycheck = st.form_submit_button("保存 paycheck 规则", use_container_width=True)

    if submitted_paycheck:
        result = add_paycheck_rule(
            paycheck_user,
            income_name,
            float(paycheck_amount),
            paycheck_frequency,
            paycheck_start_date,
            int(paycheck_second_day) if paycheck_frequency == "twice_a_month" else None,
        )
        if result == "ok":
            st.success("paycheck 规则已保存。")
            st.rerun()
        else:
            st.error(result)

    if paychecks_df.empty:
        st.info("还没有 paycheck 规则。")
    else:
        st.dataframe(
            paychecks_df.rename(
                columns={
                    "user_name": "属于谁",
                    "income_name": "收入名称",
                    "amount": "每次金额",
                    "frequency": "频率",
                    "start_date": "起始发薪日",
                    "second_day": "第二个发薪日",
                    "is_active": "启用中",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("---")

    # ===== 为现金流单独准备数据源：不要先按 expense_date 切掉 =====
    cash_source_df = df.copy()

    if selected_user_filter != "全部":
        cash_source_df = cash_source_df[
            (cash_source_df["user_name"] == selected_user_filter)
            | (cash_source_df["bill_type"] == "共同")
        ]

    if selected_bill_filter != "全部":
        cash_source_df = cash_source_df[cash_source_df["bill_type"] == selected_bill_filter]

    if selected_parent_filter != "全部":
        cash_source_df = cash_source_df[cash_source_df["parent_category"] == selected_parent_filter]

    if selected_sub_filter != "全部":
        cash_source_df = cash_source_df[cash_source_df["sub_category"] == selected_sub_filter]

    if cash_source_df.empty and paychecks_df.empty:
        st.info("当前筛选条件下暂无数据。")
    else:
        # 单个用户：个人全额 + 共同/2
        if cash_source_df.empty:
            cash_source_df = pd.DataFrame(columns=df.columns.tolist() + ["adjusted_amount"])
        else:
            if selected_user_filter == "全部":
                cash_source_df["adjusted_amount"] = cash_source_df["amount"]
            else:
                cash_source_df["adjusted_amount"] = cash_source_df["amount"]
                cash_source_df.loc[cash_source_df["bill_type"] == "共同", "adjusted_amount"] = (
                    cash_source_df.loc[cash_source_df["bill_type"] == "共同", "amount"] / 2
                )

# ===== 直接支付：消费日就是现金流日 =====
direct_outflow_all = cash_source_df[cash_source_df["payment_method"] != "信用卡"].copy()

if direct_outflow_all.empty:
    direct_outflow_in_range = pd.DataFrame()
else:
    direct_outflow_all["event_date"] = pd.to_datetime(direct_outflow_all["expense_date"]).dt.date
    direct_outflow_in_range = direct_outflow_all[
        (direct_outflow_all["event_date"] >= range_start)
        & (direct_outflow_all["event_date"] <= range_end)
    ].copy()

        # ===== 信用卡：按还款日自动算入现金流 =====
        credit_due_all = generate_credit_due_schedule(cash_source_df, cards_df)

        credit_due_in_range = credit_due_all[
            (credit_due_all["due_date"] >= range_start)
            & (credit_due_all["due_date"] <= range_end)
        ].copy() if not credit_due_all.empty else pd.DataFrame()

        # 当前待还：到区间结束日之后才到期的
        pending_credit_df = credit_due_all[
            credit_due_all["due_date"] > range_end
        ].copy() if not credit_due_all.empty else pd.DataFrame()

        # ===== paycheck 事件 =====
        active_paychecks_df = paychecks_df[paychecks_df["is_active"] == True].copy() if not paychecks_df.empty else pd.DataFrame()

        if not active_paychecks_df.empty and selected_user_filter != "全部":
            active_paychecks_df = active_paychecks_df[
                active_paychecks_df["user_name"].isin([selected_user_filter, "共同"])
            ].copy()

        paycheck_events_df = generate_paycheck_events(active_paychecks_df, range_start, range_end)

        # ===== 顶部卡片 =====
        inflow_amount = paycheck_events_df["amount"].sum() if not paycheck_events_df.empty else 0.0
        direct_outflow_amount = direct_outflow_in_range["adjusted_amount"].sum() if not direct_outflow_in_range.empty else 0.0
        card_outflow_amount = credit_due_in_range["adjusted_amount"].sum() if not credit_due_in_range.empty else 0.0
        actual_outflow_amount = direct_outflow_amount + card_outflow_amount
        pending_card_amount = pending_credit_df["adjusted_amount"].sum() if not pending_credit_df.empty else 0.0
        net_cashflow_amount = inflow_amount - actual_outflow_amount

        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(
            f"<div class='stat-card'><div class='stat-label'>预计流入</div><div class='stat-value'>¥{inflow_amount:,.2f}</div></div>",
            unsafe_allow_html=True,
        )
        c2.markdown(
            f"<div class='stat-card'><div class='stat-label'>已实际流出</div><div class='stat-value'>¥{actual_outflow_amount:,.2f}</div></div>",
            unsafe_allow_html=True,
        )
        c3.markdown(
            f"<div class='stat-card'><div class='stat-label'>当前信用卡待还</div><div class='stat-value'>¥{pending_card_amount:,.2f}</div></div>",
            unsafe_allow_html=True,
        )
        c4.markdown(
            f"<div class='stat-card'><div class='stat-label'>预计净现金流</div><div class='stat-value'>¥{net_cashflow_amount:,.2f}</div></div>",
            unsafe_allow_html=True,
        )

        # ===== 现金流日历 / 日程表 =====
        st.markdown("### 🗓️ 现金流日程表")

        schedule_frames = []

        if not paycheck_events_df.empty:
            inflow_schedule = paycheck_events_df.copy()
            inflow_schedule["日期"] = inflow_schedule["event_date"].astype(str)
            inflow_schedule["类型"] = "现金流入"
            inflow_schedule["说明"] = inflow_schedule["user_name"] + " - " + inflow_schedule["income_name"]
            inflow_schedule["金额"] = inflow_schedule["amount"]
            inflow_schedule["状态"] = "预计"
            schedule_frames.append(inflow_schedule[["日期", "类型", "说明", "金额", "状态"]])

        if not direct_outflow_in_range.empty:
            direct_schedule = direct_outflow_in_range.copy()
            direct_schedule["日期"] = direct_schedule["event_date"].astype(str)
            direct_schedule["类型"] = "已实际流出"
            direct_schedule["说明"] = (
                direct_schedule["user_name"].astype(str)
                + " - "
                + direct_schedule["parent_category"].astype(str)
                + "-"
                + direct_schedule["sub_category"].astype(str)
            )
            direct_schedule["金额"] = direct_schedule["adjusted_amount"]
            direct_schedule["状态"] = "已发生"
            schedule_frames.append(direct_schedule[["日期", "类型", "说明", "金额", "状态"]])

        if not credit_due_in_range.empty:
            card_schedule = credit_due_in_range.copy()
            card_schedule["日期"] = card_schedule["due_date"].astype(str)
            card_schedule["类型"] = "信用卡自动还款"
            card_schedule["说明"] = (
                card_schedule["card_name"].astype(str)
                + " - "
                + card_schedule["parent_category"].astype(str)
                + "-"
                + card_schedule["sub_category"].astype(str)
            )
            card_schedule["金额"] = card_schedule["adjusted_amount"]
            card_schedule["状态"] = "按还款日自动计入"
            schedule_frames.append(card_schedule[["日期", "类型", "说明", "金额", "状态"]])

        if schedule_frames:
            schedule_df = pd.concat(schedule_frames, ignore_index=True)
            schedule_df["日期_dt"] = pd.to_datetime(schedule_df["日期"], errors="coerce")
            schedule_df = schedule_df.sort_values(["日期_dt", "类型"]).drop(columns=["日期_dt"])
            st.dataframe(schedule_df, use_container_width=True, hide_index=True)
        else:
            st.info("当前日期区间内暂无现金流日程。")

        # ===== 已实际流出（月度汇总） =====
        st.markdown("### 已实际流出（月度汇总）")

        actual_frames = []

        if not direct_outflow_in_range.empty:
            tmp1 = direct_outflow_in_range.copy()
            tmp1["event_date"] = pd.to_datetime(tmp1["event_date"])
            tmp1["金额"] = tmp1["adjusted_amount"]
            actual_frames.append(tmp1[["event_date", "金额"]])

        if not credit_due_in_range.empty:
            tmp2 = credit_due_in_range.copy()
            tmp2["event_date"] = pd.to_datetime(tmp2["due_date"])
            tmp2["金额"] = tmp2["adjusted_amount"]
            actual_frames.append(tmp2[["event_date", "金额"]])

        if actual_frames:
            actual_events_df = pd.concat(actual_frames, ignore_index=True)
            actual_events_df["月份"] = actual_events_df["event_date"].dt.to_period("M").astype(str)

            actual_monthly_summary = (
                actual_events_df.groupby("月份", as_index=False)["金额"]
                .sum()
                .sort_values("月份", ascending=False)
                .rename(columns={"金额": "已实际流出金额"})
            )
            st.dataframe(actual_monthly_summary, use_container_width=True, hide_index=True)
        else:
            st.info("当前没有已实际流出记录。")

            # ===== 信用卡待还（当前欠款汇总） =====
            st.markdown("### 信用卡待还（当前欠款汇总）")
            
            # 1. 信用卡消费记录
            credit_outstanding_df = cash_source_df[
                (cash_source_df["payment_method"] == "信用卡")
                & (cash_source_df["card_name"].fillna("") != "")
            ].copy()
            
            if credit_outstanding_df.empty:
                st.info("当前没有信用卡消费记录。")
            else:
                # 单用户视角时，共同支出算一半
                if selected_user_filter == "全部":
                    credit_outstanding_df["adjusted_amount"] = credit_outstanding_df["amount"]
                else:
                    credit_outstanding_df["adjusted_amount"] = credit_outstanding_df["amount"]
                    credit_outstanding_df.loc[credit_outstanding_df["bill_type"] == "共同", "adjusted_amount"] = (
                        credit_outstanding_df.loc[credit_outstanding_df["bill_type"] == "共同", "amount"] / 2
                    )
            
                # 2. 逐笔应用 cashback 规则
                credit_outstanding_df = apply_cashback_rules(
                    credit_outstanding_df,
                    cards_df,
                    cashback_rules_df,
                )
            
                # 3. 消费汇总（每张卡）
                charge_summary = (
                    credit_outstanding_df.groupby("card_name", as_index=False)
                    .agg(
                        总消费金额=("adjusted_amount", "sum"),
                        总预计cashback=("estimated_cashback", "sum"),
                        属于谁=("user_name", "first"),
                    )
                    .rename(columns={"card_name": "信用卡"})
                )
            
                # 4. 还款汇总（每张卡）
                payments_df = credit_card_payments_df.copy()
                if not payments_df.empty:
                    if isinstance(date_range, tuple) and len(date_range) == 2:
                        end_day = pd.to_datetime(date_range[1])
                        payments_df = payments_df[payments_df["payment_date"] <= end_day]
            
                    payment_summary = (
                        payments_df.groupby("card_name", as_index=False)["amount"]
                        .sum()
                        .rename(columns={"card_name": "信用卡", "amount": "已还金额"})
                    )
                else:
                    payment_summary = pd.DataFrame(columns=["信用卡", "已还金额"])
            
                # 5. 合并信用卡主表信息
                card_meta_df = cards_df.rename(
                    columns={
                        "card_name": "信用卡",
                        "owner_name": "属于谁",
                        "payment_due_day": "每月还款日",
                    }
                )[["信用卡", "属于谁", "每月还款日"]].copy() if not cards_df.empty else pd.DataFrame(columns=["信用卡", "属于谁", "每月还款日"])
            
                final_summary = charge_summary.merge(card_meta_df, on="信用卡", how="left")
                final_summary = final_summary.merge(payment_summary, on="信用卡", how="left")
                final_summary["已还金额"] = final_summary["已还金额"].fillna(0.0)
            
                # 6. 当前待还金额 = 总消费 - 已还
                final_summary["当前待还金额"] = final_summary["总消费金额"] - final_summary["已还金额"]
                final_summary["当前待还金额"] = final_summary["当前待还金额"].clip(lower=0)
            
                # 7. 当前待还对应 cashback
                # 用比例缩减：如果部分还了，待还对应的 cashback 也按剩余比例减少
                final_summary["待还cashback"] = final_summary.apply(
                    lambda row: (
                        row["总预计cashback"] * (row["当前待还金额"] / row["总消费金额"])
                        if row["总消费金额"] > 0 else 0.0
                    ),
                    axis=1
                )
            
                # 8. 下一次还款日期（简单版）
                today_value = date.today()
            
                def get_next_due_date(due_day):
                    if pd.isna(due_day):
                        return None
                    due_day = int(due_day)
                    this_month_due = safe_day_in_month(today_value.year, today_value.month, due_day)
                    if this_month_due >= today_value:
                        return this_month_due
                    if today_value.month == 12:
                        return safe_day_in_month(today_value.year + 1, 1, due_day)
                    return safe_day_in_month(today_value.year, today_value.month + 1, due_day)
            
                final_summary["下一次还款日期"] = final_summary["每月还款日"].apply(get_next_due_date)
            
                # 9. 只显示还有待还的卡
                final_summary = final_summary[final_summary["当前待还金额"] > 0].copy()
            
                if final_summary.empty:
                    st.info("当前没有待还信用卡。")
                else:
                    final_summary = final_summary[
                        ["信用卡", "当前待还金额", "属于谁", "每月还款日", "下一次还款日期", "待还cashback", "已还金额"]
                    ].sort_values("当前待还金额", ascending=False)
            
                    st.dataframe(final_summary, use_container_width=True, hide_index=True)
        
with tab3:
    st.subheader("💳 信用卡管理")

    latest_cards_df = ensure_credit_card_columns(load_credit_cards())
    latest_rules_df = ensure_cashback_rule_columns(load_cashback_rules())

    owner_options = ["共同"] + users_df["name"].dropna().unique().tolist() if not users_df.empty else ["共同"]

    st.markdown("### 添加信用卡")
    with st.form("add_credit_card_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            new_card_name = st.text_input("信用卡名称", placeholder="例如：Rogers")
            new_owner_name = st.selectbox("属于谁", owner_options)
        with c2:
            new_cashback_rate = st.number_input(
                "默认 cashback 比例（未单独设置分类时使用）",
                min_value=0.0,
                step=0.005,
                format="%.3f"
            )
            new_payment_due_day = st.number_input("每月还款日", min_value=1, max_value=31, step=1)

        submitted_card = st.form_submit_button("保存信用卡", use_container_width=True)

    if submitted_card:
        result = add_credit_card(
            new_card_name,
            new_owner_name,
            new_cashback_rate,
            int(new_payment_due_day),
        )
        if result == "ok":
            st.success("信用卡已添加。")
            st.rerun()
        else:
            st.warning(result)

    st.markdown("### 添加 / 更新 cashback 规则（按一级分类）")

    active_cards_df = latest_cards_df[latest_cards_df["is_active"] == True].copy() if not latest_cards_df.empty else pd.DataFrame()
    active_card_names = active_cards_df["card_name"].dropna().unique().tolist() if not active_cards_df.empty else []

    if not active_card_names:
        st.info("请先添加并启用至少一张信用卡。")
    else:
        with st.form("add_cashback_rule_form", clear_on_submit=True):
            r1, r2, r3 = st.columns(3)
            with r1:
                rule_card_name = st.selectbox("信用卡", active_card_names)
            with r2:
                rule_category_name = st.selectbox("一级分类", FIXED_PARENT_CATEGORIES)
            with r3:
                rule_cashback_rate = st.number_input(
                    "该分类 cashback 比例",
                    min_value=0.0,
                    step=0.005,
                    format="%.3f"
                )

            submitted_rule = st.form_submit_button("保存 cashback 规则", use_container_width=True)

        if submitted_rule:
            result = save_cashback_rule(
                rule_card_name,
                rule_category_name,
                float(rule_cashback_rate),
            )
            if result == "ok":
                st.success("cashback 规则已添加。")
                st.rerun()
            elif result == "updated":
                st.success("cashback 规则已更新。")
                st.rerun()
            else:
                st.error(result)

    st.markdown("### 已保存的信用卡")
    if latest_cards_df.empty:
        st.info("还没有信用卡。")
    else:
        show_cards_df = latest_cards_df.rename(
            columns={
                "card_name": "卡名",
                "owner_name": "属于谁",
                "cashback_rate": "默认cashback比例",
                "payment_due_day": "每月还款日",
                "is_active": "启用中",
                "created_at": "创建时间",
            }
        )
        st.dataframe(show_cards_df, use_container_width=True, hide_index=True)

    st.markdown("### 已保存的 cashback 规则")
    if latest_rules_df.empty:
        st.info("还没有分类返现规则。")
    else:
        show_rules_df = latest_rules_df.rename(
            columns={
                "card_name": "卡名",
                "category_name": "一级分类",
                "cashback_rate": "cashback比例",
                "created_at": "创建时间",
            }
        )
        st.dataframe(show_rules_df, use_container_width=True, hide_index=True)
