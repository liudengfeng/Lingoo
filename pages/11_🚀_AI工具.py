import base64
import time
from pathlib import Path

import google.generativeai as genai
import streamlit as st
import vertexai
from google.generativeai.types.generation_types import BlockedPromptException
from PIL import Image
from vertexai.preview.generative_models import GenerativeModel, Part

from mypylib.google_gemini import SAFETY_SETTINGS
from mypylib.st_helper import authenticate, check_and_force_logout

# region 页面设置

CURRENT_CWD: Path = Path(__file__).parent.parent
IMAGE_DIR: Path = CURRENT_CWD / "resource/multimodal"

st.set_page_config(
    page_title="AI 工具",
    page_icon="🚀",
    layout="wide",
)

if "multimodal_examples_pair" not in st.session_state:
    st.session_state["multimodal_examples_pair"] = []

if "current_token_count" not in st.session_state:
    st.session_state["current_token_count"] = 0

if "total_token_count" not in st.session_state:
    st.session_state["total_token_count"] = 0

# endregion

# region 边栏

st.sidebar.markdown(
    """:rainbow[运行设置]\n
🔯 模型：gemini-pro-vision            
"""
)
st.sidebar.slider(
    "词元限制",
    key="max_output_tokens",
    min_value=32,
    max_value=2048,
    value=1024,
    step=32,
    help="""词元限制决定了一条提示的最大文本输出量。词元约为 4 个字符。默认值为 2048。""",
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
    value=40,
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
    value=0.8,
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

user_examples = st.sidebar.file_uploader(
    "🖼️ 多媒体示例",
    key="image_examples",
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
ai_examples = st.sidebar.text_input(
    "🔯 模型响应",
    key="ai_response",
    placeholder="在多个响应之间，请添加 '<>' 符号进行分隔。注意，响应的数量应与图片示例的数量相同。",
    max_chars=2000,
)

sidebar_col1, sidebar_col2, sidebar_col3, sidebar_col4 = st.sidebar.columns(4)

sidebar_col1.button(
    "➕",
    # on_click=add_chat_examples,
    disabled=len(st.session_state["multimodal_examples_pair"]) >= 4,
    help="""聊天提示的示例是输入输出对的列表，它们演示给定输入的示例性模型输出。控制在4对以内。使用示例来自定义模型如何响应某些问题。
|用户示例|AI示例|
|:-|:-|
|火星有多少颗卫星？|火星有两个卫星，火卫一和火卫二。|
""",
)
sidebar_col2.button(
    "➖",
    # on_click=del_last_examples,
    disabled=len(st.session_state["multimodal_examples_pair"]) <= 0,
    help="删除最后一对示例",
)
sidebar_col3.button(
    "🗑️",
    key="clear_example",
    help="清除当前示例对",
)

if sidebar_col4.button("🔄", key="reset_btn", help="重新设置上下文、示例，开始新的对话"):
    st.session_state["multimodal_examples_pair"] = []
    # init_chat()

# with st.sidebar.expander("查看当前样例..."):
#     # if "chat_session" not in st.session_state:
#     #     init_chat()
#     num = len(st.session_state.multimodal_examples_pair) * 2
#     for his in st.session_state.chat_session.history[:num]:
#         st.write(f"**{his.role}**：{his.parts[0].text}")

st.sidebar.info("对于 Gemini 模型，一个令牌约相当于 4 个字符。100 个词元约为 60-80 个英语单词。", icon="✨")
sidebar_status = st.sidebar.empty()
# endregion

# region 认证及强制退出

authenticate(st)
check_and_force_logout(st, sidebar_status)


# endregion
def generate():
    model = GenerativeModel("gemini-pro-vision")
    responses = model.generate_content(
        [
            image1,
            """这是一道一元二次函数的考题，图中列出了函数的图形，开口向下，顶点大于0，并与x轴有二个交点。题目中所列四个结论，请分别检验，然后统计正确结论的数量。请详解解释解答过程。""",
        ],
        generation_config={
            "max_output_tokens": 2048,
            "temperature": 0,
            "top_p": 0.5,
            "top_k": 32,
        },
        stream=True,
    )

    for response in responses:
        st.markdown(response.candidates[0].content.parts[0].text)


image1 = Part.from_data(
    data=base64.b64decode(
        """iVBORw0KGgoAAAANSUhEUgAAAtQAAAEJCAYAAAC0ZbCcAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAFE5SURBVHhe7d1/fBx1nT/w18zs790kTZtwwUKlP4i2eFJbsR4/lnIVCP4679oDW5EradRycOLpWdrafhEL/RE9BUVbNdYKlUJNTj0VCuVHWeUhVVIiB+XMpaEKbUOTJk2a/b078/1jfmRm9kd+bJJumteTxzxodmd/zOzs7Gs+8/58RlAURQEREREREY2IaL+BiIiIiIiGjoGaiIiIiKgADNRERERERAVgoCYiIiIiKgADNRERERFRARioiYiIiIgKwEBNRERERFQABmoiIiIiogIwUBMRERERFYCBmoiIiIioAAzUREREREQFYKAmIiIiIioAAzURERERUQEYqImIiIiICsBATURERERUAAZqIiIiIqICMFATERERERWAgZqIiIiIqAAM1EREREREBWCgJiIiIiIqAAM1EREREVEBGKiJiIiIiArAQD3RdDShtnoeZlXPw6zq1djbYZ+BiIiIxlJn02rtd3geZtU1odM+A006DNQTzKGHjuCO1sNobz2M9j2zsHYDv8hERETjpwU/PLJa/R1uPYzG6o24q6nLPhNNMsUbqDuaUFtdj0P22+2a6weOEnNO1uc5VD8Pm5sBoAt767RW3o4m1GpHmZ1Nq1FbpF+OBWvWYIH+x/TZWBw6gjetswyiBZur9eU/28buvRyqN33+ptaDQ/W5WxMO1c/L8rl3YW9djvdoOVswhCnr66rPP6u+xX5HTgPb7xCNyvvUW2SynRVRP8dZps/Ssv4HmYa1LBm09ZflefNNtU1d1hamjMm2nM31tvWivm7m9qKtp6yfZws259ynaesw6+PG29h9L1UD24v+WZyLcu2DyKqzaXWRrZ/c3+0B87F+zXzjrwtnB3HgyFuWOQpTRPsD2+/H6O0XTPkrm6FmQLRgs31/fbYoo+pl5b6L5yozhzR9TnnshPqo5m1zlftesj7TycbPKbc2dlpvHI4TjcqtF89VZl68TWm236d0Ko+t+pzy2Ant/y81KreualROavc2bxt4b8WsedtcZea2l+03D0L9jOzr+2xo3ja3sM84h+Ztc5WZxufZqTy2yrye1L8zX/dl5T7TNmk4Yd02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"""
    ),
    mime_type="image/png",
)

# region 主页面
st.markdown("""#### 🚀 :rainbow[多模态工具]""")

with st.form(key="ai_tool_form"):
    uploaded_file = st.file_uploader(
        "插入多媒体文件",
        type=["png", "jpg", "mkv", "mov", "mp4", "webm"],
    )
    question = st.text_input(
        "您的提示",
        placeholder="看下面的图片，告诉我谁是建筑师",
        disabled=not uploaded_file,
    )
    if uploaded_file and question:
        st.info("Please add your Anthropic API key to continue.")
    submitted = st.form_submit_button("提交")

response_element = st.empty()


with st.expander("💡 使用场景..."):
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

with st.expander("🖼️ 图片最佳做法..."):
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

with st.expander("⚠️ `Gemini`的当前限制..."):
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

with st.expander("📝 多模态提示最佳实践..."):
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

with st.expander("📘 提示设计基础知识..."):
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


with st.expander("🔍 排查多模态提示问题..."):
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
    cols_16[1].markdown("""
小兔子，好柔软的棕色，
                        
在田野中来回跳跃。
                        
你的耳朵好长，尾巴很小。
                        
你是它们中最可爱的生物。

你轻咬青草，绿意盎然，
                        
看到我就走开。
                        
但我永远是你的朋友，
                        
小兔子，直到最后。
""")
    cols_16[0].text("你能围绕这张图片写首诗吗？")    

    st.divider()
    cols_17 = st.columns(2)
    cols_17[0].markdown(":blue[更新后的提示]")
    cols_17[1].markdown(":rainbow[改进了的响应]")
    cols_17[0].image(
        Image.open(IMAGE_DIR / "rabbit.jpg"),
        use_column_width=True,
    )
    cols_17[1].markdown("""
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
""")
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
    cols_18[0].markdown("""
哪种零食可以在 1 分钟内制作，配上这种美食？
""")
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
    cols_19[0].markdown("""
哪种零食可以在 1 分钟内制作，配上这种美食？
""")
    cols_19[1].text("哪种零食可以在 1 分钟内制作，配上这种美食？请说明原因。")    

    st.markdown(
        """
###### 调整采样参数

在每个请求中，您不仅需要向模型发送多模态提示，还要向模型发送一组采样参数。对于不同的参数值，模型会生成不同的结果。尝试使用不同的参数来获得任务的最佳值。最常调整的参数如下：

- 温度
- Top-P
- Top-K

####### 温度
温度用于在响应生成过程中进行采样，这发生在应用了 Top-P 和 Top-K 时。温度可以控制词元选择的随机性。较低的温度有利于需要更具确定性、更少开放性或创造性回答的提示，而较高的温度可以带来更具多样性或创造性的结果。温度为 0 表示确定性，即始终选择概率最高的回答。

对于大多数应用场景，不妨先试着将温度设为 0.4。如果您需要更具创意的结果，请尝试调高温度。如果您观察到明显的幻觉，请尝试调低温度。

####### Top-K

Top-K 可更改模型选择输出词元的方式。如果 Top-K 设为 1，表示下一个所选词元是模型词汇表的所有词元中概率最高的词元（也称为贪心解码）。如果 Top-K 设为 3，则表示系统将从 3 个概率最高的词元（通过温度确定）中选择下一个词元。

在每个词元选择步中，系统都会对概率最高的 Top-K 词元进行采样。然后，系统会根据 Top-P 进一步过滤词元，并使用温度采样选择最终的词元。

指定较低的值可获得随机程度较低的回答，指定较高的值可获得随机程度较高的回答。 Top-K 的默认值为 32。

####### Top-P

Top-P 可更改模型选择输出词元的方式。系统会按照概率从最高（见 Top-K）到最低的顺序选择词元，直到所选词元的概率总和等于 Top-P 的值。例如，如果词元 A、B 和 C 的概率分别为 0.6、0.3 和 0.1，并且 Top-P 的值为 0.9，则模型将选择 A 或 B 作为下一个词元（通过温度确定），并会排除 C 作为候选词元。

指定较低的值可获得随机程度较低的回答，指定较高的值可获得随机程度较高的回答。 Top-P 的默认值为 1.0。
""")
# endregion
