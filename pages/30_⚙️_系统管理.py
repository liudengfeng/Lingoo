import json
import logging
import os
import datetime
from pathlib import Path

import pandas as pd
import pytz
import streamlit as st
from azure.storage.blob import BlobServiceClient
from pandas import Timedelta

from mypylib.google_db_model import (
    Payment,
    PaymentStatus,
    PurchaseType,
    User,
    UserRole,
    str_to_enum,
)
from mypylib.google_firestore_interface import PRICES, GoogleDbInterface
from mypylib.st_utils import google_translate
from mypylib.word_utils import get_lowest_cefr_level

# region 配置

# 创建或获取logger对象
logger = logging.getLogger("streamlit")

CURRENT_CWD: Path = Path(__file__).parent.parent

if "user_info" not in st.session_state:
    st.session_state["user_info"] = {}

logger.debug(st.session_state.user_info)
# st.write(st.session_state.user_info)
if st.session_state.user_info.get("user_role") != "管理员":
    st.error("对不起，您没有权限访问该页面。该页面仅限系统管理员使用。")
    st.stop()

tz = pytz.timezone(st.session_state.user_info.get("timezone", "Asia/Shanghai"))
# endregion

# region 常量配置

PM_OPTS = list(PaymentStatus)

COLUMN_CONFIG = {
    "phone_number": "手机号码",
    "payment_id": "付款编号",
    "order_id": "订单编号",
    "payment_time": st.column_config.DatetimeColumn(
        "支付时间",
        min_value=datetime.datetime(2024, 1, 1),
        max_value=datetime.datetime(2134, 1, 1),
        step=60,
    ),
    "registration_time": st.column_config.DatetimeColumn(
        "登记时间",
        min_value=datetime.datetime(2024, 1, 1),
        max_value=datetime.datetime(2134, 1, 1),
        step=60,
    ),
    "sales_representative": "销售代表",
    "purchase_type": st.column_config.SelectboxColumn(
        "套餐类型",
        help="✨ 购买的套餐类型",
        width="small",
        options=list(PurchaseType),
        default=list(PurchaseType)[-1],
        required=True,
    ),
    "receivable": st.column_config.NumberColumn(
        "应收 (元)",
        help="✨ 购买套餐应支付的金额",
        min_value=0.00,
        max_value=10000.00,
        step=0.01,
        format="￥%.2f",
    ),
    "discount_rate": st.column_config.NumberColumn(
        "折扣率",
        help="✨ 享受的折扣率",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
        format="%.2f",
    ),
    "payment_method": "付款方式",
    # "real_name": "姓名",
    # "display_name": "显示名称",
    "payment_amount": st.column_config.NumberColumn(
        "实收 (元)",
        help="✨ 购买套餐实际支付的金额",
        min_value=0.01,
        max_value=10000.00,
        step=0.01,
        format="￥%.2f",
    ),
    "is_approved": st.column_config.CheckboxColumn(
        "是否批准",
        help="✨ 选中表示允许用户使用系统",
        default=False,
    ),
    "expiry_time": st.column_config.DatetimeColumn(
        "服务截至时间",
        min_value=datetime.datetime(2024, 1, 1),
        max_value=datetime.datetime(2134, 1, 1),
        step=60,
    ),
    # "user_role": st.column_config.SelectboxColumn(
    #     "权限",
    #     help="✨ 用户权限",
    #     width="small",
    #     options=list(UserRole),
    #     default=list(UserRole)[0],
    #     required=True,
    # ),
    # "registration_time": "注册时间",
    "status": st.column_config.SelectboxColumn(
        "服务状态",
        help="✨ 服务状态",
        width="small",
        options=PM_OPTS,
        default=PM_OPTS[-1],
        required=True,
    ),
    "remark": "服务备注",
    # "memo": "用户备注",
}

COLUMN_ORDER = [
    "phone_number",
    "payment_id",
    "order_id",
    "payment_time",
    "registration_time",
    "sales_representative",
    "purchase_type",
    "receivable",
    "discount_rate",
    "payment_method",
    "payment_amount",
    "is_approved",
    "expiry_time",
    "status",
    "remark",
]

TIME_COLS = ["payment_time", "expiry_time", "registration_time"]

EDITABLE_COLS: list[str] = [
    "is_approved",
    "payment_time",
    "expiry_time",
]

PAYMENTS_FIELDS = [
    "payment_id",
    "order_id",
    "payment_time",
    "payment_amount",
    "purchase_type",
    "payment_method",
    "is_approved",
    "status",
    "remark ",
]


# endregion


# region 函数


def generate_timestamp(key: str, type: str, idx: int):
    # 获取日期和时间
    if type:
        date = st.session_state.get(f"{key}_{type}_date-{idx}")
        time = st.session_state.get(f"{key}_{type}_time-{idx}")
    else:
        date = st.session_state.get(f"{key}_date-{idx}")
        time = st.session_state.get(f"{key}_time-{idx}")

    # 将日期和时间组合成一个 datetime 对象
    datetime_obj = datetime.datetime.combine(date, time)

    # 设置时区
    datetime_obj = tz.localize(datetime_obj)

    # 转换为 UTC 时区
    datetime_utc = datetime_obj.astimezone(pytz.UTC)

    # 返回字典
    if type:
        return {f"{type}_" + key: datetime_utc}
    else:
        return {key: datetime_utc}


# endregion

# region 会话状态

if st.session_state.get("search"):
    st.session_state["queried_payments"] = []


if "gdbi" not in st.session_state:
    st.session_state["gdbi"] = GoogleDbInterface()

# endregion

# 创建选项卡
items = ["订阅登记", "支付管理", "处理反馈", "词典管理", "统计分析"]
tabs = st.tabs(items)


# region 创建收费登记页面


with tabs[items.index("订阅登记")]:
    st.subheader("订阅登记")
    with st.form(key="payment_form", clear_on_submit=True):
        cols = st.columns(2)
        phone_number = cols[0].text_input(
            "手机号码",
            key="phone_number",
            help="✨ 请输入订阅者可接收短信的手机号码",
            placeholder="请输入订阅者可接收短信的手机号码[必须]",
        )
        sales_representative = cols[1].text_input(
            "销售代表",
            key="sales_representative",
            help="✨ 请提供销售代表的名称（选填）",
            placeholder="请提供销售代表的名称（选填）",
        )
        purchase_type = cols[0].selectbox(
            "套餐类型",
            key="purchase_type",
            help="✨ 请选择套餐类型",
            options=list(PurchaseType),
            index=1,
            format_func=lambda x: x.value,
            # on_change=compute_discount,
        )
        payment_amount = cols[1].number_input(
            "实收金额",
            key="payment_amount",
            help="✨ 请输入实际收款金额",
            value=0.0,
            # on_change=compute_discount,
        )
        payment_method = cols[0].text_input(
            "付款方式", key="payment_method", help="✨ 请输入付款方式", placeholder="必填。付款方式"
        )
        payment_id = cols[1].text_input(
            "付款编号", key="payment_id", help="✨ 请输入付款编号", placeholder="必填。请在付款凭证上查找付款编号"
        )
        cols[0].date_input(
            "支付日期",
            key="payment_time_date-0",
            value=datetime.datetime.now(tz).date(),
        )
        cols[1].time_input(
            "时间", key="payment_time_time-0", value=datetime.time(0, 0, 0)
        )
        remark = st.text_input(
            "备注",
            key="remark",
            help="✨ 请输入备注信息",
        )
        is_approved = st.toggle("是否批准")
        # user = st.session_state.gdbi.get_user(phone_number=phone_number)
        if st.form_submit_button(label="登记"):
            if not phone_number:
                st.error("手机号码不能为空")
                st.stop()
            if not payment_id:
                st.error("付款编号不能为空")
                st.stop()
            order_id = str(
                len(st.session_state.gdbi.db.collection("payments").get()) + 1
            ).zfill(10)
            receivable = PRICES[purchase_type]  # type: ignore
            discount_rate = payment_amount / receivable
            key = "payment_time"
            payment_time = generate_timestamp(key, "", 0)[key]
            payment = Payment(
                phone_number=phone_number,
                payment_id=payment_id,
                registration_time=datetime.datetime.now(datetime.timezone.utc),
                payment_time=payment_time,
                expiry_time=datetime.datetime.now(datetime.timezone.utc),
                receivable=receivable,
                payment_amount=payment_amount,  # type: ignore
                purchase_type=str_to_enum(purchase_type, PurchaseType),  # type: ignore
                order_id=order_id,
                payment_method=payment_method,
                discount_rate=discount_rate,
                sales_representative=sales_representative,
                is_approved=is_approved,
                remark=remark,
            )
            # try:
            st.session_state.gdbi.add_payment(payment)
            st.toast(f"成功登记，订单号:{order_id}", icon="🎉")
            # except DuplicateKeyError:
            #     st.error("付款编号已存在，请勿重复登记")
            #     st.stop()
            # except Exception as e:
            #     raise  # 重新抛出异常

# endregion

# region 创建用户管理页面

with tabs[items.index("支付管理")]:
    st.markdown("#### 查询参数")
    with st.form(key="query_form", clear_on_submit=True):
        # 精确匹配
        t_0_cols = st.columns(4)
        t_0_cols[0].markdown(":rainbow[精确匹配查询]")
        t0 = t_0_cols[1].toggle(
            label="包含",
            key="is_include-0",
            help="✨ 选中表示包含该查询条件，否则表示不包含",
        )
        payment_0_cols = st.columns(4)
        payment_0_cols[0].text_input(label="手机号码", key="phone_number-1")
        payment_0_cols[1].text_input(label="付款编号", key="payment_id-1")
        payment_0_cols[2].text_input(label="订单编号", key="order_id-1")
        payment_0_cols[3].text_input(label="销售代表", key="sales_representative-1")
        # 选项查询
        t_1_cols = st.columns(4)
        t_1_cols[0].markdown(":rainbow[状态查询]")
        t1 = t_1_cols[1].toggle(
            label="包含",
            key="is_include-1",
            help="✨ 选中表示包含该查询条件，否则表示不包含",
        )
        payment_1_cols = st.columns(4)
        payment_1_cols[0].selectbox(
            label="套餐类型",
            key="purchase_type-1",
            options=["All"] + [x.value for x in PurchaseType],
        )
        payment_1_cols[1].selectbox(
            label="支付状态",
            key="status-1",
            options=["All"] + [x.value for x in PaymentStatus],
        )
        payment_1_cols[2].selectbox(
            label="是否批准",
            key="is_approved-1",
            options=["All", False, True],
        )

        # 支付时间
        t_2_cols = st.columns(4)
        t_2_cols[0].markdown(":rainbow[支付期间查询]")
        t2 = t_2_cols[1].toggle(
            label="包含",
            key="is_include-2",
            help="✨ 选中表示包含该查询条件，否则表示不包含",
        )
        payment_2_cols = st.columns(4)
        payment_2_cols[0].date_input(
            "支付【开始日期】",
            key="payment_time_start_date-1",
            value=datetime.datetime.now(tz).date(),
        )
        payment_2_cols[1].time_input(
            "支付【开始时间】", key="payment_time_start_time-1", value=datetime.time(0, 0, 0)
        )
        payment_2_cols[2].date_input(
            "支付【结束日期】",
            key="payment_time_end_date-1",
            value=datetime.datetime.now(tz).date(),
        )
        payment_2_cols[3].time_input(
            "支付【结束时间】", key="payment_time_end_time-1", value=datetime.time(23, 59, 59)
        )

        # 服务时间查询
        t_3_cols = st.columns(4)
        t_3_cols[0].markdown(":rainbow[服务期间查询]")
        t3 = t_3_cols[1].toggle(
            label="包含",
            key="is_include-3",
            help="✨ 选中表示包含该查询条件，否则表示不包含",
        )
        payment_3_cols = st.columns(4)
        payment_3_cols[0].date_input(
            "服务【开始日期】",
            key="expiry_time_start_date-1",
            value=datetime.datetime.now(tz).date(),
        )
        payment_3_cols[1].time_input(
            "服务【开始时间】", key="expiry_time_start_time-1", value=datetime.time(0, 0, 0)
        )
        payment_3_cols[2].date_input(
            "服务【结束日期】",
            key="expiry_time_end_date-1",
            value=datetime.datetime.now(tz).date(),
        )
        payment_3_cols[3].time_input(
            "服务【结束时间】", key="expiry_time_end_time-1", value=datetime.time(23, 59, 59)
        )

        # 模糊查询
        t_4_cols = st.columns(4)
        t_4_cols[0].markdown(":rainbow[模糊查询]")
        t4 = t_4_cols[1].toggle(
            label="包含",
            key="is_include-4",
            help="✨ 选中表示包含该查询条件，否则表示不包含",
        )
        payment_4_cols = st.columns(2)
        payment_4_cols[0].text_input(
            "支付方式",
            key="payment_method-1",
            help="✨ 要查询的支付方式信息",
        )
        payment_4_cols[1].text_input(
            "备注",
            key="remark-1",
            help="✨ 要查询的备注信息",
        )
        query_button = st.form_submit_button(label="查询")

        if query_button:
            kwargs = {}
            if t0:
                kwargs.update(
                    {
                        "phone_number": st.session_state.get("phone_number-1", None),
                        "payment_id": st.session_state.get("payment_id-1", None),
                        "order_id": st.session_state.get("order_id-1", None),
                        "sales_representative": st.session_state.get(
                            "sales_representative-1", None
                        ),
                    }
                )
            if t1:
                kwargs.update(
                    {
                        "purchase_type": None
                        if st.session_state.get("purchase_type-1", None) == "ALL"
                        else str_to_enum(
                            st.session_state.get("purchase_type-1", None),
                            PurchaseType,
                        ),
                        "status": None
                        if st.session_state.get("status-1", None) == "ALL"
                        else str_to_enum(
                            st.session_state.get("status-1", None), PaymentStatus
                        ),
                        "is_approved": None
                        if st.session_state.get("is_approved-1", None) == "ALL"
                        else st.session_state.get("is_approved-1", None),
                    }
                )

            if t2:
                kwargs.update(generate_timestamp("payment_time", "start", 1))
                kwargs.update(generate_timestamp("payment_time", "end", 1))

            if t3:
                kwargs.update(generate_timestamp("expiry_time", "start", 1))
                kwargs.update(generate_timestamp("expiry_time", "end", 1))

            if t4:
                kwargs.update(
                    {
                        "payment_method": st.session_state.get(
                            "payment_method-1", None
                        ),
                        "remark": st.session_state.get("remark-1", None),
                    }
                )

            # 删除字典中的空值部分【None ""】
            kwargs = {k: v for k, v in kwargs.items() if v}
            st.write(f"{kwargs=}")

            # 检查数据生成的参数及其类型
            # st.write(kwargs)
            # for k, v in kwargs.items():
            #     st.write(f"{k=}, {type(v)=}")
            results = st.session_state.gdbi.query_payments(kwargs)
            # 将每个文档转换为字典
            dicts = [doc.to_dict() for doc in results]
            st.session_state["queried_payments"] = dicts

    st.subheader("支付清单")
    df = pd.DataFrame(st.session_state.get("queried_payments", {}))

    placeholder = st.empty()
    status = st.empty()
    approve_btn = st.button("更新", key="approve_btn")
    # # st.divider()
    if df.empty:
        placeholder.info("没有记录")
    else:
        # 将时间列转换为本地时区
        for col in TIME_COLS:
            if col in df.columns:
                df[col] = df[col].dt.tz_convert(tz)
        edited_df = placeholder.data_editor(
            df,
            column_config=COLUMN_CONFIG,
            column_order=COLUMN_ORDER,
            hide_index=True,
            key="users_payments",
            disabled=[col for col in df.columns if col not in EDITABLE_COLS],
        )

    # # Access edited data
    if approve_btn and st.session_state.get("users_payments", None):
        users_payments = st.session_state["users_payments"]
        # st.write(f"{users_payments=}")
        for idx, d in users_payments["edited_rows"].items():
            # st.write(f"{idx=}, {d=} {users_payments=}")
            phone_number = df.iloc[idx]["phone_number"]  # type: ignore
            purchase_type = df.iloc[idx]["purchase_type"]  # type: ignore
            order_id = df.iloc[idx]["order_id"]  # type: ignore
            # 修改权限
            if d.get("user_role", None):
                st.session_state.gdbi.update_user(phone_number, {"user_role": d["user_role"]})  # type: ignore
            # 批准
            if d.get("is_approved", False):
                st.session_state.gdbi.enable_service(
                    phone_number, order_id, purchase_type
                )
                st.toast(f"批准用户：{phone_number} {order_id}", icon="🎉")


# endregion

# region 创建处理反馈页面


@st.cache_data(ttl=60 * 60 * 1)  # 缓存有效期为1小时
def get_feedbacks():
    container_name = "feedback"
    connect_str = st.secrets["Microsoft"]["AZURE_STORAGE_CONNECTION_STRING"]
    blob_service_client = BlobServiceClient.from_connection_string(connect_str)
    container_client = blob_service_client.get_container_client(container_name)

    # 获取blob列表
    blobs_list = container_client.list_blobs()

    feedbacks = {}
    for blob in blobs_list:
        name, ext = os.path.splitext(blob.name)
        if name not in feedbacks:
            feedbacks[name] = {
                "txt": None,
                "webm": None,
                "delete": False,
                "view": False,
            }
        if ext == ".txt":
            feedbacks[name]["txt"] = blob.name
        elif ext == ".webm":
            feedbacks[name]["webm"] = blob.name

    return feedbacks


with tabs[items.index("处理反馈")]:
    st.subheader("处理反馈")
    container_name = "feedback"
    connect_str = st.secrets["Microsoft"]["AZURE_STORAGE_CONNECTION_STRING"]
    blob_service_client = BlobServiceClient.from_connection_string(connect_str)
    container_client = blob_service_client.get_container_client(container_name)

    feedbacks = get_feedbacks()
    # st.write(f"{feedbacks=}")
    if len(feedbacks):
        # 将反馈字典转换为一个DataFrame
        feedbacks_df = pd.DataFrame(feedbacks.values())
        feedbacks_df.columns = ["文件文件", "视频文件", "删除", "显示"]

        feedbacks_edited_df = st.data_editor(
            feedbacks_df, hide_index=True, key="feedbacks"
        )

        cols = st.columns(2)
        # 添加一个按钮来删除反馈
        if cols[0].button("删除", help="✨ 删除选中的反馈"):
            # 获取要删除的反馈
            edited_rows = st.session_state["feedbacks"]["edited_rows"]
            for idx, vs in edited_rows.items():
                if vs.get("删除", False):
                    try:
                        txt = feedbacks_df.iloc[idx]["文件文件"]
                        webm = feedbacks_df.iloc[idx]["视频文件"]
                        if txt is not None:
                            container_client.delete_blob(txt)
                            feedbacks_df.iloc[idx]["删除"] = True
                            st.toast(f"从blob中删除：{txt}", icon="🎉")
                        if webm is not None:
                            container_client.delete_blob(webm)
                            st.toast(f"从blob中删除：{webm}", icon="🎉")
                    except Exception as e:
                        pass

        if cols[1].button("显示", help="✨ 显示选中的反馈"):
            # 显示反馈
            edited_rows = st.session_state["feedbacks"]["edited_rows"]
            for idx, vs in edited_rows.items():
                if vs.get("显示", False):
                    deleted = feedbacks_df.iloc[idx]["删除"]
                    if not deleted:
                        try:
                            st.divider()
                            txt = feedbacks_df.iloc[idx]["文件文件"]
                            if txt is not None:
                                text_blob_client = blob_service_client.get_blob_client(
                                    container_name, txt
                                )
                                text_data = (
                                    text_blob_client.download_blob()
                                    .readall()
                                    .decode("utf-8")
                                )
                                st.text(f"{text_data}")
                            webm = feedbacks_df.iloc[idx]["视频文件"]
                            if webm is not None:
                                video_blob_client = blob_service_client.get_blob_client(
                                    container_name, webm
                                )
                                video_data = video_blob_client.download_blob().readall()
                                st.video(video_data)
                        except Exception as e:
                            pass

# endregion

# region 创建词典管理页面


def get_words():
    words = []
    fp = CURRENT_CWD / "resource" / "dictionary" / "word_lists_by_edition_grade.json"
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)
    for d in data.values():
        words.extend(d)
    words = set([w for w in words if w])
    logger.info(f"共有{len(words)}个单词")
    return words


@st.cache_data(ttl=60 * 60 * 2)  # 缓存有效期为2小时
def translate_text(text: str, target_language_code):
    return google_translate(text, target_language_code)


def translate_dict(d, target_language_code):
    res = {}
    if d.get("definition", None):
        res["definition"] = translate_text(d["definition"], target_language_code)
    examples = []
    for e in d["examples"]:
        examples.append(translate_text(e, target_language_code))
    res["examples"] = examples
    return res


def translate_pos(pos: str, target_language_code):
    res = []
    for d in pos:
        res.append(translate_dict(d, target_language_code))
    return res


def translate_doc(doc, target_language_code):
    doc[target_language_code] = {}
    doc[target_language_code]["translation"] = translate_text(
        doc["word"], target_language_code
    )
    for k, v in doc["en-US"].items():
        doc[target_language_code][k] = translate_pos(v, target_language_code)


def init_word_db():
    added = ()
    target_language_code = "zh-CN"
    fp = CURRENT_CWD / "resource" / "cambridge.json"
    with open(fp, "r", encoding="utf-8") as f:
        cambridge_dict = json.load(f)

    # 获取集合中的所有单词
    existing_words = [doc["word"] for doc in st.session_state.gdbi.words.find()]

    for doc in cambridge_dict:
        logger.info(f"单词：{doc['word']}...")
        if doc["word"] not in existing_words:
            translate_doc(doc, target_language_code)
            doc["level"] = get_lowest_cefr_level(doc["word"])
            try:
                logger.info(f"添加单词：{doc['word']}")
                st.session_state.gdbi.words.insert_one(doc)
                added += (doc["word"],)
            except Exception as e:
                logger.error(f"插入单词 {doc['word']} 时出现错误: {e}")

    words = get_words()
    for w in words:
        logger.info(f"单词：{w}...")
        if w not in added and w not in existing_words:
            try:
                logger.info(f"添加单词：{w}")
                st.session_state.gdbi.words.insert_one(
                    {
                        "word": w,
                        target_language_code: {
                            "translation": translate_text(w, target_language_code)
                        },
                        "level": get_lowest_cefr_level(w),
                    }
                )
            except Exception as e:
                logger.error(f"插入单词 {w} 时出现错误: {e}")


with tabs[items.index("词典管理")]:
    st.subheader("词典管理")
    if st.button("初始化词典"):
        init_word_db()

# endregion

# region 创建统计分析页面

# endregion
