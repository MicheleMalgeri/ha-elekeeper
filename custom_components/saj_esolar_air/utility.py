import re

def find_nonzero_value_with_regex(data, key_pattern, path=None):
    if path is None:
        path = []

    if isinstance(data, dict):
        for key, value in data.items():
            current_path = path + [key]
            if key_pattern.match(str(key)) and value != 0:
                return value, current_path
            result = find_nonzero_value_with_regex(value, key_pattern, current_path)
            if result is not None:
                return result

    elif isinstance(data, list):
        for index, item in enumerate(data):
            current_path = path + [index]
            result = find_nonzero_value_with_regex(item, key_pattern, current_path)
            if result is not None:
                return result

    return 0, None
