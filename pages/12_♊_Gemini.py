import os

import streamlit as st
import vertexai
from vertexai.generative_models._generative_models import ContentsType
from vertexai.preview.generative_models import (
    Content,
    GenerationConfig,
    GenerationResponse,
    GenerativeModel,
    Image,
    Part,
)
from mypylib.ai_utils import view_stream_response
from mypylib.google_cloud_configuration import (
    DEFAULT_SAFETY_SETTINGS,
    vertexai_configure,
)
from mypylib.st_utils import authenticate_and_configure_services, load_vertex_model

vertexai_configure(st.secrets)


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
    return model.generate_content(
        prompt_list,
        generation_config=generation_config,
        safety_settings=DEFAULT_SAFETY_SETTINGS,
        stream=stream,
    )


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
        st.markdown(
            """Gemini 还可以提供视频中发生的情况的描述："""
        )
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
            vide_desc_description = st.button(
                "生成视频描述", key="vide_desc_description"
            )
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
                st.write(prompt, "\n", "{video_data}")
            with tab3:
                st.write("使用的参数：")
                st.write("默认参数")

    with video_tags:
        st.markdown(
            """Gemini can also extract tags throughout a video, as shown below:."""
        )
        video_tags_uri = "gs://github-repo/img/gemini/multimodality_usecases_overview/photography.mp4"
        video_tags_url = (
            "https://storage.googleapis.com/" + video_tags_uri.split("gs://")[1]
        )
        if video_tags_url:
            video_tags_img = Part.from_uri(video_tags_uri, mime_type="video/mp4")
            st.video(video_tags_url)
            st.write("Our expectation: Generate the tags for the video")
            prompt = """Answer the following questions using the video only:
                        1. What is in the video?
                        2. What objects are in the video?
                        3. What is the action in the video?
                        4. Provide 5 best tags for this video?
                        Give the answer in the table format with question and answer as columns.
            """
            tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
            video_tags_description = st.button(
                "Generate video tags", key="video_tags_description"
            )
            with tab1:
                if video_tags_description and prompt:
                    with st.spinner("Generating video description using Gemini..."):
                        response = get_gemini_pro_vision_response(
                            st.session_state.multimodal_model_pro,
                            [prompt, video_tags_img],
                        )
                        placeholder = st.empty()
                        # st.write(response)
                        view_stream_response(response, placeholder)
                        st.markdown("\n\n\n")
            with tab2:
                st.write("Prompt used:")
                st.write(prompt, "\n", "{video_data}")
    with video_highlights:
        st.markdown(
            """Below is another example of using Gemini to ask questions about objects, people or the context, as shown in the video about Pixel 8 below:"""
        )
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
            st.write("Our expectation: Generate the highlights for the video")
            prompt = """Answer the following questions using the video only:
What is the profession of the girl in this video?
Which all features of the phone are highlighted here?
Summarize the video in one paragraph.
Provide the answer in table format. 
            """
            tab1, tab2, tab3 = st.tabs(["模型响应", "提示词", "参数设置"])
            video_highlights_description = st.button(
                "Generate video highlights", key="video_highlights_description"
            )
            with tab1:
                if video_highlights_description and prompt:
                    with st.spinner("Generating video highlights using Gemini..."):
                        response = get_gemini_pro_vision_response(
                            st.session_state.multimodal_model_pro,
                            [prompt, video_highlights_img],
                        )
                        placeholder = st.empty()
                        # st.write(response)
                        view_stream_response(response, placeholder)
                        st.markdown("\n\n\n")
            with tab2:
                st.write("Prompt used:")
                st.write(prompt, "\n", "{video_data}")

    with video_geoloaction:
        st.markdown(
            """Even in short, detail-packed videos, Gemini can identify the locations."""
        )
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
                """Our expectation: \n
            Answer the following questions from the video:
                - What is this video about?
                - How do you know which city it is?
                - What street is this?
                - What is the nearest intersection?
            """
            )
            prompt = """Answer the following questions using the video only:
            What is this video about?
            How do you know which city it is?
            What street is this?
            What is the nearest intersection?
            Answer the following questions in a table format with question and answer as columns. 
            """
            tab1, tab2 = st.tabs(["Response", "Prompt"])
            video_geoloaction_description = st.button(
                "Generate", key="video_geoloaction_description"
            )
            with tab1:
                if video_geoloaction_description and prompt:
                    with st.spinner("Generating location tags using Gemini..."):
                        response = get_gemini_pro_vision_response(
                            st.session_state.multimodal_model_pro,
                            [prompt, video_geoloaction_img],
                        )
                        placeholder = st.empty()
                        # st.write(response)
                        view_stream_response(response, placeholder)
                        st.markdown("\n\n\n")
            with tab2:
                st.write("Prompt used:")
                st.write(prompt, "\n", "{video_data}")
