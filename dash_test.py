import threading
import random
import time

from TTS.api import TTS
import sounddevice as sd


import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
import dash_dangerously_set_inner_html
from dash.dependencies import Input, Output, State

from conver_html import get_html
from collections import deque

import logging


class ReadingStatus:
    def __init__(self):
        self.div_idx = 0
        self.sentence_idx = 0
        self.current_reading_status = "READY"
        self.current_play_state = "PAUSED"
        self.update_flag = False


def get_tts_model():
    tts = TTS("tts_models/en/jenny/jenny")

    return tts


def incr_sentence_idx(div_idx, sentence_idx, div_ids_list, div_ids_dict):

    div_id = div_ids_list[div_idx]
    sentences = div_ids_dict[div_id]["sentences"]

    new_sentence_idx = sentence_idx + 1
    new_div_idx = div_idx
    if new_sentence_idx >= len(sentences):
        new_sentence_idx = 0
        new_div_idx += 1

    if new_div_idx >= len(div_ids_list):
        return div_idx, new_sentence_idx

    while len(div_ids_dict[div_ids_list[new_div_idx]]["sentences"]) == 0:
        new_div_idx += 1
        if new_div_idx >= len(div_ids_list):
            break

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

    prev_html = div_ids_dict[div_id]["prev_html"]
    next_html = div_ids_dict[div_id]["next_html"]

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
        "prev_html": prev_html,
        "next_html": next_html,
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

    prev_html = div_ids_dict[div_id]["prev_html"]
    next_html = div_ids_dict[div_id]["next_html"]

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
        "prev_html": prev_html,
        "next_html": next_html,
    }


def thread_turn_sentence_to_audio(tts, wav_dict, div_ids_list, div_ids_dict, reading_status):

    while True:

        next_div_idx = reading_status.div_idx
        next_sentence_idx = reading_status.sentence_idx

        print(f"Next div_idx: {next_div_idx}, Next sentence_idx: {next_sentence_idx}")

        next_div_id = div_ids_list[next_div_idx]

        if next_div_id == "#end":
            time.sleep(1)
            continue

        # div_id = s_queue_dict["div_id"]
        # sentence = s_queue_dict["sentence"]
        # sentence_id = s_queue_dict["sentence_id"]

        while (next_div_id, next_sentence_idx) in wav_dict:
            next_div_idx, next_sentence_idx = incr_sentence_idx(
                next_div_idx, next_sentence_idx, div_ids_list, div_ids_dict
            )
            if next_div_idx >= len(div_ids_list):
                break
            next_div_id = div_ids_list[next_div_idx]

        try:
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

        except Exception:
            pass


def async_highlight_trigger(wav_dict, next_queue, reading_status):
    """Runs a background process that waits for a random time and sets the update flag."""

    next_keys = None

    while True:
        if next_queue:
            if not next_keys:
                next_keys = next_queue.popleft()
                print(f"Processing sentence: {next_keys}")

        if next_keys:
            if next_keys in wav_dict:
                sd.play(wav_dict[next_keys], blocking=True, samplerate=44000)
                reading_status.update_flag = True
                reading_status.current_reading_status = "READ_TEXT"
                del wav_dict[next_keys]
                next_keys = None
            else:
                time.sleep(0.5)
        else:
            time.sleep(0.5)


def set_app_layout(app, sec_title, html_left, html_right, html_bottom, prev_html, next_html):
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
                                style={"padding": "10px", "height": "10vh", "overflow": "hidden"},
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        dash_dangerously_set_inner_html.DangerouslySetInnerHTML(prev_html),
                                        id="prev_content",
                                        style={"display": "inline-block", "width": "55vw"},
                                    ),
                                    html.Div("", id="scroll_here"),
                                    html.Div(
                                        dash_dangerously_set_inner_html.DangerouslySetInnerHTML(html_left),
                                        id="pap_content",
                                        style={"display": "inline-block", "width": "55vw"},
                                    ),
                                    html.Div(
                                        dash_dangerously_set_inner_html.DangerouslySetInnerHTML(next_html),
                                        id="next_content",
                                        style={"display": "inline-block", "width": "55vw"},
                                    ),
                                ],
                                style={
                                    "display": "inline-block",
                                    "vertical-align": "top",
                                    "padding": "10px",
                                    "height": "75vh",
                                    "overflow": "scroll",
                                },
                            ),
                            html.Div(
                                # "Controls",
                                [
                                    html.Div("0", id="inp_div_id", style={"width": "2rem"}),
                                    html.Div("0", id="inp_sentence_id", style={"width": "2rem"}),
                                    html.Button("<<", id="button_div_bckwrd"),
                                    html.Button("<", id="button_sent_bckwrd"),
                                    html.Button("play", id="button_play"),
                                    html.Button(">", id="button_sent_fwd"),
                                    html.Button(">>", id="button_div_fwd"),
                                    html.Button("🔓", id="button_scroll", style={"margin-left": "1rem"}),
                                ],
                                style={
                                    "display": "flex",
                                    "justify-content": "space-between",
                                    "padding": "10px",
                                    "margin-bottom": "15vh",
                                    "position": "fixed",
                                    "bottom": "0",
                                    "left": "0",
                                    "background-color": "white",
                                    "z-index": "3000",
                                },
                                id="bottom_controls",
                            ),
                        ],
                        style={
                            "width": "59vw",
                            "display": "inline-block",
                            "vertical-align": "top",
                            "padding": "10px",
                            "height": "85vh",
                            "overflow": "wrap",
                        },
                    ),
                    # Right section (40%)
                    html.Div(
                        dash_dangerously_set_inner_html.DangerouslySetInnerHTML(html_right),
                        style={
                            "width": "39vw",
                            "display": "inline-block",
                            "vertical-align": "top",
                            # "overflow": "clip",
                            "padding": "10px",
                            "word-wrap": "break-word",
                            "height": "85vh",
                            "overflow": "scroll",
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
                    style={"font-size": "1.1em", "text-align": "center", "z-index": "2001"},
                    mathjax=True,
                ),
                style={"height": "15vh", "padding": "10px", "backgroundColor": "#f8f9fa", "z-index": "2000"},
                id="pap_sentences",
            ),
            # Polling interval to update the content
            dcc.Interval(  # A minimal interval to poll for updates
                id="polling-content-interval", interval=200, n_intervals=0  # Milliseconds (0.1 seconds)
            ),
            dcc.Interval(  # A minimal interval to poll for updates
                id="polling-speech-interval", interval=200, n_intervals=0  # Milliseconds (0.1 seconds)
            ),
            dcc.Store(
                id="scroll-enabled-store", storage_type="local", data=False
            ),  # Store scroll state in localStorage
        ]
    )


def add_button_callbacks(app, reading_status, next_queue, div_ids_list, div_ids_dict):
    """Add the callbacks for the buttons."""

    @app.callback(
        Output("button_play", "children"),
        Output("scroll-enabled-store", "data"),
        Input("button_play", "n_clicks"),
    )
    def toggle_play_pause(n_clicks):
        if n_clicks is None:
            raise dash.exceptions.PreventUpdate

        reading_status.update_flag = True
        next_queue.clear()

        if reading_status.current_play_state == "PAUSED":
            reading_status.current_play_state = "PLAY"
            reading_status.current_reading_status = "READY"
            return "pause", True
        else:
            sd.stop()
            reading_status.current_play_state = "PAUSED"
            return "play", False

    @app.callback(
        Output("inp_div_id", "children", allow_duplicate=True),
        Output("inp_sentence_id", "children", allow_duplicate=True),
        Input("button_div_bckwrd", "n_clicks"),
        prevent_initial_call=True,
    )
    def update_div_bckwrd(n_clicks_div_bckwrd):
        if n_clicks_div_bckwrd is None:
            raise dash.exceptions.PreventUpdate

        sd.stop()

        reading_status.div_idx, reading_status.sentence_idx = decr_div_idx(
            reading_status.div_idx, reading_status.sentence_idx, div_ids_list, div_ids_dict
        )

        reading_status.update_flag = True
        next_queue.clear()

        return f"{reading_status.div_idx}", f"{reading_status.sentence_idx}"

    @app.callback(
        Output("inp_div_id", "children", allow_duplicate=True),
        Output("inp_sentence_id", "children", allow_duplicate=True),
        Input("button_sent_bckwrd", "n_clicks"),
        prevent_initial_call=True,
    )
    def update_sent_bckwrd(n_clicks_sent_bckwrd):
        if n_clicks_sent_bckwrd is None:
            raise dash.exceptions.PreventUpdate

        sd.stop()

        reading_status.div_idx, reading_status.sentence_idx = decr_sentence_idx(
            reading_status.div_idx, reading_status.sentence_idx, div_ids_list, div_ids_dict
        )

        reading_status.update_flag = True
        next_queue.clear()

        return f"{reading_status.div_idx}", f"{reading_status.sentence_idx}"

    @app.callback(
        Output("inp_div_id", "children", allow_duplicate=True),
        Output("inp_sentence_id", "children", allow_duplicate=True),
        Input("button_sent_fwd", "n_clicks"),
        prevent_initial_call=True,
    )
    def update_sent_fwd(n_clicks_sent_fwd):
        if n_clicks_sent_fwd is None:
            raise dash.exceptions.PreventUpdate

        sd.stop()

        reading_status.div_idx, reading_status.sentence_idx = incr_sentence_idx(
            reading_status.div_idx, reading_status.sentence_idx, div_ids_list, div_ids_dict
        )

        reading_status.update_flag = True
        next_queue.clear()

        return f"{reading_status.div_idx}", f"{reading_status.sentence_idx}"

    @app.callback(
        Output("inp_div_id", "children", allow_duplicate=True),
        Output("inp_sentence_id", "children", allow_duplicate=True),
        Input("button_div_fwd", "n_clicks"),
        prevent_initial_call=True,
    )
    def update_div_fwd(n_clicks_div_fwd):
        if n_clicks_div_fwd is None:
            raise dash.exceptions.PreventUpdate

        sd.stop()

        reading_status.div_idx, reading_status.sentence_idx = incr_div_idx(
            reading_status.div_idx, reading_status.sentence_idx, div_ids_list, div_ids_dict
        )

        reading_status.update_flag = True
        next_queue.clear()

        return f"{reading_status.div_idx}", f"{reading_status.sentence_idx}"

    @app.callback(
        Output("scroll-enabled-store", "data", allow_duplicate=True),
        Input("button_scroll", "n_clicks"),
        State("scroll-enabled-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_scroll(n_clicks, scroll_enabled):
        if n_clicks is None:
            raise dash.exceptions.PreventUpdate

        return not scroll_enabled


def add_speech_polling_callback(app, reading_status, next_queue, div_ids_list, div_ids_dict):
    """Add the callback for the speech polling."""

    def add_sentence_to_queue(idx_tuple):
        if idx_tuple[0] == "#end":
            return
        next_queue.append(idx_tuple)
        print(f"Added sentence to queue: {idx_tuple}")

    @app.callback(
        Input("polling-speech-interval", "n_intervals"),
    )
    def update_speech(_):
        if reading_status.current_play_state == "PLAY":
            if reading_status.current_reading_status == "READY":
                if div_ids_list[reading_status.div_idx] == "#end":
                    return
                add_sentence_to_queue((div_ids_list[reading_status.div_idx], reading_status.sentence_idx))
                reading_status.current_reading_status = "READING"
                reading_status.update_flag = True
            elif reading_status.current_reading_status == "READ_TEXT":
                reading_status.div_idx, reading_status.sentence_idx = incr_sentence_idx(
                    reading_status.div_idx, reading_status.sentence_idx, div_ids_list, div_ids_dict
                )
                reading_status.current_reading_status = "READY"

        return


def add_html_update_callback(app, div_ids_list, div_ids_dict, reading_status):
    """Add the callback for the html update."""

    @app.callback(
        Output("pap_title", "children"),
        Output("pap_content", "children"),
        Output("pap_figure", "children"),
        Output("pap_sentences", "children"),
        Output("inp_div_id", "children"),
        Output("inp_sentence_id", "children"),
        Output("prev_content", "children"),
        Output("next_content", "children"),
        Input("polling-content-interval", "n_intervals"),
    )
    def update_content(_):
        if not reading_status.update_flag:
            raise dash.exceptions.PreventUpdate

        reading_status.update_flag = False

        if div_ids_list[reading_status.div_idx] == "#end":
            return (
                html.H2(
                    "The end",
                ),
                dash.no_update,
                dash.no_update,
                dcc.Markdown(
                    "The end",
                    dangerously_allow_html=True,
                    style={"font-size": "1.1em", "text-align": "center"},
                    mathjax=True,
                ),
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update,
            )

        selected_content = get_selected_content(
            div_ids_list, div_ids_dict, reading_status.div_idx, reading_status.sentence_idx
        )

        sec_title = selected_content["sec_title"]

        reading_status.div_idx = selected_content["div_idx"]
        reading_status.sentence_idx = selected_content["sentence_idx"]

        html_content = selected_content["html_content"]
        html_figure = selected_content["html_figure"]
        html_sentences = selected_content["html_sentences"]

        sentences_update = dcc.Markdown(
            html_sentences,
            dangerously_allow_html=True,
            style={"font-size": "1.1em", "text-align": "center"},
            mathjax=True,
        )

        title_update = html.H2(sec_title)
        left_update = dash_dangerously_set_inner_html.DangerouslySetInnerHTML(html_content)
        right_update = dash_dangerously_set_inner_html.DangerouslySetInnerHTML(html_figure)

        prev_html = selected_content["prev_html"]
        next_html = selected_content["next_html"]

        prev_update = dash_dangerously_set_inner_html.DangerouslySetInnerHTML(prev_html)
        next_update = dash_dangerously_set_inner_html.DangerouslySetInnerHTML(next_html)

        return (
            title_update,
            left_update,
            right_update,
            sentences_update,
            f"{reading_status.div_idx}",
            f"{reading_status.sentence_idx}",
            prev_update,
            next_update,
        )


def init_app(url):

    print("1")

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

    # Get tts model
    tts = get_tts_model()

    # Set the logging level
    logging.getLogger("werkzeug").setLevel(logging.WARN)

    # Initialize the reading status and the sentence queue
    reading_status = ReadingStatus()

    next_queue = deque()
    wav_dict = {}

    # Shared trigger variable for the callback

    print("2")

    div_ids_list, div_ids_dict = get_html(url=url)

    print("2.10")

    div_id = div_ids_list[reading_status.div_idx]

    html_left = div_ids_dict[div_id]["html"]
    html_right = div_ids_dict[div_id]["figure"]

    sentences = div_ids_dict[div_id]["sentences"]
    html_bottom = f"<b>{sentences[0]}</b>\n<br>{sentences[1]}\n<br>{sentences[2]}\n"

    sec_title = div_ids_dict[div_id]["title"]

    prev_html = div_ids_dict[div_id]["prev_html"]
    next_html = div_ids_dict[div_id]["next_html"]

    set_app_layout(app, sec_title, html_left, html_right, html_bottom, prev_html, next_html)

    print("3")

    # Start the background thread
    tts_thread = threading.Thread(
        target=thread_turn_sentence_to_audio,
        args=(tts, wav_dict, div_ids_list, div_ids_dict, reading_status),
        daemon=True,
    )
    tts_thread.start()

    print("4")

    # Start the background thread
    trigger_thread = threading.Thread(
        target=async_highlight_trigger, args=(wav_dict, next_queue, reading_status), daemon=True
    )
    trigger_thread.start()

    add_speech_polling_callback(app, reading_status, next_queue, div_ids_list, div_ids_dict)
    add_html_update_callback(app, div_ids_list, div_ids_dict, reading_status)
    add_button_callbacks(app, reading_status, next_queue, div_ids_list, div_ids_dict)

    return app


if __name__ == "__main__":

    # url = "https://arxiv.org/html/2412.06787v2"
    url = "https://arxiv.org/html/2410.10812v1"

    app = init_app(url)

    app.run_server(debug=False)
