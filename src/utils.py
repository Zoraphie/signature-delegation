from datetime import timedelta

def compute_timedelta_from_string(timedelta_str: str) -> timedelta:
    """This function computes a real timedelta from a string such as 3w, 4d or 5h"""
    VALID_SUFFIXES = ["w", "d", "h"]
    if timedelta_str[-1] not in VALID_SUFFIXES:
        raise ValueError("Specified duration is incorrect")
    if timedelta_str[-1] == "w":
        return timedelta(weeks=int(timedelta_str[:-1]))
    if timedelta_str[-1] == "d":
        return timedelta(days=int(timedelta_str[:-1]))
    if timedelta_str[-1] == "h":
        return timedelta(hours=int(timedelta_str[:-1]))
