import re



def _get_location_base(s):
        if s:
            match = re.match(r"^[^\s-]+", s)
            return match.group(0) if match else s
        return None


def _transform_location(location):
    if _get_location_base(location) == "Shuttle":
        return "Shuttle"
    elif _get_location_base(location) == "Palette":
        return "Palette"
    return location

def _update_locations(data, transform_func):
    for item in data:
        item["LocationName"] = transform_func(item["LocationName"])
    return data  

def _harmonize_empty_values(data):
    for item in data:
        for key, value in item.items():
            if value == "" or value is None or value == '---':
                item[key] = None
    return data
