import re
import time
import requests
from bs4 import BeautifulSoup, NavigableString
from markdownify import markdownify as md
import markdown
from tqdm import tqdm

from mathtex2text import latex_to_speech_with_latexwalker


# # Custom function to convert LaTeX to spoken text
# def latex_to_spoken_text(latex_code):
#     try:
#         # Parse the LaTeX into a sympy expression
#         expression = sympify(latex_code, evaluate=False)
#         # Use sympy's string printer to create a more human-readable version
#         spoken_text = StrPrinter().doprint(expression)
#         return spoken_text
#     except Exception:
#         # If parsing fails, return the original LaTeX
#         return latex_code


# Step 1: Fetch the HTML content from the webpage

MIN_SENTENCE_LENGTH = 30
MAX_SENTENCE_LENGTH = 150


def split_into_sentences(text):
    # Split based on '.', '!', '?', and ensure boundaries are respected
    sentence_endings = re.compile(r"(?<!\b(?:e\.g|i\.e))([.!?])\s+")
    sentences = sentence_endings.split(text)
    # Recombine the sentences and punctuation
    sentences = ["".join(pair) for pair in zip(sentences[::2], sentences[1::2])]
    # Further split sentences longer than MAX_SENTENCE_LENGTH characters by ','
    final_sentences = []
    for sentence in sentences:
        if len(sentence) > 150:
            sub_sentences = sentence.split(",")
            for sub_sentence in sub_sentences:
                sub_sentence = sub_sentence + ","
                if len(sub_sentence) > MAX_SENTENCE_LENGTH:
                    # Split after the first " " after MAX_SENTENCE_LENGTH chars
                    split_index = sub_sentence.find(" ", MAX_SENTENCE_LENGTH)
                    if split_index != -1:
                        final_sentences.append(sub_sentence[:split_index].strip())
                        final_sentences.append(sub_sentence[split_index + 1 :].strip())
                    else:
                        final_sentences.append(sub_sentence.strip())
                else:
                    final_sentences.append(sub_sentence.strip())
        else:
            final_sentences.append(sentence.strip())
    return [s for s in final_sentences if s]


def split_text(text, min_length=MIN_SENTENCE_LENGTH, max_length=MAX_SENTENCE_LENGTH):
    # Step 1: Extract protected text and replace with placeholders
    protected_segments = re.findall(r"\$.*?\$", text)
    temp_text = re.sub(r"\$.*?\$", lambda match: f"@@{protected_segments.index(match.group())}@@", text)

    # Step 2: Split text into chunks
    words = temp_text.split()
    chunks = []
    current_chunk = ""
    current_length = 0

    for i, word in enumerate(words):
        if word == "##break##":
            # Split at the break point
            chunks.append(current_chunk.replace("##break##", "").strip())
            current_chunk = ""
            current_length = 0
        elif current_length + len(word) + 1 <= max_length:
            current_chunk += ("" if not current_chunk else " ") + word
            current_length += len(word) + 1
        else:
            # Check for natural breaking points if chunk length is beyond 2/3 of max_length
            if current_length >= (2 / 3) * max_length:
                # Find natural break within the chunk
                for break_point in [". ", ", ", ": ", "! ", "? "]:
                    last_break = current_chunk.rfind(break_point)
                    if last_break != -1 and last_break >= min_length:
                        # Split at the last breaking point
                        chunks.append(current_chunk[: last_break + 1].strip())
                        current_chunk = current_chunk[last_break + 2 :] + " " + word
                        current_length = len(current_chunk)
                        break
                else:
                    # No break point found, finalize the chunk
                    if current_length >= min_length:
                        chunks.append(current_chunk.strip())
                        current_chunk = word
                        current_length = len(word) + 1
            else:
                # If chunk is too short, extend it further
                current_chunk += " " + word
                current_length += len(word) + 1

    if current_chunk:
        chunks.append(current_chunk.strip())

    # Step 3: Restore protected text in the chunks
    restored_chunks = []
    for chunk in chunks:
        restored_chunk = re.sub(r"@@(\d+)@@", lambda match: protected_segments[int(match.group(1))], chunk)
        restored_chunks.append(restored_chunk)

    return restored_chunks


# Recursive function to process each element's text content
def process_element(soup, element, sentence_id=1):
    new_sentence_id = sentence_id
    # Iterate over children
    for child in element.contents:
        if isinstance(child, NavigableString):  # Text node
            sentences = split_into_sentences(child)
            if sentences:
                # Replace the text node with spans wrapping each sentence
                span_wrapped_sentences = [
                    soup.new_tag("span", **{"class": f"sentence_{new_sentence_id + i}"}) for i in range(len(sentences))
                ]
                for span, sentence in zip(span_wrapped_sentences, sentences):
                    span.string = sentence  # Set sentence inside span
                child.replace_with(*span_wrapped_sentences)  # Replace the text node
                new_sentence_id += len(sentences)
        elif child.name:  # If it's a tag, process recursively
            new_sentence_id = process_element(soup, child, new_sentence_id)
    return new_sentence_id


def mark_words_in_html(html: str, words: list, start_index: int) -> tuple:
    """
    Marks words in an HTML string with <mark> tags starting from a specific index.

    Args:
        html (str): The HTML string to search in.
        words (list): List of words to mark.
        start_index (int): The starting index in the HTML string.

    Returns:
        tuple: Updated HTML string with <mark> tags and the last index of the original string after the last word.
    """
    current_index = start_index
    last_position_in_original = start_index

    for word in words:
        # Find the first occurrence of the word after the current index
        position = html.find(word, current_index)
        while position != -1:
            # Check if the found word is within an HTML tag
            if html.rfind("<", current_index, position) > html.rfind(">", current_index, position):
                # Move the current index past the end of the tag
                current_index = html.find(">", position) + 1
                position = html.find(word, current_index)
            else:
                break
        if position == -1:
            # Word not found, skip to the next word
            continue

        position_increment = position - current_index

        # Update last position in the original string
        last_position_in_original += position_increment + len(word)

        # Add <mark> tags around the found word
        html = f"{html[:position]}<mark>{word}</mark>{html[position + len(word):]}"

        # Update current index to the end of the marked word in the modified string
        current_index = position + len("<mark>") + len(word) + len("</mark>")

    return html, last_position_in_original


def get_html(url):

    response = requests.get(url)

    if response.status_code == 200:
        html_content = response.content
    else:
        raise Exception(f"Failed to fetch the page. Status code: {response.status_code}")

    # Step 2: Parse the HTML using BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")

    # Step 3: Locate the "article" HTML tag
    article_tag = soup.find("article")
    if article_tag is None:
        raise Exception("No 'article' tag found in the HTML.")

    # # Step 4: Replace all math parts with their spoken text versions
    # for math_tag in article_tag.find_all("math"):
    #     alttext = math_tag.get("alttext", "[Math not found]")
    #     alttext = alttext.replace("\n", " ").replace("%", " ").strip()
    #     spoken_text = latex_to_speech_with_latexwalker(alttext)  # Convert LaTeX to spoken text
    #     cleaned_text = re.sub(r"\s+", " ", spoken_text).strip()
    #     math_tag.replace_with("$" + alttext + "$")  # Replace the math tag with the spoken text

    # Step 5: Add the URL prefix to all image sources
    for img_tag in article_tag.find_all("img"):
        src = img_tag.get("src", "")
        if src and not src.startswith("http"):
            img_tag["src"] = f"{url}/{src}"

    # # Extract all <div> elements with class "ltx_para" and their IDs
    # divs_with_ltx_para = soup.find_all("div", class_="ltx_para")

    # Extract all <div> elements with class "ltx_para" or ltx_figure and their IDs
    divs_with_ltx_para = soup.find_all(["div", "figure"], class_=["ltx_para", "ltx_figure", "ltx_table"])

    # Remove all divs that are a child of another div already in the list
    divs_with_ltx_para = [
        div for div in divs_with_ltx_para if not any(parent in list(div.parents) for parent in divs_with_ltx_para)
    ]

    div_ids_list = [div["id"] for div in divs_with_ltx_para if "id" in div.attrs]

    div_ids_list.insert(0, "ltx_abstract")

    # Get IDs and sort lexicographically
    div_ids_dict = {
        div["id"]: {
            "id": div["id"],
            "html": str(div),
            "div_obj": div,
            "class": div["class"][0] if len(div["class"]) > 0 else "None",
            "type": "figure" if div.name == "figure" else "text",
            "title": (
                div.parent.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "h7"], class_="ltx_title")[0]
                .get_text()
                .strip()
                if div.parent.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "h7"], class_="ltx_title")
                else ""
            ),
        }
        for div in divs_with_ltx_para
        if "id" in div.attrs
    }

    div_ids_dict["ltx_abstract"] = {
        "id": "ltx_abstract",
        "type": "abstract",
        "class": "ltx_abstract",
        "html": str(soup.find("div", class_="ltx_abstract")),
        "div_obj": soup.find("div", class_="ltx_abstract"),
        "title": soup.find(["h1", "h2", "h3", "h4", "h5", "h6", "h7"], class_="ltx_title").get_text().strip()[:150]
        + " (Abstract)",
    }

    # Find the closest figure for each div
    prev_figure_tag = None
    for div_id, div_info in div_ids_dict.items():
        if div_info["type"] == "figure":
            div_info["figure"] = str(div_info["div_obj"])
            div_info["figure_id"] = div_info["div_obj"].get("id", "")
            prev_figure_tag = div_info["div_obj"]
            continue
        div_obj = div_info["div_obj"]
        figure_tag = div_obj.find_next("figure", class_="ltx_figure")
        while figure_tag and not figure_tag.find("img"):
            figure_tag = figure_tag.find_next("figure", class_="ltx_figure")

        if figure_tag:
            div_info["figure_id"] = figure_tag.get("id", "")
            div_info["figure"] = str(figure_tag)
            prev_figure_tag = figure_tag
        else:
            div_info["figure"] = str(prev_figure_tag) if prev_figure_tag else ""
            div_info["figure_id"] = prev_figure_tag.get("id", "") if prev_figure_tag else ""

    # Check if in the div html is <a class="ltx_ref" href="https://arxiv.org/html/2412.06787v2#FIG_ID">
    for div_id, div_info in div_ids_dict.items():
        if div_info["type"] == "figure":
            continue
        div_obj = div_info["div_obj"]
        ltx_ref_links = div_obj.find_all("a", class_="ltx_ref")
        for link in ltx_ref_links:
            href = link.get("href", "")
            match = href.split("#")[-1]
            if match and match.startswith("S") and ("F" in match or "T" in match):
                fig_id = match
                # Find the figure with the extracted fig_id
                figure_tag = soup.find(id=fig_id)
                if figure_tag:
                    # print(f"Found figure with ID: {fig_id} for div: {div_id}")
                    div_info["figure_id"] = fig_id
                    div_info["figure"] = str(figure_tag)

    # Remove all tags with class ltx_note_outer from article
    for note_tag in article_tag.find_all(class_="ltx_note_outer"):
        note_tag.replace_with("")

    # Remove all nav tags from article
    for nav_tag in article_tag.find_all("nav"):
        nav_tag.replace_with("")

    article_str = str(article_tag)

    last_title = ""

    remove_list = []

    for div_id, div_info in tqdm(div_ids_dict.items(), desc="Processing divs"):

        if div_id == "A2.EGx1":
            print("xD")

        div_html = div_info["html"]
        div_soup = BeautifulSoup(div_html, "html.parser")
        div_html_str = str(div_soup)

        # get the html code up to this div in the article

        div_info_str = str(div_info["div_obj"])
        div_position = article_str.find(div_info_str)

        prev_html = article_str[:div_position]
        next_html = article_str[div_position + len(div_info_str) :]

        div_ids_dict[div_id]["prev_html"] = prev_html
        div_ids_dict[div_id]["next_html"] = next_html

        # Replace/ Remove all tables
        for table_tag in div_soup.find_all("table"):
            if (
                "ltx_equationgroup" not in table_tag["class"]
                and "ltx_equation" not in table_tag["class"]
                and "ltx_eqn_table" not in table_tag["class"]
            ):
                table_tag.replace_with("")

        # Replace all math parts with their spoken text versions
        for math_tag in div_soup.find_all("math"):
            alttext = math_tag.get("alttext", "[Math not found]")
            alttext = alttext.replace("\n", " ").replace("%", " ").replace("&", " ").strip()
            alttext = alttext.replace("\\begin{split}", "").replace("\\end{split}", "")
            len_alttext = len(alttext)
            if len_alttext > 100:
                math_tag.replace_with(f" ##break## ${alttext}$ ##break## ")  # Replace the math tag with the alttext
            else:
                math_tag.replace_with(f"${alttext}$")  # Replace the math tag with the alttext

        # Replacce/ Remove all citations with class "ltx_cite"
        for cite_tag in div_soup.find_all("cite", class_="ltx_cite"):
            cite_tag.replace_with("")

        # Replace all "[" and "]" with "(" and ")" respectively (in not math parts)
        for tag in div_soup.find_all(["p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "h7"]):
            tag.string = tag.get_text().replace("[", "(").replace("]", ")")

        # Convert the modified HTML to text
        cleaned_text = div_soup.get_text(separator=" ", strip=True)
        div_ids_dict[div_id]["cleaned_text"] = cleaned_text

        if cleaned_text == "":
            div_ids_list.remove(div_id)
            remove_list.append(div_id)
            continue

        # Split the cleaned text into sentences
        div_ids_dict[div_id]["sentences"] = split_text(cleaned_text)

        # Check if each sentence has an equation in it and replace with spoken text
        spoken_sentences = []
        for i, sentence in enumerate(div_ids_dict[div_id]["sentences"]):
            equation_matches = re.findall(r"\$(.*?)\$", sentence)
            spoken_sentence = sentence
            for equation in equation_matches:
                spoken_text = latex_to_speech_with_latexwalker(equation)
                spoken_sentence = spoken_sentence.replace(f"${equation}$", spoken_text)
            spoken_sentences.append(spoken_sentence)
        div_ids_dict[div_id]["sentences_spoken"] = spoken_sentences

        if div_id.startswith("S3.SS1"):
            print("xD")

        # Highlight each sentence / chunk in the div
        highlighted_divs = []
        start_highlight_index = 0
        for sentence in div_ids_dict[div_id]["sentences"]:
            temp_text = re.sub(r"\$.*?\$", lambda match: "", sentence)
            words = temp_text.split()
            highlighted_div_html, start_highlight_index = mark_words_in_html(
                str(div_html_str), words, start_highlight_index
            )
            highlighted_divs.append(highlighted_div_html)
            # print(div_id, start_highlight_index)

        div_ids_dict[div_id]["highlighted_html"] = highlighted_divs

        if div_info["title"] != last_title and div_info["title"] != "":
            last_title = div_info["title"]
            div_ids_dict[div_id]["sentences"].insert(0, last_title)
            div_ids_dict[div_id]["sentences_spoken"].insert(0, last_title)
            div_ids_dict[div_id]["highlighted_html"].insert(0, str(div_html_str))

    for div_id in remove_list:
        del div_ids_dict[div_id]

    # Add end to div_ids_list and div_ids_dict
    div_ids_list.append("#end")
    div_ids_dict["#end"] = {
        "id": "#end",
        "html": "",
        "div_obj": None,
        "type": "end",
        "title": "End",
        "sentences": ["The end"],
    }

    # enhanced_article_html = process_element(soup, article_tag)
    # Step 6: Get the modified HTML content of the "article" tag
    # modified_article_html = str(article_tag)

    # Step 7: Convert the modified HTML to Markdown
    # markdown_content = md(modified_article_html)

    # Step 8: Convert the Markdown to HTML (optional)
    # html_content = markdown.markdown(markdown_content, extensions=["tables"])

    # # Print the Markdown result (or save it to a file if needed)
    # print(markdown_content)

    # # Optionally, save the Markdown output to a file
    # with open("modified_article.md", "w", encoding="utf-8") as file:
    #     file.write(markdown_content)

    # # Optionally, save the HTML output to a file
    # with open("modified_article.html", "w", encoding="utf-8") as file:
    #     file.write(modified_article_html)

    # markdown_content = markdown_content.replace(
    #     "In generative models, two paradigms have gained attraction in various applications:",
    #     "<p style='background-color: #FFFF00; display:inline'>In generative models, two paradigms have gained attraction in various applications:</p>",
    # )

    return div_ids_list, div_ids_dict


if __name__ == "__main__":
    get_html()
