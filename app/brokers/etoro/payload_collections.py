def keep_dict_items(items: list) -> list[dict]:
    return [item for item in items if isinstance(item, dict)]
