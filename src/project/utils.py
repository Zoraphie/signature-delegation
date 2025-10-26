from datetime import timedelta

def compute_timedelta_from_string(timedelta_str: str) -> timedelta:
    """
    Parse a short duration string and return a corresponding datetime.timedelta.

    The input must be an integer followed by a single suffix:
      - "w" for weeks
      - "d" for days
      - "h" for hours

    Examples: "3w" -> 3 weeks, "4d" -> 4 days, "5h" -> 5 hours

    Args:
        timedelta_str: Duration string to parse.

    Returns:
        datetime.timedelta representing the parsed duration.

    Raises:
        ValueError: If the suffix is not one of "w", "d", "h" or if the numeric portion
                    cannot be converted to an integer.
    """
    VALID_SUFFIXES = ["w", "d", "h"]
    if timedelta_str[-1] not in VALID_SUFFIXES:
        raise ValueError("Specified duration is incorrect")
    if timedelta_str[-1] == "w":
        return timedelta(weeks=int(timedelta_str[:-1]))
    if timedelta_str[-1] == "d":
        return timedelta(days=int(timedelta_str[:-1]))
    if timedelta_str[-1] == "h":
        return timedelta(hours=int(timedelta_str[:-1]))
