import json
import logging
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from azure.storage.blob import BlobServiceClient
from pandas import Timedelta
from pymongo.errors import DuplicateKeyError

# from mypylib.auth_utils import generate_unique_code
from mypylib.authenticate import PRICES, Authenticator
from mypylib.db_model import Payment, PaymentStatus, PurchaseType, User, UserRole
from mypylib.google_api import get_translation_client, google_translate

# region 配置

# 创建或获取logger对象
logger = logging.getLogger("streamlit")
# 设置日志级别
logger.setLevel(logging.DEBUG)

current_cwd: Path = Path(__file__).parent.parent

if "google_translation_client" not in st.session_state:
    st.session_state["google_translation_client"] = get_translation_client(st.secrets)
# endregion

# region 常量配置

PM_OPTS = list(PaymentStatus)
COLUMN_CONFIG = {
    "payment_id": "付款编号",
    "order_id": "订单编号",
    "payment_time": "支付时间",
    "payment_method": "付款方式",
    "name": "姓名",
    "username": "用户名称",
    "phone_number": "手机号码",
    "purchase_type": st.column_config.SelectboxColumn(
        "套餐类型",
        help="购买的套餐类型",
        width="small",
        options=list(PurchaseType),
        default=list(PurchaseType)[-1],
        required=True,
    ),
    "receivable": st.column_config.NumberColumn(
        "应收 (元)",
        help="购买套餐应支付的金额",
        min_value=0.01,
        max_value=10000.00,
        step=0.01,
        format="￥%.2f",
    ),
    "payment_amount": st.column_config.NumberColumn(
        "实收 (元)",
        help="购买套餐实际支付的金额",
        min_value=0.01,
        max_value=10000.00,
        step=0.01,
        format="￥%.2f",
    ),
    "discount_rate": st.column_config.NumberColumn(
        "折扣率",
        help="享受的折扣率",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
        format="%.2f",
    ),
    "is_approved": st.column_config.CheckboxColumn(
        "是否批准",
        help="选中表示允许用户使用系统",
        default=False,
    ),
    "expiry_time": st.column_config.DatetimeColumn(
        "服务截至时间",
    ),
    "permission": st.column_config.SelectboxColumn(
        "权限",
        help="用户权限",
        width="small",
        options=list(UserRole),
        default=list(UserRole)[0],
        required=True,
    ),
    "registration_time": "注册时间",
    "status": st.column_config.SelectboxColumn(
        "服务状态",
        help="服务状态",
        width="small",
        options=PM_OPTS,
        default=PM_OPTS[-1],
        required=True,
    ),
    "remark": "服务备注",
    "memo": "用户备注",
}

TIME_COLS = ["payment_time", "expiry_time", "registration_time"]

EDITABLE_COLS: list[str] = [
    "is_approved",
    "permission",
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


def _normalized_query_params(
    d: dict,
    registration_on,
    payment_on,
    server_on,
):
    """
    根据查询参数字典和三个开关参数，返回标准化的查询参数字典。
    如果 registration_on 为 True，则将 registration_start_date 和 registration_start_time 合并为 registration_start_datetime，
    将 registration_end_date 和 registration_end_time 合并为 registration_end_datetime。
    如果 payment_on 为 True，则将 pay_start_date 和 pay_start_time 合并为 pay_start_datetime，
    将 pay_end_date 和 pay_end_time 合并为 pay_end_datetime。
    如果 server_on 为 True，则将 server_start_date 和 server_start_time 合并为 server_start_datetime，
    将 server_end_date 和 server_end_time 合并为 server_end_datetime。
    如果查询参数字典中的枚举值为 All，则忽略该查询条件。
    返回标准化后的查询参数字典。
    """

    res = {}
    if (
        registration_on
        and "registration_start_date" in d
        and "registration_start_time" in d
        and "registration_end_date" in d
        and "registration_end_time" in d
    ):
        res["registration_start_datetime"] = datetime.combine(
            d.pop("registration_start_date"), d.pop("registration_start_time")
        )
        res["registration_end_datetime"] = datetime.combine(
            d.pop("registration_end_date"), d.pop("registration_end_time")
        )
    else:
        d.pop("registration_start_date", None)
        d.pop("registration_start_time", None)
        d.pop("registration_end_date", None)
        d.pop("registration_end_time", None)

    if (
        payment_on
        and "pay_start_date" in d
        and "pay_end_date" in d
        and "pay_start_time" in d
        and "pay_end_time" in d
    ):
        res["pay_start_datetime"] = datetime.combine(
            d.pop("pay_start_date"), d.pop("pay_start_time")
        )
        res["pay_end_datetime"] = datetime.combine(
            d.pop("pay_end_date"), d.pop("pay_end_time")
        )
    else:
        d.pop("pay_start_date", None)
        d.pop("pay_start_time", None)
        d.pop("pay_end_date", None)
        d.pop("pay_end_time", None)

    if (
        server_on
        and "server_start_date" in d
        and "server_end_date" in d
        and "server_start_time" in d
        and "server_end_time" in d
    ):
        res["server_start_datetime"] = datetime.combine(
            d.pop("server_start_date"), d.pop("server_start_time")
        )
        res["server_end_datetime"] = datetime.combine(
            d.pop("server_end_date"), d.pop("server_end_time")
        )
    else:
        d.pop("server_start_date", None)
        d.pop("server_start_time", None)
        d.pop("server_end_date", None)
        d.pop("server_end_time", None)

    # 当枚举值为All时，忽略该查询条件
    for k, v in d.items():
        if v != "All":
            res[k] = v

    return res


def get_query_dict(
    names: list,
    index: int,
    registration_on,
    payment_on,
    server_on,
):
    res = {}
    for n in names:
        v = st.session_state.get(f"{n}-{index}", None)
        # 忽略空值
        if v == "":
            continue
        if v is not None:
            res[n] = st.session_state[f"{n}-{index}"]

    return _normalized_query_params(res, registration_on, payment_on, server_on)


def search(**kwargs):
    # 如果存在时间范围参数，创建一个新的字典来表示时间范围

    # 限定注册期间
    if (
        "registration_start_datetime" in kwargs
        and "registration_end_datetime" in kwargs
    ):
        kwargs["registration_time"] = {}
        kwargs["registration_time"]["$gte"] = kwargs.pop("registration_start_datetime")
        kwargs["registration_time"]["$lte"] = kwargs.pop("registration_end_datetime")

    # 限定支付期间
    if "pay_start_datetime" in kwargs and "pay_end_datetime" in kwargs:
        kwargs["payments.payment_time"] = {}
        kwargs["payments.payment_time"]["$gte"] = kwargs.pop("pay_start_datetime")
        kwargs["payments.payment_time"]["$lte"] = kwargs.pop("pay_end_datetime")

    if "server_start_datetime" in kwargs and "server_end_datetime" in kwargs:
        kwargs["payments.expiry_time"] = {}
        kwargs["payments.expiry_time"]["$gte"] = kwargs.pop("server_start_datetime")
        kwargs["payments.expiry_time"]["$lte"] = kwargs.pop("server_end_datetime")

    for field in PAYMENTS_FIELDS:
        if field in kwargs and field != "remark":
            kwargs[f"payments.{field}"] = kwargs.pop(field)

    if "memo" in kwargs:
        kwargs["memo"] = {"$regex": kwargs.pop("memo")}
    if "remark" in kwargs:
        kwargs["payments.remark"] = {"$regex": kwargs.pop("remark")}

    # 创建一个聚合管道
    pipeline = [
        {
            "$lookup": {
                "from": "payments",
                "localField": "phone_number",
                "foreignField": "phone_number",
                "as": "payments",
            }
        },
        {"$unwind": "$payments"},
        {"$match": kwargs},
        {
            "$project": {
                "phone_number": 1,
                "name": 1,
                "username": 1,
                "permission": 1,
                "registration_time": 1,
                "order_id": "$payments.order_id",
                "payment_id": "$payments.payment_id",
                "payment_time": "$payments.payment_time",
                "receivable": "$payments.receivable",
                "payment_amount": "$payments.payment_amount",
                "purchase_type": "$payments.purchase_type",
                "discount_rate": "$payments.discount_rate",
                "payment_method": "$payments.payment_method",
                "is_approved": "$payments.is_approved",
                "expiry_time": "$payments.expiry_time",
                "status": "$payments.status",
                "remark": "$payments.remark",
                "memo": 1,
                "_id": 0,
            }
        },
    ]

    # from pprint import pprint

    # pprint(pipeline)
    # pprint("=" * 60)
    # 执行聚合查询
    result = list(st.session_state.auth.users.aggregate(pipeline))

    return result


# endregion

# region 会话状态

if st.session_state.get("search"):
    st.session_state["searched_data"] = []

if "user_id" not in st.session_state:
    st.session_state["user_id"] = None

if "auth" not in st.session_state:
    st.session_state["auth"] = Authenticator()

if not (
    st.session_state.get("user_id")
    and st.session_state.auth.is_admin(st.session_state.get("user_id"))
):
    st.error("对不起，您没有权限访问该页面。该页面仅限系统管理员使用。")
    st.stop()

# endregion

# 创建选项卡
items = ["订阅登记", "用户管理", "处理反馈", "词典管理", "统计分析"]
tabs = st.tabs(items)


# region 创建收费登记页面


def compute_discounted_price():
    dtype = st.session_state["purchase_type"]
    price = PRICES[dtype]
    discount_rate = st.session_state["discount_rate"]
    st.session_state["receivable"] = price * (1 - discount_rate)


with tabs[items.index("订阅登记")]:
    st.subheader("登记收款")
    # with st.form(key="payment_form", clear_on_submit=True):
    with st.form(key="payment_form"):
        cols = st.columns(2)
        phone_number = cols[0].text_input(
            "手机号码",
            key="phone_number",
            help="请输入有效手机号码",
            placeholder="必须",
        )
        purchase_type = cols[1].selectbox(
            "套餐类型",
            key="purchase_type",
            help="请选择套餐类型",
            options=list(PurchaseType),
            index=1,
            format_func=lambda x: x.value,
        )
        payment_method = cols[0].text_input(
            "付款方式", key="payment_method", help="请输入付款方式", placeholder="必须。付款方式"
        )
        payment_id = cols[1].text_input(
            "付款编号", key="payment_id", help="请输入付款编号", placeholder="必须。请在付款凭证上查找付款编号"
        )
        payment_amount = cols[0].number_input(
            "实收金额", key="payment_amount", help="请输入实际收款金额", value=0.0
        )
        remark = st.text_input("备注", key="remark", help="请输入备注信息", value="")
        user = st.session_state.auth.find_user(phone_number=phone_number)
        if st.form_submit_button(label="登记"):
            order_id = str(
                st.session_state.auth.payments.count_documents({}) + 1
            ).zfill(10)
            receivable = PRICES[purchase_type]  # type: ignore
            payment = Payment(
                phone_number=phone_number,
                payment_id=payment_id,
                payment_time=datetime.utcnow(),
                receivable=receivable,
                payment_amount=payment_amount,  # type: ignore
                purchase_type=purchase_type,  # type: ignore
                order_id=order_id,
                payment_method=payment_method,
                discount_rate=payment_amount / receivable,
                remark=remark,
            )
            try:
                st.session_state.auth.add_payment(payment)
                st.toast(f"成功登记，订单号:{order_id}", icon="🎉")
            except DuplicateKeyError:
                st.error("付款编号已存在，请勿重复登记")
                st.stop()
            except Exception as e:
                raise  # 重新抛出异常

# endregion

# region 创建用户管理页面


with tabs[items.index("用户管理")]:
    st.markdown("#### 查询参数")
    # with st.form(key="query_form", clear_on_submit=True):
    with st.form(key="query_form"):
        # with st.form(key="query_form"):
        user_cols = st.columns(5)
        user_cols[0].text_input(label="手机号码", key="phone_number-1")
        user_cols[1].text_input(label="邮箱", key="email-1")
        user_cols[2].text_input(label="姓名", key="name-1")
        user_cols[3].text_input(label="用户名称", key="username-1")

        user_cols[4].selectbox(
            "用户权限",
            key="permission-1",
            options=["All"] + [x.value for x in list(UserRole)],
            # format_func=lambda x: x.value,
            index=0,
        )

        user_time_cols = st.columns(5)

        user_time_cols[0].date_input(
            "用户注册：开始日期",
            key="registration_start_date-1",
            value=(datetime.utcnow() - timedelta(days=365)).date(),
        )
        user_time_cols[1].time_input(
            "时间", value=time(0, 0, 0), key="registration_start_time-1"
        )  # type: ignore
        user_time_cols[2].date_input(
            "结束日期", key="registration_end_date-1", value=datetime.utcnow().date()
        )
        user_time_cols[3].time_input(
            "时间", key="registration_end_time-1", value=time(23, 59, 59)
        )

        pay_cols = st.columns(5)
        pay_cols[0].text_input(label="订单编号", key="order_id-1")
        pay_cols[1].text_input(label="付款编号", key="payment_id-1")
        pay_cols[2].selectbox(
            "服务状态",
            key="status-1",
            options=["All"] + [x.value for x in list(PaymentStatus)],
            index=0,
        )
        pay_cols[3].selectbox(
            "套餐类型",
            key="purchase_type-1",
            # options=list(PurchaseType),
            options=["All"] + [x.value for x in list(PurchaseType)],
            index=0,
            # format_func=lambda x: x.value,
        )
        pay_cols[4].selectbox(
            "是否已批准", key="is_approved-1", options=["All", False, True], index=0
        )

        payment_time_cols = st.columns(5)
        payment_time_cols[0].date_input(
            "支付查询：开始日期",
            key="pay_start_date-1",
            value=(datetime.utcnow() - timedelta(days=7)).date(),
        )
        payment_time_cols[1].time_input(
            "时间", value=time(0, 0, 0), key="pay_start_time-1"
        )  # type: ignore
        payment_time_cols[2].date_input(
            "结束日期", key="pay_end_date-1", value=datetime.utcnow().date()
        )
        payment_time_cols[3].time_input(
            "时间", key="pay_end_time-1", value=time(23, 59, 59)
        )

        payment_time_cols[0].date_input(
            "服务截至：开始日期",
            key="server_start_date-1",
            value=(datetime.utcnow() - timedelta(days=7)).date(),
        )
        payment_time_cols[1].time_input(
            "时间", value=time(0, 0, 0), key="server_start_time-1"
        )  # type: ignore
        payment_time_cols[2].date_input(
            "结束日期", key="server_end_date-1", value=datetime.utcnow().date()
        )
        payment_time_cols[3].time_input(
            "时间", key="server_end_time-1", value=time(23, 59, 59)
        )
        memo_cols = st.columns(2)
        memo_cols[0].text_input(label="用户备注", key="memo-1")
        memo_cols[1].text_input(label="付款备注", key="remark-1")
        btn_cols = st.columns(5)
        # plus_arg_on = btn_cols[0].toggle("添加支付参数？", key="plu_pay_arg", value=False)
        registration_on = btn_cols[0].checkbox(
            "限制注册时间", key="registration-1", value=False
        )
        payment_on = btn_cols[1].checkbox("限制支付时间", key="payment-1", value=False)
        server_on = btn_cols[2].checkbox("限制服务时间", key="server-1", value=False)
        query_button = btn_cols[3].form_submit_button(label="查询")

        if query_button:
            kwargs = get_query_dict(
                [
                    "is_approved",
                    "phone_number",
                    "email",
                    "name",
                    "username",
                    "permission",
                    "registration_start_date",
                    "registration_start_time",
                    "registration_end_date",
                    "registration_end_time",
                    "order_id",
                    "payment_id",
                    "status",
                    "purchase_type",
                    "pay_start_date",
                    "pay_start_time",
                    "pay_end_date",
                    "pay_end_time",
                    "server_start_date",
                    "server_start_time",
                    "server_end_date",
                    "server_end_time",
                    "memo",
                    "remark",
                ],
                1,
                registration_on,
                payment_on,
                server_on,
            )
            # 检查数据生成的参数及其类型
            # st.write(kwargs)
            # for k, v in kwargs.items():
            #     st.write(f"{k=}, {type(v)=}")
            st.session_state["searched_data"] = search(**kwargs)

    st.markdown("#### 查询结果")
    df = pd.DataFrame.from_records(
        st.session_state.get("searched_data", []), columns=COLUMN_CONFIG.keys()
    )

    # if not df.empty:
    #     for col in TIME_COLS:
    #         df[col] = df[col] + Timedelta(hours=8)

    placeholder = st.empty()
    status = st.empty()
    approve_btn = st.button("更新", key="approve_btn")
    # # st.divider()
    if df.empty:
        placeholder.info("没有记录")
    else:
        edited_df = placeholder.data_editor(
            df,
            column_config=COLUMN_CONFIG,
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
            if d.get("permission", None):
                st.session_state.auth.update_user(phone_number, {"permission": d["permission"]})  # type: ignore
            # 批准
            if d.get("is_approved", False):
                st.session_state.auth.enable_service(
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
        if cols[0].button("删除", help="删除选中的反馈"):
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

        if cols[1].button("显示", help="显示选中的反馈"):
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

# 基础词库
# 剑桥词典
# 翻译
# 添加单词


def get_words():
    words = []
    fp = current_cwd / "resource" / "dictionary" / "word_lists_by_edition_grade.json"
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)
    for d in data.values():
        words.extend(d)
    words = set([w for w in words if w])
    logger.info(f"共有{len(words)}个单词")
    return words


def translate_text(text: str, target_language_code):
    return google_translate(
        text, st.session_state.google_translation_client, target_language_code
    )


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
    if st.session_state.auth.words.count_documents({}) == 0:
        fp = current_cwd / "resource" / "cambridge.json"
        with open(fp, "r", encoding="utf-8") as f:
            cambridge_dict = json.load(f)
            for doc in cambridge_dict:
                doc[target_language_code] = translate_doc(doc, target_language_code)
                st.session_state.auth.words.insert_one(doc)
                added += (doc["word"],)
                # 临时测试
                break

        words = get_words()
        for w in words:
            if w not in added:
                st.session_state.auth.words.insert_one(
                    {
                        "word": w,
                        target_language_code: {
                            "translation": translate_text(w, target_language_code)
                        },
                    }
                )
                # 临时测试
                break


with tabs[items.index("词典管理")]:
    st.subheader("词典管理")
    if st.button("初始化词典"):
        init_word_db()

# endregion

# region 创建统计分析页面

# endregion
