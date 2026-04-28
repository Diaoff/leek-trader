def normalize_a_share_symbol(symbol: str) -> str:
    value = symbol.strip().lower()
    if not value:
        return ""
    if "." in value:
        code, suffix = value.split(".", 1)
        if suffix == "sz":
            return f"sz{code}"
        if suffix == "sh":
            return f"sh{code}"
        if suffix == "bj":
            return f"bj{code}"
    if value.startswith(("sh", "sz", "bj")):
        return value
    if len(value) == 6 and value.isdigit():
        if value.startswith(("300", "301", "000", "001", "002", "003")):
            return f"sz{value}"
        if value.startswith(("600", "601", "603", "605", "688")):
            return f"sh{value}"
        if value.startswith(("8", "4")):
            return f"bj{value}"
    return value
