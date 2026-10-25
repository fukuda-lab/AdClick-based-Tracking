import re
from urllib.parse import (urlparse,parse_qsl,unquote,urlunparse,)


def multi_TT_decode(value, max_rounds=5):
    previous = value

    for _ in range(max_rounds):
        decoded = unquote(previous)
        if decoded == previous:
            break
        previous = decoded

    return previous

def extract_TT_url_from_markdown(text):
    if not text:
        return text

    match = re.search(r'\]\((https?://[^)\s]+)\)', text)
    if match:
        return match.group(1)
    return text


def clean_url(url):
    if not url:
        return ""

    url = url.strip()
    url = extract_TT_url_from_markdown(url)

    return url


def extract_TT_matrix_params(path):
    params = []

    for segment in path.split("/"):
        if ";" not in segment:
            continue

        matrix_parts = segment.split(";")
        for part in matrix_parts[1:]:
            if "=" not in part:
                continue

            key, value = part.split("=", 1)

            key = multi_TT_decode(key)
            value = multi_TT_decode(value)

            params.append({
                "name": key,
                "value": value
            })

    return params


def extract_TT_params_from_url(url, max_decode_rounds=5):
    all_params = []

    url = clean_url(url)
    if not url:
        return all_params
    parsed = urlparse(url)

    query_params = parse_qsl(parsed.query,keep_blank_values=True)

    for key, value in query_params:
        key = multi_TT_decode(key,max_rounds=max_decode_rounds)
        value = multi_TT_decode(value,max_rounds=max_decode_rounds)
        all_params.append({
            "name": key,
            "value": value
        })

    matrix_params = extract_TT_matrix_params(parsed.path)
    all_params.extend(matrix_params)

    return all_params

