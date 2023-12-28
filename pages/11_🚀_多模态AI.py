import base64
import mimetypes
import time
from pathlib import Path

import streamlit as st
import vertexai
from PIL import Image

# from vertexai.preview.generative_models import GenerativeModel
from vertexai.preview.generative_models import Image as GImage
from vertexai.preview.generative_models import Part

from mypylib.google_gemini import NORMAL_SAFETY_SETTINGS
from mypylib.st_utils import (
    authenticate_and_configure_services,
    check_and_force_logout,
    load_model,
)

# region 页面设置

CURRENT_CWD: Path = Path(__file__).parent.parent
IMAGE_DIR: Path = CURRENT_CWD / "resource/multimodal"


st.set_page_config(
    page_title="多模态AI",
    page_icon=":rocket:",
    layout="wide",
)

authenticate_and_configure_services()

if "multimodal_examples_pair" not in st.session_state:
    st.session_state["multimodal_examples_pair"] = []

if "current_token_count" not in st.session_state:
    st.session_state["current_token_count"] = 0

if "total_token_count" not in st.session_state:
    st.session_state["total_token_count"] = 0

if "user_prompt" not in st.session_state:
    st.session_state["user_prompt"] = ""

if st.session_state.get("clear_prompt"):
    st.session_state["user_prompt"] = ""

# endregion

# region 边栏

st.sidebar.markdown(
    """:rainbow[运行设置]\n
:dotted_six-pointed_star: 模型：gemini-pro-vision            
"""
)
st.sidebar.slider(
    "词元限制",
    key="max_output_tokens",
    min_value=32,
    max_value=4096,
    value=4096,
    step=32,
    help="""词元限制决定了一条提示的最大文本输出量。词元约为 4 个字符。默认值为 4096""",
)
# 生成参数
st.sidebar.slider(
    "温度",
    min_value=0.00,
    max_value=1.0,
    key="temperature",
    value=0.0,
    step=0.1,
    help="温度可以控制词元选择的随机性。较低的温度适合希望获得真实或正确回复的提示，而较高的温度可能会引发更加多样化或意想不到的结果。如果温度为 0，系统始终会选择概率最高的词元。对于大多数应用场景，不妨先试着将温度设为 0.2。",
)

st.sidebar.slider(
    "Top K",
    key="top_k",
    min_value=1,
    max_value=40,
    value=32,
    step=1,
    help="""Top-k 可更改模型选择输出词元的方式。
- 如果 Top-k 设为 1，表示所选词元是模型词汇表的所有词元中概率最高的词元（也称为贪心解码）。
- 如果 Top-k 设为 3，则表示系统将从 3 个概率最高的词元（通过温度确定）中选择下一个词元。
- Top-k 的默认值为 40。""",
)
st.sidebar.slider(
    "Top P",
    key="top_p",
    min_value=0.00,
    max_value=1.0,
    value=1.0,
    step=0.05,
    help="""Top-p 可更改模型选择输出词元的方式。系统会按照概率从最高到最低的顺序选择词元，直到所选词元的概率总和等于 Top-p 的值。
- 例如，如果词元 A、B 和 C 的概率分别是 0.3、0.2 和 0.1，并且 Top-p 的值为 0.5，则模型将选择 A 或 B 作为下一个词元（通过温度确定）。
- Top-p 的默认值为 0.8。""",
)

st.sidebar.text_input(
    "添加停止序列",
    key="stop_sequences",
    max_chars=64,
    help="停止序列是一连串字符（包括空格），如果模型中出现停止序列，则会停止生成回复。该序列不包含在回复中。您最多可以添加五个停止序列。",
)


st.sidebar.info("对于 Gemini 模型，一个令牌约相当于 4 个字符。100 个词元约为 60-80 个英语单词。", icon="✨")
sidebar_status = st.sidebar.empty()
sidebar_status.markdown(
    f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{st.session_state.total_token_count}"
)

# endregion

# region 认证及强制退出


check_and_force_logout(sidebar_status)

# endregion


def _process_media(uploaded_file):
    # 用文件扩展名称形成 MIME 类型
    mime_type = mimetypes.guess_type(uploaded_file.name)[0]
    st.image(uploaded_file)
    p = Part.from_data(
        data=uploaded_file.getvalue(), mime_type=mime_type
    )
    return p


def _process_image_and_prompt(uploaded_files, prompt):
    contents = []
    separator = "<>"
    if separator not in prompt:
        # 如果没有分隔符，代表没有示例
        for mf in uploaded_files:
            contents.append(_process_media(mf))
        contents.append(prompt)
        return contents
    ps = [p.strip() for p in prompt.split(separator)]
    msg = f"错误：多媒体文件的数量应等于提示的数量加1。请检查你的输入并重试。"
    if len(uploaded_files) != len(ps) + 1:
        st.error(msg)
        st.stop()
    # To read file as bytes:
    media_parts = [_process_media(m) for m in uploaded_files]
    for m, p in zip(media_parts[:-1], ps):
        contents.append(m)
        contents.append(p)
    contents.append(media_parts[-1])
    return contents


def generate_content_from_files_and_prompt(uploaded_files, prompt, response_container):
    try:
        contents = _process_image_and_prompt(uploaded_files, prompt)
    except Exception as e:
        st.error(f"处理多媒体文件时出错：{e}")
        return
    model = load_model("gemini-pro-vision")
    generation_config = {
        "temperature": st.session_state["temperature"],
        "top_p": st.session_state["top_p"],
        "top_k": st.session_state["top_k"],
        "max_output_tokens": st.session_state["max_output_tokens"],
    }
    responses = model.generate_content(
        contents,
        generation_config=generation_config,
        safety_settings=NORMAL_SAFETY_SETTINGS,
        stream=True,
    )

    col1, col2 = response_container.columns(2)
    for m in uploaded_files:
        mime_type = mimetypes.guess_type(m.name)[0]
        if mime_type.startswith("image"):
            col1.image(m, use_column_width=True)
        elif mime_type.startswith("video"):
            col1.video(m)

    full_response = ""
    message_placeholder = col2.empty()
    for chunk in responses:
        full_response += chunk.text
        time.sleep(0.05)
        # Add a blinking cursor to simulate typing
        message_placeholder.markdown(full_response + "▌")

    message_placeholder.markdown(full_response)
    # 令牌数 TODO:需要考虑多媒体的令牌数
    st.session_state.current_token_count = model.count_tokens(
        prompt + full_response
    ).total_tokens
    st.session_state.total_token_count += st.session_state.current_token_count
    sidebar_status.markdown(
        f"当前令牌数：{st.session_state.current_token_count}，累计令牌数：{st.session_state.total_token_count}"
    )


# region 主页面
st.markdown(
    """#### :rocket: :rainbow[多模态AI]

您可以向`Gemini`模型发送多模态提示信息。支持的模态包括文字、图片和视频。
"""
)

uploaded_files = st.file_uploader(
    "插入多媒体文件【点击`Browse files`按钮，从本地上传文件】",
    accept_multiple_files=True,
    type=["png", "jpg", "mkv", "mov", "mp4", "webm"],
    help="""
支持的格式
- 图片：PNG、JPG
- 视频：
    - 您可以上传视频，支持以下格式：MKV、MOV、MP4、WEBM（最大 7MB）
    - 该模型将分析长达 2 分钟的视频。 请注意，它将处理从视频中获取的一组不连续的图像帧。
""",
)

prompt = st.text_area(
    "您的提示词",
    key="user_prompt_key",
    value=st.session_state.get("user_prompt", ""),
    placeholder="请输入关于多媒体的提示词，例如：'描述这张风景图片'",
    max_chars=12288,
    height=300,
)
cols = st.columns([1, 1, 1, 1, 4])
add_btn = cols[0].button(
    ":heavy_plus_sign:",
    help="模型可以接受多个输入，以用作示例来了解您想要的输出。添加这些样本有助于模型识别模式，并将指定图片和响应之间的关系应用于新样本。这也称为少量样本学习。示例之间，添加'<>'符号用于分隔。",
)
del_btn = cols[1].button(":heavy_minus_sign:", help="删除提示词尾部的分隔符")
cls_btn = cols[2].button(":wastebasket:", help="清空提示词", key="clear_prompt")
submitted = cols[3].button("提交", help="如果含有示例响应，在多个响应之间，添加 '<>' 符号进行分隔。")

response_container = st.container()

if add_btn:
    st.session_state["user_prompt"] = prompt + "\n" + "<>"
    st.rerun()

if del_btn:
    st.session_state["user_prompt"] = prompt.rstrip("<>\n")
    st.rerun()

if submitted:
    if len(uploaded_files) == 0:
        st.error("请上传图片或视频")
        st.stop()
    if not prompt:
        st.error("请添加提示词")
        st.stop()
    generate_content_from_files_and_prompt(uploaded_files, prompt, response_container)


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
        Image.open(IMAGE_DIR / "timetable.png"),
        use_column_width=True,
    )
    cols_1[1].text("此图片显示了机场到达和出发信息面板。")
    cols_1[0].text("描述此图片。")

    st.divider()

    cols_2 = st.columns(2)
    cols_2[0].markdown(":blue[更新后的提示]")
    cols_2[1].markdown(":rainbow[改进了的响应]")
    cols_2[0].image(
        Image.open(IMAGE_DIR / "timetable.png"),
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
        Image.open(IMAGE_DIR / "redeemer.png"),
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
        Image.open(IMAGE_DIR / "colosseum.png"),
        use_column_width=True,
    )
    cols_4[0].text("城市：罗马 ，地标：罗马斗兽场。")
    cols_4[0].image(
        Image.open(IMAGE_DIR / "forbidden-city.png"),
        use_column_width=True,
    )
    cols_4[0].text("城市：北京，地标：紫禁城")
    cols_4[0].image(
        Image.open(IMAGE_DIR / "redeemer.png"),
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
        Image.open(IMAGE_DIR / "toilet-paper.jpg"),
        use_column_width=True,
    )
    cols_5[1].text("您只剩下 3 卷了。")
    cols_5[0].text("我什么时候会用完卫生纸？")

    st.divider()

    cols_6 = st.columns(2)
    cols_6[0].markdown(":blue[更新后的提示]")
    cols_6[1].markdown(":rainbow[改进了的响应]")

    cols_6[0].image(
        Image.open(IMAGE_DIR / "toilet-paper.jpg"),
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
        Image.open(IMAGE_DIR / "math.jpg"),
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
        Image.open(IMAGE_DIR / "math.jpg"),
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
        Image.open(IMAGE_DIR / "math.jpg"),
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
        Image.open(IMAGE_DIR / "excel-example.png"),
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
        Image.open(IMAGE_DIR / "spanish-meal.png"),
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
        Image.open(IMAGE_DIR / "diapers.png"),
        use_column_width=True,
    )
    cols_11[1].text("这些尿片可以使用 198 天。")
    cols_11[0].text("这些尿片可供一个婴儿使用多少天？")

    st.divider()

    cols_12 = st.columns(2)
    cols_12[0].markdown(":blue[更新后的提示]")
    cols_12[1].markdown(":rainbow[改进了的响应]")
    cols_12[0].image(
        Image.open(IMAGE_DIR / "diapers.png"),
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
        Image.open(IMAGE_DIR / "packing.jpg"),
        use_column_width=True,
    )
    cols_13[0].image(
        Image.open(IMAGE_DIR / "mall.jpg"),
        use_column_width=True,
    )
    cols_13[0].image(
        Image.open(IMAGE_DIR / "toilet-paper.jpg"),
        use_column_width=True,
    )
    cols_13[0].image(
        Image.open(IMAGE_DIR / "ocean.jpg"),
        use_column_width=True,
    )
    cols_13[1].text("所有四张图片都是风景摄影的示例。")
    cols_13[0].text("这些图片有什么共同之处？")

    st.divider()

    cols_14 = st.columns(2)
    cols_14[0].markdown(":blue[更新后的提示]")
    cols_14[1].markdown(":rainbow[改进了的响应]")
    cols_14[0].image(
        Image.open(IMAGE_DIR / "packing.jpg"),
        use_column_width=True,
    )
    cols_14[0].image(
        Image.open(IMAGE_DIR / "mall.jpg"),
        use_column_width=True,
    )
    cols_14[0].image(
        Image.open(IMAGE_DIR / "toilet-paper.jpg"),
        use_column_width=True,
    )
    cols_14[0].image(
        Image.open(IMAGE_DIR / "ocean.jpg"),
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
        Image.open(IMAGE_DIR / "packing.jpg"),
        use_column_width=True,
    )
    cols_15[0].image(
        Image.open(IMAGE_DIR / "mall.jpg"),
        use_column_width=True,
    )
    cols_15[0].image(
        Image.open(IMAGE_DIR / "toilet-paper.jpg"),
        use_column_width=True,
    )
    cols_15[0].image(
        Image.open(IMAGE_DIR / "ocean.jpg"),
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
        Image.open(IMAGE_DIR / "rabbit.jpg"),
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
        Image.open(IMAGE_DIR / "rabbit.jpg"),
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
        Image.open(IMAGE_DIR / "tea-set.png"),
        use_column_width=True,
    )
    cols_18[1].image(
        Image.open(IMAGE_DIR / "tea-set.png"),
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
        Image.open(IMAGE_DIR / "tea-set.png"),
        use_column_width=True,
    )
    cols_19[1].image(
        Image.open(IMAGE_DIR / "tea-set.png"),
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
