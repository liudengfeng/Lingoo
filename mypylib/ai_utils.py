import time


def view_stream_response(responses, placeholder):
    """
    Concatenates the text from the given responses and displays it in a placeholder.

    Args:
        responses (list): A list of response chunks.
        placeholder: The placeholder where the concatenated text will be displayed.
    """
    full_response = ""
    for chunk in responses:
        try:
            full_response += chunk.text
        except IndexError:
            # st.write(response)
            continue
        time.sleep(0.05)
        # Add a blinking cursor to simulate typing
        placeholder.markdown(full_response + "▌")
    placeholder.markdown(full_response)
