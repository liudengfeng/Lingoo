import os
from pathlib import Path

import streamlit as st
import vertexai
from PIL import Image as PImage
from vertexai.generative_models._generative_models import ContentsType
from vertexai.preview.generative_models import (GenerationConfig,
                                                GenerativeModel, Part)

from mypylib.ai_utils import view_stream_response
from mypylib.google_cloud_configuration import DEFAULT_SAFETY_SETTINGS
from mypylib.st_utils import (authenticate_and_configure_services,
                              check_and_force_logout, load_vertex_model)

CURRENT_CWD: Path = Path(__file__).parent.parent
IMAGE_DIR: Path = CURRENT_CWD / "resource/multimodal"

authenticate_and_configure_services()

gemini_pro_vision_generation_config = {
    "max_output_tokens": 2048,
    "temperature": 0.4,
    "top_p": 1,
    "top_k": 32,
}


def get_gemini_pro_text_response(
    model: GenerativeModel,
    contents: ContentsType,
    generation_config: GenerationConfig,
    stream=True,
):
    return model.generate_content(
        contents,
        generation_config=generation_config,
        safety_settings=DEFAULT_SAFETY_SETTINGS,
        stream=stream,
    )


def get_gemini_pro_vision_response(
    model, prompt_list, generation_config=None, stream=True
):
    if generation_config is None:
        generation_config = gemini_pro_vision_generation_config
    return model.generate_content(
        prompt_list,
        generation_config=generation_config,
        safety_settings=DEFAULT_SAFETY_SETTINGS,
        stream=stream,
    )


help_info = "✨ 对于 Gemini 模型，一个令牌约相当于 4 个字符。100 个词元约为 60-80 个英语单词。"
sidebar_status = st.sidebar.empty()
sidebar_status.markdown(
    f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{st.session_state.total_token_count}",
    help=help_info,
)

# region 认证及强制退出

check_and_force_logout(sidebar_status)

# endregion

st.header("Vertex AI Gemini 示例", divider="rainbow")

if "text_model_pro" not in st.session_state:
    st.session_state["text_model_pro"] = load_vertex_model("gemini-pro")

if "multimodal_model_pro" not in st.session_state:
    st.session_state["multimodal_model_pro"] = load_vertex_model("gemini-pro-vision")


tab1, tab2, tab3, tab4 = st.tabs(["生成故事", "营销活动", "图像游乐场", "视频游乐场"])

with tab1:
    st.write("使用 Gemini Pro - 仅有文本模型")
    st.subheader("生成一个故事")

    # Story premise
    character_name = st.text_input("输入角色名称：", key="character_name", value="七七")
    character_type = st.text_input("它是什么类型的角色？ ", key="character_type", value="狗")
    character_persona = st.text_input(
        "这个角色有什么性格？",
        key="character_persona",
        value="七七是一只非常黏人的比熊犬。",
    )
    character_location = st.text_input(
        "角色住在哪里？",
        key="character_location",
        value="山城重庆",
    )
    story_premise = st.multiselect(
        "故事前提是什么？ (可以选择多个)",
        ["爱", "冒险", "神秘", "恐怖", "喜剧", "科幻", "幻想", "惊悚片"],
        key="story_premise",
        default=["神秘", "喜剧"],
    )
    creative_control = st.radio(
        "选择创意级别：",
        ["低", "高"],
        key="creative_control",
        horizontal=True,
    )
    length_of_story = st.radio(
        "选择故事的长度:",
        ["短", "长"],
        key="length_of_story",
        horizontal=True,
    )

    if creative_control == "低":
        temperature = 0.30
    else:
        temperature = 0.95

    max_output_tokens = 2048

    prompt = f"""根据以下前提编写一个 {length_of_story} 故事：\n
    角色名称: {character_name} \n
    角色类型：{character_type} \n
    角色性格：{character_persona} \n
    角色位置：{character_location} \n
    故事前提：{",".join(story_premise)} \n
    如果故事“短”，则确保有 5 章，如果故事“长”，则确保有 10 章。
    重要的一点是，每一章都应该基于上述前提生成。
    首先介绍本书，然后介绍章节，之后逐一介绍每一章。 应该有一个合适的结局。
    这本书应该有序言和结语。
    """
    config = {
        "temperature": 0.8,
        "max_output_tokens": 2048,
    }

    generate_t2t = st.button("生成我的故事", key="generate_t2t")
    if generate_t2t and prompt:
        # st.write(prompt)
        with st.spinner("使用 Gemini 生成您的故事..."):
            first_tab1, first_tab2, first_tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
            with first_tab1:
                response = get_gemini_pro_text_response(
                    st.session_state.text_model_pro,
                    prompt,
                    generation_config=config,
                )
                if response:
                    st.write("生成的故事：")
                    placeholder = st.empty()
                    # st.write(response)
                    view_stream_response(response, placeholder)
            with first_tab2:
                st.text(prompt)
            with first_tab3:
                st.write("参数设置：")
                st.write(config)

with tab2:
    st.write("使用 Gemini Pro - 仅有文本模型")
    st.subheader("生成您的营销活动")

    product_name = st.text_input("产品名称是什么？", key="product_name", value="ZomZoo")
    product_category = st.radio(
        "选择您的产品类别：",
        ["服装", "电子产品", "食品", "健康与美容", "家居与园艺"],
        key="product_category",
        horizontal=True,
    )
    st.write("选择您的目标受众：")
    target_audience_age = st.radio(
        "目标年龄：",
        ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
        key="target_audience_age",
        horizontal=True,
    )
    # target_audience_gender = st.radio("Target gender: \n\n",["male","female","trans","non-binary","others"],key="target_audience_gender",horizontal=True)
    target_audience_location = st.radio(
        "目标位置：",
        ["城市", "郊区", "乡村"],
        key="target_audience_location",
        horizontal=True,
    )
    st.write("选择您的营销活动目标：")
    campaign_goal = st.multiselect(
        "选择您的营销活动目标：",
        [
            "提高品牌知名度",
            "产生潜在客户",
            "推动销售",
            "提高品牌情感",
        ],
        key="campaign_goal",
        default=["提高品牌知名度", "产生潜在客户"],
    )
    if campaign_goal is None:
        campaign_goal = ["提高品牌知名度", "产生潜在客户"]
    brand_voice = st.radio(
        "选择您的品牌风格：",
        ["正式", "非正式", "严肃", "幽默"],
        key="brand_voice",
        horizontal=True,
    )
    estimated_budget = st.radio(
        "选择您的估计预算（人民币）：",
        ["1,000-5,000", "5,000-10,000", "10,000-20,000", "20,000+"],
        key="estimated_budget",
        horizontal=True,
    )

    prompt = f"""为 {product_name} 生成营销活动，该 {product_category} 专为年龄组：{target_audience_age} 设计。
    目标位置是：{target_audience_location}。
    主要目标是实现{campaign_goal}。
    使用 {brand_voice} 的语气强调产品的独特销售主张。
    分配总预算 {estimated_budget} 元【人民币】。
    遵循上述条件，请确保满足以下准则并生成具有正确标题的营销活动：\n
    - 简要描述公司、其价值观、使命和目标受众。
    - 突出显示任何相关的品牌指南或消息传递框架。
    - 简要概述活动的目的和目标。
    - 简要解释所推广的产品或服务。
    - 通过清晰的人口统计数据、心理统计数据和行为洞察来定义您的理想客户。
    - 了解他们的需求、愿望、动机和痛点。
    - 清楚地阐明活动的预期结果。
    - 为了清晰起见，使用 SMART 目标（具体的、可衡量的、可实现的、相关的和有时限的）。
    - 定义关键绩效指标 (KPI) 来跟踪进度和成功。
    - 指定活动的主要和次要目标。
    - 示例包括品牌知名度、潜在客户开发、销售增长或网站流量。
    - 明确定义您的产品或服务与竞争对手的区别。
    - 强调为目标受众提供的价值主张和独特优势。
    - 定义活动信息所需的基调和个性。
    - 确定您将用于接触目标受众的具体渠道。
    - 清楚地说明您希望观众采取的期望行动。
    - 使其具体、引人注目且易于理解。
    - 识别并分析市场上的主要竞争对手。
    - 了解他们的优势和劣势、目标受众和营销策略。
    - 制定差异化战略以在竞争中脱颖而出。
    - 定义您将如何跟踪活动的成功。
    - 利用相关的 KPI 来衡量绩效和投资回报 (ROI)。
    为营销活动提供适当的要点和标题。 不要产生任何空行。
    非常简洁并切中要点。
    """
    config = {
        "temperature": 0.8,
        "max_output_tokens": 2048,
    }
    generate_t2t = st.button("生成我的活动", key="generate_campaign")
    if generate_t2t and prompt:
        second_tab1, second_tab2, second_tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
        with st.spinner("使用 Gemini 生成您的营销活动..."):
            with second_tab1:
                response = get_gemini_pro_text_response(
                    st.session_state.text_model_pro,
                    prompt,
                    generation_config=config,
                )
                if response:
                    st.write("Your marketing campaign:")
                    placeholder = st.empty()
                    # st.write(response)
                    view_stream_response(response, placeholder)
            with second_tab2:
                st.text(prompt)
            with second_tab3:
                st.write(config)

with tab3:
    st.write("使用 Gemini Pro Vision - 多模态模型")
    image_undst, screens_undst, diagrams_undst, recommendations, sim_diff = st.tabs(
        [
            "家具推荐",
            "烤箱使用说明",
            "实体关系（ER）图",
            "眼镜推荐",
            "数学推理",
        ]
    )

    with image_undst:
        st.markdown(
            """在此演示中，您将看到一个场景（例如客厅），并将使用 Gemini 模型来执行视觉理解。 您将看到如何使用 Gemini 从家具选项列表中推荐一个项目（例如一把椅子）作为输入。 您可以使用 Gemini 推荐一把可以补充给定场景的椅子，并将从提供的列表中提供其选择的理由。
        """
        )

        room_image_uri = (
            "gs://github-repo/img/gemini/retail-recommendations/rooms/living_room.jpeg"
        )
        chair_1_image_uri = (
            "gs://github-repo/img/gemini/retail-recommendations/furnitures/chair1.jpeg"
        )
        chair_2_image_uri = (
            "gs://github-repo/img/gemini/retail-recommendations/furnitures/chair2.jpeg"
        )
        chair_3_image_uri = (
            "gs://github-repo/img/gemini/retail-recommendations/furnitures/chair3.jpeg"
        )
        chair_4_image_uri = (
            "gs://github-repo/img/gemini/retail-recommendations/furnitures/chair4.jpeg"
        )

        room_image_urls = (
            "https://storage.googleapis.com/" + room_image_uri.split("gs://")[1]
        )
        chair_1_image_urls = (
            "https://storage.googleapis.com/" + chair_1_image_uri.split("gs://")[1]
        )
        chair_2_image_urls = (
            "https://storage.googleapis.com/" + chair_2_image_uri.split("gs://")[1]
        )
        chair_3_image_urls = (
            "https://storage.googleapis.com/" + chair_3_image_uri.split("gs://")[1]
        )
        chair_4_image_urls = (
            "https://storage.googleapis.com/" + chair_4_image_uri.split("gs://")[1]
        )

        room_image = Part.from_uri(room_image_uri, mime_type="image/jpeg")
        chair_1_image = Part.from_uri(chair_1_image_uri, mime_type="image/jpeg")
        chair_2_image = Part.from_uri(chair_2_image_uri, mime_type="image/jpeg")
        chair_3_image = Part.from_uri(chair_3_image_uri, mime_type="image/jpeg")
        chair_4_image = Part.from_uri(chair_4_image_uri, mime_type="image/jpeg")

        st.image(room_image_urls, width=350, caption="客厅的图像")
        st.image(
            [
                chair_1_image_urls,
                chair_2_image_urls,
                chair_3_image_urls,
                chair_4_image_urls,
            ],
            width=200,
            caption=["椅子 1", "椅子 2", "椅子 3", "椅子 4"],
        )

        st.write("我们的期望：推荐一把与客厅既定形象相得益彰的椅子。")
        content = [
            "考虑以下椅子：",
            "椅子 1:",
            chair_1_image,
            "椅子 2:",
            chair_2_image,
            "椅子 3:",
            chair_3_image,
            "以及",
            "椅子 4:",
            chair_4_image,
            "\n" "对于每把椅子，请解释为什么它适合或不适合以下房间：",
            room_image,
            "只推荐所提供的房间，不推荐其他房间。 以表格形式提供您的建议，并以椅子名称和理由为标题列。",
        ]

        tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
        generate_image_description = st.button("生成推荐", key="generate_image_description")
        with tab1:
            if generate_image_description and content:
                with st.spinner("使用 Gemini 生成推荐..."):
                    response = get_gemini_pro_vision_response(
                        st.session_state.multimodal_model_pro, content
                    )
                    placeholder = st.empty()
                    # st.write(response)
                    view_stream_response(response, placeholder)
        with tab2:
            st.write("使用的提示词：")
            st.text(content)
        with tab2:
            st.write("使用的参数：")
            st.write(None)

    with screens_undst:
        stove_screen_uri = (
            "gs://github-repo/img/gemini/multimodality_usecases_overview/stove.jpg"
        )
        stove_screen_url = (
            "https://storage.googleapis.com/" + stove_screen_uri.split("gs://")[1]
        )

        st.write("Gemini 能够从屏幕上的视觉元素中提取信息，可以分析屏幕截图、图标和布局，以全面了解所描绘的场景。")
        # cooking_what = st.radio("What are you cooking?",["Turkey","Pizza","Cake","Bread"],key="cooking_what",horizontal=True)
        stove_screen_img = Part.from_uri(stove_screen_uri, mime_type="image/jpeg")
        st.image(stove_screen_url, width=350, caption="烤箱的图像")
        st.write("我们的期望：提供有关重置此设备时钟的中文说明")
        prompt = """如何重置此设备上的时钟？ 提供中文说明。
如果说明包含按钮，还要解释这些按钮的物理位置。
"""
        tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
        generate_instructions_description = st.button(
            "生成指令", key="generate_instructions_description"
        )
        with tab1:
            if generate_instructions_description and prompt:
                with st.spinner("使用 Gemini 生成指令..."):
                    response = get_gemini_pro_vision_response(
                        st.session_state.multimodal_model_pro,
                        [stove_screen_img, prompt],
                    )
                    placeholder = st.empty()
                    # st.write(response)
                    view_stream_response(response, placeholder)
        with tab2:
            st.write("使用的提示词：")
            st.text(prompt + "\n" + "input_image")
        with tab3:
            st.write("使用的参数：")
            st.write("默认参数")

    with diagrams_undst:
        er_diag_uri = (
            "gs://github-repo/img/gemini/multimodality_usecases_overview/er.png"
        )
        er_diag_url = "https://storage.googleapis.com/" + er_diag_uri.split("gs://")[1]

        st.write(
            "Gemini 的多模式功能使其能够理解图表并采取可操作的步骤，例如优化或代码生成。 以下示例演示了 Gemini 如何解读实体关系 (ER) 图。"
        )
        er_diag_img = Part.from_uri(er_diag_uri, mime_type="image/jpeg")
        st.image(er_diag_url, width=350, caption="Image of a ER diagram")
        st.write("我们的期望：记录此 ER 图中的实体和关系。")
        prompt = """记录此 ER 图中的实体和关系。"""
        tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
        er_diag_img_description = st.button("生成！", key="er_diag_img_description")
        with tab1:
            if er_diag_img_description and prompt:
                with st.spinner("生成..."):
                    response = get_gemini_pro_vision_response(
                        st.session_state.multimodal_model_pro, [er_diag_img, prompt]
                    )
                    placeholder = st.empty()
                    # st.write(response)
                    view_stream_response(response, placeholder)
        with tab2:
            st.write("使用的提示词：")
            st.text(prompt + "\n" + "input_image")
        with tab3:
            st.write("使用的参数：")
            st.text("默认参数")

    with recommendations:
        compare_img_1_uri = (
            "gs://github-repo/img/gemini/multimodality_usecases_overview/glasses1.jpg"
        )
        compare_img_2_uri = (
            "gs://github-repo/img/gemini/multimodality_usecases_overview/glasses2.jpg"
        )

        compare_img_1_url = (
            "https://storage.googleapis.com/" + compare_img_1_uri.split("gs://")[1]
        )
        compare_img_2_url = (
            "https://storage.googleapis.com/" + compare_img_2_uri.split("gs://")[1]
        )

        st.write(
            """Gemini 能够进行图像比较并提供建议。 这在电子商务和零售等行业可能很有用。
            以下是选择哪副眼镜更适合不同脸型的示例："""
        )
        compare_img_1_img = Part.from_uri(compare_img_1_uri, mime_type="image/jpeg")
        compare_img_2_img = Part.from_uri(compare_img_2_uri, mime_type="image/jpeg")
        face_type = st.radio(
            "你是什么脸型？",
            ["椭圆形", "圆形", "方形", "心形", "钻石形"],
            key="face_type",
            horizontal=True,
        )
        output_type = st.radio(
            "选择输出类型",
            ["text", "table", "json"],
            key="output_type",
            horizontal=True,
        )
        st.image(
            [compare_img_1_url, compare_img_2_url],
            width=350,
            caption=["眼镜类型 1", "眼镜类型 2"],
        )
        st.write(f"我们的期望：建议哪种眼镜类型更适合 {face_type} 脸型")
        content = [
            f"""根据我的脸型，您为我推荐哪一款眼镜：{face_type}?
           我有一张 {face_type} 形状的脸。
           眼镜 1: """,
            compare_img_1_img,
            """
           眼镜 2: """,
            compare_img_2_img,
            f"""
           解释一下你是如何做出这个决定的。
           根据我的脸型提供您的建议，并以 {output_type} 格式对每个脸型进行推理。
           """,
        ]
        tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
        compare_img_description = st.button("生成推荐", key="compare_img_description")
        with tab1:
            if compare_img_description and content:
                with st.spinner("使用 Gemini 生成推荐..."):
                    response = get_gemini_pro_vision_response(
                        st.session_state.multimodal_model_pro, content
                    )
                    placeholder = st.empty()
                    # st.write(response)
                    view_stream_response(response, placeholder)
        with tab2:
            st.write("使用的提示词：")
            st.text(content)
        with tab3:
            st.write("使用的参数：")
            st.text("默认参数")

    with sim_diff:
        math_image_uri = "gs://github-repo/img/gemini/multimodality_usecases_overview/math_beauty.jpg"
        math_image_url = (
            "https://storage.googleapis.com/" + math_image_uri.split("gs://")[1]
        )
        st.write("Gemini 还可以识别数学公式和方程，并从中提取特定信息。 此功能对于生成数学问题的解释特别有用，如下所示。")
        math_image_img = Part.from_uri(math_image_uri, mime_type="image/jpeg")
        st.image(math_image_url, width=350, caption="Image of a math equation")
        st.markdown(
            f"""
我们的期望：提出有关数学方程的问题如下：
- 提取公式。
- Pi 前面的符号是什么？ 这是什么意思？
- 这是一个著名的公式吗？ 它有名字吗？
"""
        )
        prompt = """
按照说明进行操作。
用"$"将数学表达式括起来。
使用一个表格，其中一行代表每条指令及其结果。

指示：
- 提取公式。
- $\pi$ 前面的符号是什么？ 这是什么意思？
- 这是一个著名的公式吗？ 它有名字吗？
"""
        tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
        math_image_description = st.button("生成答案", key="math_image_description")
        with tab1:
            if math_image_description and prompt:
                with st.spinner("使用 Gemini 生成公式答案..."):
                    response = get_gemini_pro_vision_response(
                        st.session_state.multimodal_model_pro,
                        [math_image_img, prompt],
                    )
                    placeholder = st.empty()
                    # st.write(response)
                    view_stream_response(response, placeholder)
        with tab2:
            st.write("使用的提示词：")
            st.text(content)
        with tab3:
            st.write("使用的参数：")
            st.text("默认参数")

with tab4:
    st.write("使用 Gemini Pro Vision - 多模态模型")

    vide_desc, video_tags, video_highlights, video_geoloaction = st.tabs(
        ["视频描述", "视频标签", "视频亮点", "视频地理位置"]
    )

    with vide_desc:
        st.markdown("""Gemini 还可以提供视频中发生的情况的描述：""")
        vide_desc_uri = "gs://github-repo/img/gemini/multimodality_usecases_overview/mediterraneansea.mp4"
        video_desc_url = (
            "https://storage.googleapis.com/" + vide_desc_uri.split("gs://")[1]
        )
        if vide_desc_uri:
            vide_desc_img = Part.from_uri(vide_desc_uri, mime_type="video/mp4")
            st.video(video_desc_url)
            st.write("我们的期望：生成视频的描述")
            prompt = """描述视频中发生的事情并回答以下问题：\n
- 我在看什么？ \n
- 我应该去哪里看？ \n
- 世界上还有哪些像这样的前 5 个地方？
            """
            tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
            vide_desc_description = st.button("生成视频描述", key="vide_desc_description")
            with tab1:
                if vide_desc_description and prompt:
                    with st.spinner("使用 Gemini 生成视频描述..."):
                        response = get_gemini_pro_vision_response(
                            st.session_state.multimodal_model_pro,
                            [prompt, vide_desc_img],
                        )
                        placeholder = st.empty()
                        # st.write(response)
                        view_stream_response(response, placeholder)
                        st.markdown("\n\n\n")
            with tab2:
                st.write("使用的提示词：")
                st.markdown(prompt + "\n" + "{video_data}")
            with tab3:
                st.write("使用的参数：")
                st.write("默认参数")

    with video_tags:
        st.markdown("""Gemini 还可以提取整个视频中的标签，如下所示：""")
        video_tags_uri = "gs://github-repo/img/gemini/multimodality_usecases_overview/photography.mp4"
        video_tags_url = (
            "https://storage.googleapis.com/" + video_tags_uri.split("gs://")[1]
        )
        if video_tags_url:
            video_tags_img = Part.from_uri(video_tags_uri, mime_type="video/mp4")
            st.video(video_tags_url)
            st.write("我们的期望：为视频生成标签")
            prompt = """仅使用视频回答以下问题：
1. 视频里讲了什么？
2. 视频中有哪些物体？
3. 视频中的动作是什么？
4. 为该视频提供5个最佳标签？
以表格形式给出答案，问题和答案作为列。
            """
            tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
            video_tags_description = st.button("生成标签", key="video_tags_description")
            with tab1:
                if video_tags_description and prompt:
                    with st.spinner("使用 Gemini 生成视频描述..."):
                        response = get_gemini_pro_vision_response(
                            st.session_state.multimodal_model_pro,
                            [prompt, video_tags_img],
                        )
                        placeholder = st.empty()
                        # st.write(response)
                        view_stream_response(response, placeholder)
                        st.markdown("\n\n\n")
            with tab2:
                st.write("使用的提示词：")
                st.write(prompt, "\n", "{video_data}")
            with tab3:
                st.write("使用的参数：")
                st.write("默认参数")

    with video_highlights:
        st.markdown("""下面是使用 Gemini 询问有关物体、人或上下文的问题的另一个示例，如下面有关 Pixel 8 的视频所示：""")
        video_highlights_uri = (
            "gs://github-repo/img/gemini/multimodality_usecases_overview/pixel8.mp4"
        )
        video_highlights_url = (
            "https://storage.googleapis.com/" + video_highlights_uri.split("gs://")[1]
        )
        if video_highlights_url:
            video_highlights_img = Part.from_uri(
                video_highlights_uri, mime_type="video/mp4"
            )
            st.video(video_highlights_url)
            st.write("我们的期望：生成视频的亮点")
            prompt = """仅使用视频回答以下问题：
视频中的女孩是什么职业？
这里重点介绍了手机的哪些功能？
用一段总结视频。
以表格形式提供答案。
            """
            tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
            video_highlights_description = st.button(
                "生成视频精彩片段", key="video_highlights_description"
            )
            with tab1:
                if video_highlights_description and prompt:
                    with st.spinner("使用 Gemini 生成视频集锦..."):
                        response = get_gemini_pro_vision_response(
                            st.session_state.multimodal_model_pro,
                            [prompt, video_highlights_img],
                        )
                        placeholder = st.empty()
                        # st.write(response)
                        view_stream_response(response, placeholder)
                        st.markdown("\n\n\n")
            with tab2:
                st.write("使用的提示词：")
                st.write(prompt, "\n", "{video_data}")
            with tab3:
                st.write("使用的参数：")
                st.write(gemini_pro_vision_generation_config)

    with video_geoloaction:
        st.markdown("""即使在简短、细节丰富的视频中，Gemini 也能识别出位置。""")
        video_geoloaction_uri = (
            "gs://github-repo/img/gemini/multimodality_usecases_overview/bus.mp4"
        )
        video_geoloaction_url = (
            "https://storage.googleapis.com/" + video_geoloaction_uri.split("gs://")[1]
        )
        if video_geoloaction_url:
            video_geoloaction_img = Part.from_uri(
                video_geoloaction_uri, mime_type="video/mp4"
            )
            st.video(video_geoloaction_url)
            st.markdown(
                """我们的期望：\n
回答视频中的以下问题：
- 这个视频是关于什么的？
- 你怎么知道是哪个城市？
- 这是哪条街？
- 最近的十字路口是什么？
            """
            )
            prompt = """仅使用视频回答以下问题：

- 这个视频是关于什么的？
- 你怎么知道是哪个城市？
- 这是哪条街？
- 最近的十字路口是什么？

以表格形式回答以下问题，问题和答案作为列。
            """
            tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
            video_geoloaction_description = st.button(
                "生成", key="video_geoloaction_description"
            )
            with tab1:
                if video_geoloaction_description and prompt:
                    with st.spinner("使用 Gemini 生成位置标签..."):
                        response = get_gemini_pro_vision_response(
                            st.session_state.multimodal_model_pro,
                            [prompt, video_geoloaction_img],
                        )
                        placeholder = st.empty()
                        # st.write(response)
                        view_stream_response(response, placeholder)
                        st.markdown("\n\n\n")
            with tab2:
                st.write("使用的提示词：")
                st.write(prompt, "\n", "{video_data}")
            with tab3:
                st.write("使用的参数：")
                st.write(gemini_pro_vision_generation_config)


# region 示例

with st.expander(":bulb: 使用场景..."):
    st.markdown(
        """##### 使用场景

Gemini Pro Vision 非常适合各种多模态用例，包括但不限于下表中所述的用例：

| 使用场景 | 说明 |备注|
| --- | --- |--- |
| 信息搜寻 | 将世界知识与从图片和视频中提取的信息融合。 ||
| 对象识别 | 回答与对图片和视频中的对象进行精细识别相关的问题。 ||
| 数字内容理解 | 从信息图、图表、数字、表格和网页等内容中提取信息，回答问题。 ||
| 生成结构化内容 | 根据提供的提示说明，以 HTML 和 JSON 等格式生成响应。 ||
| 字幕/说明 | 生成具有不同细节级别的图片和视频说明。 ||
| 推断 | 对图片中未显示的内容或视频播放前后的情况进行猜测。 ||          
| 辅助答题 | 对图片中问题进行解答。 |最好提交单个问题。如果图片中含有复杂的公式，效果欠佳。|           
"""
    )

with st.expander(":frame_with_picture: 图片最佳做法..."):
    st.markdown(
        """
##### 图片最佳做法

在提示中使用图片时，请遵循以下建议以获得最佳效果：

- 包含一张图片的提示往往能产生更好的结果。
- 如果提示包含单张图片，则将图片放在文本提示之前可能会得到更好的结果。
- 如果提示中有多个图片，并且您希望稍后在提示中引用这些图片，或者希望模型在模型响应中引用这些图片，则在图片之前为每张图片提供索引会有所帮助。对索引使用`a` `b` `c` 或 `image 1` `image 2` `image 3`。以下示例展示了如何在提示中使用已编入索引的图片：

```
image 1 <piano_recital.jpeg>
image 2 <family_dinner.jpeg>
image 3 <coffee_shop.jpeg>

Write a blogpost about my day using image 1 and image 2. Then, give me ideas
for tomorrow based on image 3.
```
- 图片分辨率越高，效果就越好。
- 在提示中添加一些示例。
- 将图片旋转到正确的方向，然后再将其添加到提示中。
"""
    )

with st.expander(":warning: `Gemini`的当前限制..."):
    st.markdown(
        """##### `Gemini`的当前限制

虽然强大，但 Gemini 存在局限性。它在图片、长视频和复杂的指令等方面难以确定精确的对象位置。不适用于医疗用途或聊天机器人。

| 限制 | 说明 |
| --- | --- |
| 空间推理 | 难以对图片进行精确的对象/文本定位。它对理解旋转图片的准确率可能较低。 |
| 计数 | 只能提供对象数量的粗略近似值，尤其是对于模糊的对象。 |
| 理解较长的视频 | 可支持视频作为单独的模态（与仅处理单张图片不同）。但是，模型从一组非连续的图片帧中接收信息，而不是从连续视频本身（不接收音频）接收。Gemini 也不会提取超过视频 2 分钟之外的任何信息。如需提升包含密集内容的视频的性能，请缩短视频，以便模型捕获更多视频内容。 |
| 按照复杂的说明操作 | 难以处理需要多个推理步骤的任务。可以考虑分解说明或提供镜头较少的示例，以获得更好的指导。 |
| 幻觉 | 有时，推断内容可能超出图片/视频中的实际位置，或生成不正确的内容以进行广泛文本解析。降低温度或要求缩短说明有助于缓解这种情况。 |
| 医疗用途 | 不适合解读医学图片（例如 X 光片和 CT 扫描），或不适合提供医学建议。 |
| 多轮（多模态）聊天 | 未经训练，无法使用聊天机器人功能或以聊天语气回答问题，并且在多轮对话中表现不佳。 |
"""
    )

with st.expander(":memo: 多模态提示最佳实践..."):
    st.markdown(
        """
##### 多模态提示最佳实践
                
您可以按照以下最佳实践改进多模态提示：

###### 提示设计基础知识
- **说明要具体**：写出清晰简明的说明，尽量避免误解。
- **在提示中添加几个示例**：使用切实可行的少样本示例来说明您想实现的目标。
- **逐步细分**：将复杂的任务划分为多个易于管理的子目标，引导模型完成整个过程。
- **指定输出格式**：在提示中，要求输出采用您想要的格式，例如 Markdown、JSON、HTML 等。
- **对于单个图片的提示，首先放置图片**：虽然 Gemini 可以按任意顺序处理图片和文字输入，但对于包含单张图片的提示，如果将图片（或视频）放在文本提示前面，效果可能会更好。 不过，如果提示要求图片与文本高度交错才有意义，请使用最自然的顺序。

###### 排查多模态提示问题
                
- **如果模型没有从图片的相关部分绘制信息**：添加提示，说明您希望提示从图片的哪些方面提取信息。
- **如果模型输出过于宽泛（未针对图片/视频输入量身打造**）： 在提示开始时，尝试让模型描述图片或视频，然后再提供任务说明，或者尝试让模型参考图片中的内容。
- **排查哪个部分出错**：要求模型描述图片，或要求模型解释原因，从而衡量模型对图片的初步理解。
- **如果提示会生成幻觉内容**：请尝试调低温度设置，或要求模型提供较短的说明，以降低推断出其他细节的可能性。
- **调整采样参数**：尝试不同的温度设置和 Top-k 选择，以调整模型的创造力。
"""
    )

with st.expander(":blue_book: 提示设计基础知识..."):
    st.markdown(
        """
##### 提示设计基础知识

本部分扩展了上一部分中列出的最佳实践。
注意：以下 Gemini 示例的模型结果可能因运行而异。

###### 说明应当明确具体

清晰、详尽的提示效果最好。如果您有特定的输出，最好在提示中包含该要求，以确保获得所需的输出。

有时，提示的编写者可能看上去很清楚，但实际上并没有明确。如需自定义模型行为，请考虑对您的提示的误解，并确保您提供的说明简短具体。请尽量避免误解。

对于此机场登机牌图片，要求模型仅“描述此图片”可以生成一般描述。如果您需要模型解析图片中的时间和城市，您可以直接在提示中包含该请求。
"""
    )
    cols_1 = st.columns(2)
    cols_1[0].markdown("**提示**")
    cols_1[1].markdown("**模型响应**")
    cols_1[0].image(
        PImage.open(IMAGE_DIR / "timetable.png"),
        use_column_width=True,
    )
    cols_1[1].text("此图片显示了机场到达和出发信息面板。")
    cols_1[0].text("描述此图片。")

    st.divider()

    cols_2 = st.columns(2)
    cols_2[0].markdown(":blue[更新后的提示]")
    cols_2[1].markdown(":rainbow[改进了的响应]")
    cols_2[0].image(
        PImage.open(IMAGE_DIR / "timetable.png"),
        use_column_width=True,
    )
    cols_2[1].markdown(
        """
- 10:50 莫斯科
- 11:05 爱丁堡
- 11:05 伦敦
- 11:10 布加勒斯特
- 11:30 基辅
- 11:35 都柏林
- 11:45 东米德兰兹
- 12:15 索非亚
- 12:30 伦敦
- 12:30 纽卡斯尔
- 12:40 圣彼得堡
- 12:40 伦敦
- 12:45 曼彻斯特
"""
    )
    cols_2[0].text("将下图中显示的机场面板中的时间和城市解析为列表。")

    st.divider()

    st.markdown(
        """
###### 添加一些示例

`Gemini`模型可以接受多个输入，以用作示例来了解您想要的输出。添加这些样本有助于模型识别模式，并将指定图片和响应之间的关系应用于新样本。这也称为少量样本学习。

在以下示例中，初始输出以句子形式编写，并且还包含国家/地区（巴西）。假设您需要不同格式或样式的输出，并且只希望输入城市而不是国家/地区。在提示中添加少样本样本可以引导模型以您想要的方式响应。"""
    )

    cols_3 = st.columns(2)
    cols_3[0].markdown("**提示**")
    cols_3[1].markdown("**模型响应**")
    cols_3[0].image(
        PImage.open(IMAGE_DIR / "redeemer.png"),
        use_column_width=True,
    )
    cols_3[1].text("地标是巴西里约热内卢的基督救世主雕像。")
    cols_3[0].text("确定城市和地标。")

    st.divider()

    cols_4 = st.columns(2)
    cols_4[0].markdown(":blue[更新后的提示]")
    cols_4[1].markdown(":rainbow[改进了的响应]")
    cols_4[0].text("确定城市和地标。")
    cols_4[0].image(
        PImage.open(IMAGE_DIR / "colosseum.png"),
        use_column_width=True,
    )
    cols_4[0].text("城市：罗马 ，地标：罗马斗兽场。")
    cols_4[0].image(
        PImage.open(IMAGE_DIR / "forbidden-city.png"),
        use_column_width=True,
    )
    cols_4[0].text("城市：北京，地标：紫禁城")
    cols_4[0].image(
        PImage.open(IMAGE_DIR / "redeemer.png"),
        use_column_width=True,
    )
    cols_4[1].markdown("""城市：里约热内卢，地标：基督救世主雕像""")

    st.divider()

    st.markdown(
        """
###### 分步解析

对于像需要视觉理解和推理这样的复杂任务，将任务拆分为更小、更简单的步骤会很有帮助。或者，如果你在提示中直接要求模型“一步步思考”，也可以有效地解决问题。"""
    )
    cols_5 = st.columns(2)
    cols_5[0].markdown("**提示**")
    cols_5[1].markdown("**模型响应**")
    cols_5[0].image(
        PImage.open(IMAGE_DIR / "toilet-paper.jpg"),
        use_column_width=True,
    )
    cols_5[1].text("您只剩下 3 卷了。")
    cols_5[0].text("我什么时候会用完卫生纸？")

    st.divider()

    cols_6 = st.columns(2)
    cols_6[0].markdown(":blue[更新后的提示]")
    cols_6[1].markdown(":rainbow[改进了的响应]")

    cols_6[0].image(
        PImage.open(IMAGE_DIR / "toilet-paper.jpg"),
        use_column_width=True,
    )
    cols_6[1].markdown(
        """
1. 这张图片中有 3 卷卫生纸。
2. 一个典型的人每天使用大约 20 张卫生纸。
3. 如果每卷包含 200 张纸，则每卷将持续约 10 天。
因此，3 卷将持续大约一个月。"""
    )
    cols_6[0].markdown(
        """
1. 首先，统计此图片中有多少个卫生纸卷。
2. 然后，确定一般人每天会使用多少卫生纸。
3. 计算这些卫生纸卷的使用时长。"""
    )

    st.markdown("""数学题或其他类型的文字题非常适合要求模型分步思考。""")

    cols_7 = st.columns(2)
    cols_7[0].markdown("**提示**")
    cols_7[1].markdown("**模型响应**")
    cols_7[0].image(
        PImage.open(IMAGE_DIR / "math.jpg"),
        use_column_width=True,
    )
    cols_7[1].text("-135")
    cols_7[0].text("序列中的第 4 项是什么？")

    st.markdown("""模型的响应不正确。改进此问题的一些方法是，先让模型解析问题，然后再回答提示。""")
    st.divider()
    cols_8 = st.columns(2)
    cols_8[0].markdown(":blue[更新后的提示]")
    cols_8[1].markdown(":rainbow[改进了的响应]")

    cols_8[0].image(
        PImage.open(IMAGE_DIR / "math.jpg"),
        use_column_width=True,
    )
    cols_8[1].markdown(
        """
$$ b(n) = b(n-1) * (-3) $$

$$ b(1) = 15 $$

将 n = 4 代入公式：
$$ b(4) = b(4-1) * (-3) $$

$$ b(4) = b(3) * (-3) $$

我们不知道 b(3) 的值，因此将 n = 3 代入公式：
$$ b(3) = b(3-1) * (-3) $$

$$ b(3) = b(2) * (-3) $$

我们不知道 b(2) 的值，因此将 n = 2 代入公式：
$$ b(2) = b(2-1) * (-3) $$

$$ b(2) = b(1) * (-3) $$

我们知道 b(1) 的值是 15，所以代入公式：
$$ b(2) = 15 * (-3) $$

$$ b(2) = -45 $$

现在我们已经知道 b(2) 的值，可以将其代入 b(3) 的公式中：
$$ b(3) = b(2) * (-3) $$

$$ b(3) = -45 * (-3) $$

$$ b(3) = 135 $$

现在我们已经知道 b(3) 的值，将其代入公式 b(4)：
$$ b(4) = b(3) * (-3) $$

$$ b(4) = 135 * (-3) $$

$$ b(4) = -405 $$

因此，序列中的第四项是 -405。"""
    )
    cols_8[0].markdown(
        """
请先解析图片中的公式。
然后，根据公式回答“数列中的第 4 个项是什么？”。"""
    )

    st.markdown("""此模型回答是正确的 - 现在，为了简化回答，你可以要求模型逐步思考。""")
    st.divider()
    cols_9 = st.columns(2)
    cols_9[0].markdown(":blue[更新后的提示]")
    cols_9[1].markdown(":rainbow[改进了的响应]")

    cols_9[0].image(
        PImage.open(IMAGE_DIR / "math.jpg"),
        use_column_width=True,
    )
    cols_9[0].markdown("序列中的第 4 项是什么？**循序渐进**地思考。")
    cols_9[1].markdown(
        """
第一项是 15。

第二项是 $$ b(1) * (-3) = 15 * (-3) = -45 $$。

第三项是 $$ b(2) * (-3) = -45 * (-3) = 135 $$。

第四项是 $$ b(3) * (-3) = 135 * (-3) = -405 $$。"""
    )

    st.divider()

    st.markdown(
        """
###### 尝试指定输出格式
一个常见问题是，模型输出需要采用某种格式（例如`Markdown`、`JSON`、`HTML`），尤其是在模型输出需要由下游任务提取时。您可以尝试在提示中指示模型生成该格式的输出。以下是两个示例："""
    )

    cols_10 = st.columns(2)
    cols_10[0].markdown("**提示**")
    cols_10[1].markdown("**模型响应**")
    cols_10[0].image(
        PImage.open(IMAGE_DIR / "excel-example.png"),
        use_column_width=True,
    )
    cols_10[1].markdown(
        """
| 主题 | 状态 | 时间 | 开始日期 | 截止日期 |
| ------- | ------ | ----: | ---------: | ------: |
| 数学 | 完成 | 1.5 小时 | 2023 年 11 月 29 日 | 2023 年 12 月 1 日 |
| 地理位置 | 完成 | 30 分钟 | 2023 年 12 月 2 日 | 2023 年 12 月 4 日 |
| 物理 | 进行中 | 2 小时 | 2023 年 12 月 3 日 | 2023 年 12 月 5 日 |
| 生物学 | 未开始 | 6 小时 | 2016 年 11 月 2 日 | 2023 年 12 月 6 日 |"""
    )
    cols_10[0].text("将此图片中的表解析为 Markdown 格式")

    st.divider()
    cols_10 = st.columns(2)
    cols_10[0].markdown("**提示**")
    cols_10[1].markdown("**模型响应**")
    cols_10[0].image(
        PImage.open(IMAGE_DIR / "spanish-meal.png"),
        use_column_width=True,
    )
    cols_10[1].markdown(
        """
```json
```json```
{
"ingredients": [
"rice",
"shrimp",
"clams",
"mussels",
"peas",
"tomatoes",
"onions",
"garlic",
"olive oil",
"paprika",
"salt",
"pepper"
],
"type of cuisine": "Spanish",
"vegetarian": false                        
```
"""
    )
    cols_10[0].markdown(
        """
请提供以下所有属性的列表：
                        
食材、菜系类型、是否是素食（采用 JSON 格式）"""
    )

    st.divider()
    st.markdown(
        """
###### 首先将图片放在单图片提示中

虽然 Gemini 可以在提示中以任意顺序解读图片和文字，但将单个图片置于文字提示之前可以获得更好的结果。在以下示例中，您会注意到，在每个提示中，图片或视频都排在文本前面。
"""
    )

with st.expander(":mag: 排查多模态提示问题..."):
    st.markdown(
        """    
##### 排查多模态提示问题

如果您没有收到有用的响应，则可能需要对提示进行问题排查。您可以尝试以下这些策略。

###### 如果模型不是从图片的相关部分绘制信息
为了获得更具体的响应，您可以指出您希望提示从图片的哪些方面获取信息来作为响应。"""
    )

    cols_11 = st.columns(2)
    cols_11[0].markdown("**提示**")
    cols_11[1].markdown("**模型响应**")
    cols_11[0].image(
        PImage.open(IMAGE_DIR / "diapers.png"),
        use_column_width=True,
    )
    cols_11[1].text("这些尿片可以使用 198 天。")
    cols_11[0].text("这些尿片可供一个婴儿使用多少天？")

    st.divider()

    cols_12 = st.columns(2)
    cols_12[0].markdown(":blue[更新后的提示]")
    cols_12[1].markdown(":rainbow[改进了的响应]")
    cols_12[0].image(
        PImage.open(IMAGE_DIR / "diapers.png"),
        use_column_width=True,
    )
    cols_12[0].markdown(
        """这些尿片可以使用多长时间？

根据包装盒上显示的体重来确定儿童的年龄，并使用包装盒中尿布的总数。

将总数除以孩子每天穿尿布的数量。"""
    )
    cols_12[1].markdown(
        """包装盒中有 198 张尿片。包装盒上注明尿布适用于体重 22-37 磅的儿童。

此体重范围的平均儿童可能在 1 至 2 岁之间。

2 岁的孩子通常每天要换 6 片尿片，因此尿片的使用寿命约为 33 天 (198/6)。"""
    )

    st.markdown(
        """
###### 如果模型输出过于宽泛，并且未针对图片或视频输入量身打造

为了帮助模型定制其对图片的响应，在执行推理任务之前，请尝试让模型对图片进行描述。"""
    )

    cols_13 = st.columns(2)
    cols_13[0].markdown("**提示**")
    cols_13[1].markdown("**模型响应**")
    cols_13[0].image(
        PImage.open(IMAGE_DIR / "packing.jpg"),
        use_column_width=True,
    )
    cols_13[0].image(
        PImage.open(IMAGE_DIR / "mall.jpg"),
        use_column_width=True,
    )
    cols_13[0].image(
        PImage.open(IMAGE_DIR / "toilet-paper.jpg"),
        use_column_width=True,
    )
    cols_13[0].image(
        PImage.open(IMAGE_DIR / "ocean.jpg"),
        use_column_width=True,
    )
    cols_13[1].text("所有四张图片都是风景摄影的示例。")
    cols_13[0].text("这些图片有什么共同之处？")

    st.divider()

    cols_14 = st.columns(2)
    cols_14[0].markdown(":blue[更新后的提示]")
    cols_14[1].markdown(":rainbow[改进了的响应]")
    cols_14[0].image(
        PImage.open(IMAGE_DIR / "packing.jpg"),
        use_column_width=True,
    )
    cols_14[0].image(
        PImage.open(IMAGE_DIR / "mall.jpg"),
        use_column_width=True,
    )
    cols_14[0].image(
        PImage.open(IMAGE_DIR / "toilet-paper.jpg"),
        use_column_width=True,
    )
    cols_14[0].image(
        PImage.open(IMAGE_DIR / "ocean.jpg"),
        use_column_width=True,
    )
    cols_14[0].markdown("""首先，请详细描述每张图片中的内容。这些图片有什么共同之处？""")
    cols_14[1].markdown(
        """
第一张图片展示了一个人打包行李。第二张图片展示了购物中心内一个空旷的走廊。第三张图片展示了一卷卫生纸。第四张图片展示了暴风雨中的黑暗海浪。

这些图像的共同之处在于，它们都是极限空间的示例。边缘空间是指介于两个不同位置或场景之间的位置或场景。他们通常带有不确定性或不明确感。

第一张图片展示了此人在家中和出门旅行的间隙。第二张图片展示了两家商店之间的走廊。第三张图片是卫生纸，它可以代表浴室。浴室是介于私人领域和公共领域之间的过渡空间。在这个地方，我们无论是要进入还是离开外面的世界，都能做好充分的准备。

第四张图片展示了平静与风暴之间的大海。

私密空间既可能会令人兴奋，也会令人不安。它们可以是新的开始，也可以是终点。它们可以是反思之地，也可以是行动之地。"""
    )

    st.divider()

    st.markdown("""您还可以尝试明确要求模型引用图片中的内容。""")

    st.divider()

    cols_15 = st.columns(2)
    cols_15[0].markdown(":blue[更新后的提示]")
    cols_15[1].markdown(":rainbow[改进了的响应]")
    cols_15[0].image(
        PImage.open(IMAGE_DIR / "packing.jpg"),
        use_column_width=True,
    )
    cols_15[0].image(
        PImage.open(IMAGE_DIR / "mall.jpg"),
        use_column_width=True,
    )
    cols_15[0].image(
        PImage.open(IMAGE_DIR / "toilet-paper.jpg"),
        use_column_width=True,
    )
    cols_15[0].image(
        PImage.open(IMAGE_DIR / "ocean.jpg"),
        use_column_width=True,
    )
    cols_15[0].markdown("""这些图片有什么共同之处？请参阅回复中图片中的内容。""")
    cols_15[1].markdown(
        """
所有图片都与旅行相关。第一张图片展示一个人打包行李箱，第二张图片显示购物中心里空旷的走廊，第三张图片显示一叠厕纸，第四张图片显示的是暴风雨中的海浪。

这些图片都与旅行有关，因为它们是人们在旅行时需要或使用的 所有物品。第一张图片展示了一个人打包行李，也就是人们出门旅行时所做的一件事。第二张图片显示的是购物中心内的一个空廊，人们经常前往该购物场所购物。第三张图片展示了一叠厕纸，这是人们在旅行时经常使用的东西。第四张图片展示了黑暗风暴的海浪，这是人们在旅行时经常遇到的场景。"""
    )

    st.divider()

    st.markdown(
        """
同样的提示也适用于基于图片或视频的广告素材输出。在下面的兔子示例中，明确要求模型包含图片的各个方面可以提高输出。"""
    )

    cols_16 = st.columns(2)
    cols_16[0].markdown("**提示**")
    cols_16[1].markdown("**模型响应**")
    cols_16[0].image(
        PImage.open(IMAGE_DIR / "rabbit.jpg"),
        use_column_width=True,
    )
    cols_16[1].markdown(
        """
小兔子，好柔软的棕色，
                        
在田野中来回跳跃。
                        
你的耳朵好长，尾巴很小。
                        
你是它们中最可爱的生物。

你轻咬青草，绿意盎然，
                        
看到我就走开。
                        
但我永远是你的朋友，
                        
小兔子，直到最后。
"""
    )
    cols_16[0].text("你能围绕这张图片写首诗吗？")

    st.divider()
    cols_17 = st.columns(2)
    cols_17[0].markdown(":blue[更新后的提示]")
    cols_17[1].markdown(":rainbow[改进了的响应]")
    cols_17[0].image(
        PImage.open(IMAGE_DIR / "rabbit.jpg"),
        use_column_width=True,
    )
    cols_17[1].markdown(
        """
绿地上的小兔子，
                        
耳朵好长，好热烈。
                                         
你在那里看到了什么？
                        
在远处，你凝视的地方是什么？

是海洋蓝吗？
                        
在阳光下闪闪发光？
                        
或者是潺潺的海浪声。
                        
您喜欢的节奏？

小兔子，跟我说实话，
                        
什么事这么吸引你的注意力？
                        
是微风吹拂，
                        
还是海鸥的哭泣？

也许这原来是广袤无边的，
                        
这个世界是那么大，小。
                        
一个地方，梦想可以漫游，
                        
冒险就在眼前。

小兔子，我想知道你梦寐以求的是什么。
                        
你坐在草地上，如此宁静。
                        
您是渴望探索深海，
                        
还是待在陆地上，尽情跃跃欲试？

无论是什么，小兔子，
                        
让奇迹之光始终燃烧起来。
                        
在梦想和愿望中，
                        
谎言世界在等着您创作。
"""
    )
    cols_17[0].text("你能为我写一首关于这张图片的描述性和戏剧性诗歌，并添加地点吗？")

    st.divider()

    st.markdown(
        """
###### 排查提示失败的那个部分

很难知道提示失败是否是因为模型一开始不理解图片，或者它是否理解图片但随后没有执行正确的推理步骤。

为区分这些原因，请让模型描述图片中的内容。

在下面的示例中，如果模型在响应时提供与茶搭配的零食（例如爆米花），则可以首先排查问题，以确定模型是否正确识别出图片包含茶。"""
    )

    cols_18 = st.columns(2)
    cols_18[0].markdown("**提示**")
    cols_18[1].markdown("**提示排查问题**")
    cols_18[0].image(
        PImage.open(IMAGE_DIR / "tea-set.png"),
        use_column_width=True,
    )
    cols_18[1].image(
        PImage.open(IMAGE_DIR / "tea-set.png"),
        use_column_width=True,
    )
    cols_18[0].markdown(
        """
哪种零食可以在 1 分钟内制作，配上这种美食？
"""
    )
    cols_18[1].text("描述此图片中的内容。")

    st.divider()

    st.markdown("""另一种策略是让模型解释其推理。这有助于你缩小原因的哪一部分（如果有的话）。""")

    cols_19 = st.columns(2)
    cols_19[0].markdown("**提示**")
    cols_19[1].markdown("**提示排查问题**")
    cols_19[0].image(
        PImage.open(IMAGE_DIR / "tea-set.png"),
        use_column_width=True,
    )
    cols_19[1].image(
        PImage.open(IMAGE_DIR / "tea-set.png"),
        use_column_width=True,
    )
    cols_19[0].markdown(
        """
哪种零食可以在 1 分钟内制作，配上这种美食？
"""
    )
    cols_19[1].text("哪种零食可以在 1 分钟内制作，配上这种美食？请说明原因。")

    st.markdown(
        """\
###### 调整采样参数

在每个请求中，您不仅需要向模型发送多模态提示，还要向模型发送一组采样参数。对于不同的参数值，模型会生成不同的结果。尝试使用不同的参数来获得任务的最佳值。最常调整的参数如下：

- 温度
- Top-P
- Top-K

`温度`

温度用于在响应生成过程中进行采样，这发生在应用了`Top-P`和`Top-K`时。温度可以控制词元选择的随机性。较低的温度有利于需要更具确定性、更少开放性或创造性回答的提示，而较高的温度可以带来更具多样性或创造性的结果。温度为 0 表示确定性，即始终选择概率最高的回答。

对于大多数应用场景，不妨先试着将温度设为 0.4。如果您需要更具创意的结果，请尝试调高温度。如果您观察到明显的幻觉，请尝试调低温度。

`Top-K`

`Top-K`可更改模型选择输出词元的方式。如果 `Top-K`设为 1，表示下一个所选词元是模型词汇表的所有词元中概率最高的词元（也称为贪心解码）。如果 `Top-K`设为 3，则表示系统将从 3 个概率最高的词元（通过温度确定）中选择下一个词元。

在每个词元选择步中，系统都会对概率最高的 `Top-K`词元进行采样。然后，系统会根据 Top-P 进一步过滤词元，并使用温度采样选择最终的词元。

指定较低的值可获得随机程度较低的回答，指定较高的值可获得随机程度较高的回答。 `Top-K`的默认值为 32。

`Top-P`

`Top-P`可更改模型选择输出词元的方式。系统会按照概率从最高（见`Top-K`）到最低的顺序选择词元，直到所选词元的概率总和等于 `Top-P`的值。例如，如果词元 A、B 和 C 的概率分别为 0.6、0.3 和 0.1，并且`Top-P`的值为 0.9，则模型将选择 A 或 B 作为下一个词元（通过温度确定），并会排除 C 作为候选词元。

指定较低的值可获得随机程度较低的回答，指定较高的值可获得随机程度较高的回答。`Top-P`的默认值为 1.0。
"""
    )

# endregion
