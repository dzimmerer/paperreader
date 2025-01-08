import threading
import random
import time

from TTS.api import TTS
import sounddevice as sd


import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
import dash_dangerously_set_inner_html
from dash.dependencies import Input, Output

from conver_html import get_html
from collections import deque

import logging


# tts = TTS("tts_models/en/vctk/vits")
tts = TTS("tts_models/en/jenny/jenny")


def incr_sentence_idx(div_idx, sentence_idx, div_ids_list, div_ids_dict):

    div_id = div_ids_list[div_idx]
    sentences = div_ids_dict[div_id]["sentences"]

    new_sentence_idx = sentence_idx + 1
    new_div_idx = div_idx
    if new_sentence_idx >= len(sentences):
        new_sentence_idx = 0
        new_div_idx += 1

    if div_idx >= len(div_ids_list):
        new_div_idx = div_idx

    return new_div_idx, new_sentence_idx


def decr_sentence_idx(div_idx, sentence_idx, div_ids_list, div_ids_dict):

    new_sentence_idx = sentence_idx - 1
    new_div_idx = div_idx
    if new_sentence_idx < 0:
        if new_div_idx > 0:
            new_div_idx -= 1

            div_id = div_ids_list[new_div_idx]
            sentences = div_ids_dict[div_id]["sentences"]

            new_sentence_idx = len(sentences) - 1

        else:
            new_div_idx = 0
            new_sentence_idx = 0

    return new_div_idx, new_sentence_idx


def incr_div_idx(div_idx, sentence_idx, div_ids_list, div_ids_dict):

    new_div_idx = div_idx + 1
    new_sentence_idx = 0

    if new_div_idx >= len(div_ids_list):
        new_div_idx = div_idx

    return new_div_idx, new_sentence_idx


def decr_div_idx(div_idx, sentence_idx, div_ids_list, div_ids_dict):

    new_div_idx = div_idx - 1
    new_sentence_idx = 0

    if new_div_idx < 0:
        new_div_idx = 0

    return new_div_idx, new_sentence_idx


def get_next_selected_content(div_ids_list, div_ids_dict, div_idx, sentence_idx):

    div_id = div_ids_list[div_idx]

    sentences = div_ids_dict[div_id]["sentences"]

    overflow = False
    sentence_idx += 1
    if sentence_idx >= len(sentences):
        sentence_idx = 0
        div_idx += 1
        overflow = True

    end = False
    if div_idx >= len(div_ids_list):
        end = True

    div_id = div_ids_list[div_idx]
    sentences = div_ids_dict[div_id]["sentences"]
    sec_title = div_ids_dict[div_id]["title"]

    # html_content = div_ids_dict[div_id]["html"]
    html_content = div_ids_dict[div_id]["highlighted_html"][sentence_idx]
    html_figure = div_ids_dict[div_id]["figure"]

    if len(sentences) < 3:
        sentences = sentences + [""] * (3 - len(sentences))

    if sentence_idx == 0:
        html_sentences = (
            f"<b>{sentences[sentence_idx]}</b>\n<br>{sentences[sentence_idx + 1]}\n{sentences[sentence_idx + 2]}\n"
        )
    elif sentence_idx == len(sentences) - 1:
        html_sentences = f"{sentences[sentence_idx-1]}\n<br><b>{sentences[sentence_idx]}</b>\n"
    else:
        html_sentences = (
            f"{sentences[sentence_idx-1]}\n<br><b>{sentences[sentence_idx]}</b>\n<br>{sentences[sentence_idx + 1]}\n"
        )

    return {
        "html_content": html_content,
        "html_figure": html_figure,
        "html_sentences": html_sentences,
        "sec_title": sec_title,
        "div_idx": div_idx,
        "sentence_idx": sentence_idx,
        "overflow": overflow,
        "end": end,
    }


def get_selected_content(div_ids_list, div_ids_dict, div_idx, sentence_idx):

    div_id = div_ids_list[div_idx]

    sentences = div_ids_dict[div_id]["sentences"]

    div_id = div_ids_list[div_idx]
    sentences = div_ids_dict[div_id]["sentences"]
    sec_title = div_ids_dict[div_id]["title"][:100]

    # html_content = div_ids_dict[div_id]["html"]
    html_content = div_ids_dict[div_id]["highlighted_html"][sentence_idx]
    html_figure = div_ids_dict[div_id]["figure"]

    if len(sentences) < 3:
        sentences = sentences + [""] * (3 - len(sentences))

    if sentence_idx == 0:
        html_sentences = (
            f"<b>{sentences[sentence_idx]}</b>\n<br>{sentences[sentence_idx + 1]}\n{sentences[sentence_idx + 2]}\n"
        )
    elif sentence_idx == len(sentences) - 1:
        html_sentences = f"{sentences[sentence_idx-1]}\n<br><b>{sentences[sentence_idx]}</b>\n"
    else:
        html_sentences = (
            f"{sentences[sentence_idx-1]}\n<br><b>{sentences[sentence_idx]}</b>\n<br>{sentences[sentence_idx + 1]}\n"
        )

    return {
        "html_content": html_content,
        "html_figure": html_figure,
        "html_sentences": html_sentences,
        "sec_title": sec_title,
        "div_idx": div_idx,
        "sentence_idx": sentence_idx,
    }


# Initialize the app
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css",
        "https://arxiv.org/static/browse/0.3.4/css/ar5iv.0.7.9.min.css",
        "https://arxiv.org/static/browse/0.3.4/css/ar5iv-fonts.0.7.9.min.css",
        "https://arxiv.org/static/browse/0.3.4/css/latexml_styles.css",
    ],
)

logging.getLogger("werkzeug").setLevel(logging.WARN)


# Example HTML content as strings
html_left = "<h3>Left Section</h3><p>This is the left section with some HTML content.</p>"
html_right = "<h3>Right Section</h3><p>This is the right section with some HTML content.</p>"
html_bottom = "<p>This is the bottom 10% section, rendered with HTML content.</p>"

div_ids_list, div_ids_dict = get_html()

div_idx = 0
sentence_idx = 0

current_reading_status = "READY"
current_play_state = "PAUSED"


div_id = div_ids_list[div_idx]

html_left = div_ids_dict[div_id]["html"]
html_right = div_ids_dict[div_id]["figure"]

sentences = div_ids_dict[div_id]["sentences"]
html_bottom = f"<b>{sentences[0]}</b>\n<br>{sentences[1]}\n<br>{sentences[2]}\n"

sec_title = div_ids_dict[div_id]["title"]

# Shared trigger variable for the callback
update_flag = False

wav_dict = {}


def thread_turn_sentence_to_audio(src_queue, tgt_queue):
    global wav_dict

    while True:
        # if src_queue:
        # s_queue_dict = src_queue.popleft()  # Pop a sentence from the queue

        next_div_idx = div_idx
        next_sentence_idx = sentence_idx

        print(f"Next div_idx: {next_div_idx}, Next sentence_idx: {next_sentence_idx}")

        next_div_id = div_ids_list[next_div_idx]

        # div_id = s_queue_dict["div_id"]
        # sentence = s_queue_dict["sentence"]
        # sentence_id = s_queue_dict["sentence_id"]

        while (next_div_id, next_sentence_idx) in wav_dict:
            next_div_idx, next_sentence_idx = incr_sentence_idx(
                next_div_idx, next_sentence_idx, div_ids_list, div_ids_dict
            )
            next_div_id = div_ids_list[next_div_idx]

        sentence = div_ids_dict[next_div_id]["sentences_spoken"][next_sentence_idx]

        print(f"Processing sentence: {sentence}")
        # time.sleep(1 + random.random() * 2)

        # wav = tts.tts(text="Hello world!", speaker_wav="my/cloning/audio.wav", language="en")
        wav = tts.tts(
            text=sentence,
            # language="en",
            split_sentences=True,
            # speaker="p229",
        )

        wav_dict[(next_div_id, next_sentence_idx)] = wav

        # tgt_queue.append({"div_id": div_id, "sentence_id": sentence_id, "wav": wav})


# Initialize a deque to act as the sentence queue
sentence_queue = deque()
wav_queue = deque()
next_queue = deque()


for div_id_ in div_ids_list:
    for s_id, sentence in enumerate(div_ids_dict[div_id_]["sentences_spoken"]):
        sentence_queue.append({"div_id": div_id_, "sentence": sentence, "sentence_id": s_id})


tts_thread = threading.Thread(target=thread_turn_sentence_to_audio, args=(sentence_queue, wav_queue), daemon=True)
tts_thread.start()


def async_highlight_trigger():
    """Runs a background process that waits for a random time and sets the update flag."""
    global update_flag, current_play_state, wav_queue, next_queue, current_reading_status, wav_dict

    next_keys = None

    while True:

        # if wav_queue:
        #     s_wav_dict = wav_queue.popleft()

        #     div_id = s_wav_dict["div_id"]
        #     sentence_id = s_wav_dict["sentence_id"]
        #     wav = s_wav_dict["wav"]

        #     wav_dict[(div_id, sentence_id)] = wav

        # Sleep for a random time (up to 3 seconds)
        # time.sleep(random.random() * 2)
        if next_queue:
            if not next_keys:
                next_keys = next_queue.popleft()
                print(f"Processing sentence: {next_keys}")
                # time.sleep(1 + random.random() * 2)

        if next_keys:

            if next_keys in wav_dict:
                sd.play(wav_dict[next_keys], blocking=True, samplerate=44000)
                update_flag = True
                current_reading_status = "READ_TEXT"
                # del wav_dict[next_keys]
                next_keys = None
            else:
                time.sleep(0.5)
                pass
                # print("Waiting for the audio to be generated...")
                # next_key_processing_dict = {
                #     "div_id": next_keys[0],
                #     "sentence": div_ids_dict[next_keys[0]]["sentences_spoken"][next_keys[1]],
                #     "sentence_id": next_keys[1],
                # }
                # sentence_queue.appendleft(next_key_processing_dict)
                # time.sleep(0.1)
        else:
            time.sleep(0.5)


# Start the background thread
trigger_thread = threading.Thread(target=async_highlight_trigger, daemon=True)
trigger_thread.start()


# Example function to add sentences to the queue
def add_sentence_to_queue(idx_tuple):
    next_queue.append(idx_tuple)
    print(f"Added sentence to queue: {idx_tuple}")


# Add some example sentences to the queue
# add_sentence_to_queue((div_id, sentence_idx))


app.layout = html.Div(
    [
        # Top section: split into two parts (60% left, 40% right)
        html.Div(
            [
                # Left section (60%)
                html.Div(
                    [
                        html.Div(
                            html.H2(
                                sec_title,
                            ),
                            id="pap_title",
                        ),
                        html.Div(
                            dash_dangerously_set_inner_html.DangerouslySetInnerHTML(html_left),
                            style={
                                "display": "inline-block",
                                "vertical-align": "top",
                                "padding": "10px",
                            },
                            id="pap_content",
                        ),
                        html.Div(
                            # "Controls",
                            [
                                html.Div(f"{div_idx}", id="inp_div_id", style={"width": "2rem"}),
                                html.Div(f"{sentence_idx}", id="inp_sentence_id", style={"width": "2rem"}),
                                html.Button("<<", id="button_div_bckwrd"),
                                html.Button("<", id="button_sent_bckwrd"),
                                html.Button("play", id="button_play"),
                                html.Button(">", id="button_sent_fwd"),
                                html.Button(">>", id="button_div_fwd"),
                            ],
                            style={
                                "display": "flex",
                                "justify-content": "space-between",
                                "padding": "10px",
                                "margin-bottom": "15vh",
                                "position": "fixed",
                                "bottom": "0",
                                "left": "0",
                            },
                            id="bottom_controls",
                        ),
                    ],
                    style={
                        "width": "60%",
                        "display": "inline-block",
                        "vertical-align": "top",
                        "padding": "10px",
                    },
                ),
                # Right section (40%)
                html.Div(
                    dash_dangerously_set_inner_html.DangerouslySetInnerHTML(html_right),
                    style={
                        "width": "40%",
                        "display": "inline-block",
                        "vertical-align": "top",
                        "overflow": "clip",
                        "padding": "10px",
                        "word-wrap": "break-word",
                    },
                    id="pap_figure",
                ),
            ],
            style={"height": "85vh"},
        ),  # Takes 90% of the screen height
        # Bottom section (10%)
        html.Div(
            dcc.Markdown(
                html_bottom,
                dangerously_allow_html=True,
                style={"font-size": "1.1em", "text-align": "center"},
                mathjax=True,
            ),
            style={"height": "15vh", "padding": "10px", "backgroundColor": "#f8f9fa"},
            id="pap_sentences",
        ),
        # Polling interval to update the content
        dcc.Interval(  # A minimal interval to poll for updates
            id="polling-content-interval", interval=200, n_intervals=0  # Milliseconds (0.1 seconds)
        ),
        dcc.Interval(  # A minimal interval to poll for updates
            id="polling-speech-interval", interval=200, n_intervals=0  # Milliseconds (0.1 seconds)
        ),
    ]
)


@app.callback(
    Input("polling-speech-interval", "n_intervals"),
)
def update_speech(_):
    global current_play_state, div_idx, sentence_idx, current_reading_status, update_flag

    if current_play_state == "PLAY":
        if current_reading_status == "READY":
            add_sentence_to_queue((div_ids_list[div_idx], sentence_idx))
            current_reading_status = "READING"
            update_flag = True
        elif current_reading_status == "READ_TEXT":
            div_idx, sentence_idx = incr_sentence_idx(div_idx, sentence_idx, div_ids_list, div_ids_dict)
            current_reading_status = "READY"
            # print("Reading next sentence...")

    return


@app.callback(
    Output("pap_title", "children"),
    Output("pap_content", "children"),
    Output("pap_figure", "children"),
    Output("pap_sentences", "children"),
    Output("inp_div_id", "children"),
    Output("inp_sentence_id", "children"),
    Input("polling-content-interval", "n_intervals"),
)
def update_content(_):
    global update_flag, div_idx, sentence_idx

    # Only proceed if the update_flag is True
    if not update_flag:
        raise dash.exceptions.PreventUpdate  # Prevent unnecessary updates

    # Reset the flag
    update_flag = False

    # Update the content here
    print("Updating content...", div_idx, sentence_idx)

    # Get the next selected content
    selected_content = get_selected_content(div_ids_list, div_ids_dict, div_idx, sentence_idx)

    sec_title = selected_content["sec_title"]

    # Update the indices
    div_idx = selected_content["div_idx"]
    sentence_idx = selected_content["sentence_idx"]

    # div_id = div_ids_list[div_idx]
    # add_sentence_to_queue((div_id, sentence_idx))

    html_content = selected_content["html_content"]
    html_figure = selected_content["html_figure"]
    html_sentences = selected_content["html_sentences"]

    sentences_update = dcc.Markdown(
        html_sentences, dangerously_allow_html=True, style={"font-size": "1.1em", "text-align": "center"}, mathjax=True
    )

    # if not selected_content["overflow"]:
    #     title_update = dash.no_update
    #     right_update = dash.no_update
    #     left_update = dash_dangerously_set_inner_html.DangerouslySetInnerHTML(html_content)
    # else:
    title_update = html.H2(sec_title)
    left_update = dash_dangerously_set_inner_html.DangerouslySetInnerHTML(html_content)
    right_update = dash_dangerously_set_inner_html.DangerouslySetInnerHTML(html_figure)

    # # Check if the end is reached
    # if selected_content["end"]:
    #     print("End of content reached.")

    #     raise dash.exceptions.PreventUpdate

    return title_update, left_update, right_update, sentences_update, f"{div_idx}", f"{sentence_idx}"

    # return html.Div(content)


@app.callback(
    Output("button_play", "children"),
    Input("button_play", "n_clicks"),
)
def toggle_play_pause(n_clicks):
    global current_play_state

    if n_clicks is None:
        raise dash.exceptions.PreventUpdate

    print(f"Play/Pause button clicked: {n_clicks}")

    if current_play_state == "PAUSED":
        current_play_state = "PLAY"
        return "pause"
    else:
        current_play_state = "PAUSED"
        return "play"


@app.callback(
    Output("inp_div_id", "children", allow_duplicate=True),
    Output("inp_sentence_id", "children", allow_duplicate=True),
    Input("button_div_bckwrd", "n_clicks"),
    prevent_initial_call=True,
)
def update_div_bckwrd(n_clicks_div_bckwrd):
    global div_idx, sentence_idx, div_ids_list, div_ids_dict, update_flag, next_queue

    if n_clicks_div_bckwrd is None:
        raise dash.exceptions.PreventUpdate

    div_idx, sentence_idx = decr_div_idx(div_idx, sentence_idx, div_ids_list, div_ids_dict)

    update_flag = True
    next_queue.clear()

    return f"{div_idx}", f"{sentence_idx}"


@app.callback(
    Output("inp_div_id", "children", allow_duplicate=True),
    Output("inp_sentence_id", "children", allow_duplicate=True),
    Input("button_sent_bckwrd", "n_clicks"),
    prevent_initial_call=True,
)
def update_sent_bckwrd(n_clicks_sent_bckwrd):
    global div_idx, sentence_idx, div_ids_list, div_ids_dict, update_flag, next_queue

    if n_clicks_sent_bckwrd is None:
        raise dash.exceptions.PreventUpdate

    div_idx, sentence_idx = decr_sentence_idx(div_idx, sentence_idx, div_ids_list, div_ids_dict)

    update_flag = True
    next_queue.clear()

    return f"{div_idx}", f"{sentence_idx}"


@app.callback(
    Output("inp_div_id", "children", allow_duplicate=True),
    Output("inp_sentence_id", "children", allow_duplicate=True),
    Input("button_sent_fwd", "n_clicks"),
    prevent_initial_call=True,
)
def update_sent_fwd(n_clicks_sent_fwd):
    global div_idx, sentence_idx, div_ids_list, div_ids_dict, update_flag, next_queue

    if n_clicks_sent_fwd is None:
        raise dash.exceptions.PreventUpdate

    div_idx, sentence_idx = incr_sentence_idx(div_idx, sentence_idx, div_ids_list, div_ids_dict)

    update_flag = True
    next_queue.clear()

    return f"{div_idx}", f"{sentence_idx}"


@app.callback(
    Output("inp_div_id", "children", allow_duplicate=True),
    Output("inp_sentence_id", "children", allow_duplicate=True),
    Input("button_div_fwd", "n_clicks"),
    prevent_initial_call=True,
)
def update_div_fwd(n_clicks_div_fwd):
    global div_idx, sentence_idx, div_ids_list, div_ids_dict, update_flag, next_queue

    if n_clicks_div_fwd is None:
        raise dash.exceptions.PreventUpdate

    div_idx, sentence_idx = incr_div_idx(div_idx, sentence_idx, div_ids_list, div_ids_dict)

    update_flag = True
    next_queue.clear()

    return f"{div_idx}", f"{sentence_idx}"


if __name__ == "__main__":
    app.run_server(debug=False)
