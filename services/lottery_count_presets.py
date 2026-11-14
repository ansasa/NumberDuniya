
from copy import deepcopy


# Expected counts manually checked against
# the original uploaded lottery result image.
#
# These counts are specific to this draw.
# They are NOT universal lottery rules.

DRAW_COUNT_PRESETS = {
    # Independently confirmed for the 01 Nov 2026 Nagaland 8 PM PDF.
    ("nagaland state lotteries", "2026-11-01", "20:00:00"): {
        "1st Prize": 1,
        "2nd Prize": 10,
        "3rd Prize": 10,
        "4th Prize": 10,
        "5th Prize": 100,
    },

    (
        "sikkim state lotteries",
        "2026-10-15",
        "18:00:00"
    ): {
        "1st Prize": 1,
        "Consolation Prize": 1,
        "2nd Prize": 10,
        "3rd Prize": 10,
        "4th Prize": 10,
        "5th Prize": 100
    }
}


def get_expected_prize_counts(
    lottery_name,
    result_date,
    draw_time
):
    """
    Return independently configured expected
    prize counts for a specific draw.

    Returns None if no matching preset exists.
    """

    if not all(
        isinstance(value, str)
        for value in (
            lottery_name,
            result_date,
            draw_time
        )
    ):
        return None

    normalized_name = " ".join(
        lottery_name.split()
    ).casefold()

    normalized_date = result_date.strip()
    normalized_time = draw_time.strip()

    if len(normalized_time) == 5:
        normalized_time += ":00"

    key = (
        normalized_name,
        normalized_date,
        normalized_time
    )

    preset = DRAW_COUNT_PRESETS.get(key)

    if preset is None:
        return None

    return deepcopy(preset)
