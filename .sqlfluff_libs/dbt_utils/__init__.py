"""Minimal dbt_utils stand-in so sqlfluff's jinja templater can lint offline."""


def generate_surrogate_key(field_list):
    parts = [f"coalesce(cast({field} as string), '')" for field in field_list]
    return "md5(" + " || '-' || ".join(parts) + ")"
