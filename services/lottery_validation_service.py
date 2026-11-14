
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation


# ==========================================
# VALID PRIZE CATEGORIES
# ==========================================

VALID_CATEGORIES = {
    "1st Prize",
    "2nd Prize",
    "3rd Prize",
    "4th Prize",
    "5th Prize",
    "Consolation Prize"
}


# ==========================================
# CATEGORY NORMALIZATION
# ==========================================

CATEGORY_ALIASES = {
    "1st prize": "1st Prize",
    "2nd prize": "2nd Prize",
    "3rd prize": "3rd Prize",
    "4th prize": "4th Prize",
    "5th prize": "5th Prize",
    "consolation prize": "Consolation Prize",
    "cons. prize": "Consolation Prize",
    "cons prize": "Consolation Prize"
}


def normalize_prize_category(category):
    """
    Convert recognized lottery prize headings
    into standard database category names.

    Unknown categories are returned unchanged
    so validation can reject them.
    """

    if not isinstance(category, str):
        return category

    cleaned = " ".join(category.strip().split())

    # Remove a known heading suffix.
    cleaned = re.sub(
        r"\s+amount\s+for\s+winner(?:s)?\.?$",
        "",
        cleaned,
        flags=re.IGNORECASE
    ).strip()

    normalized_key = cleaned.lower().rstrip(".")

    return CATEGORY_ALIASES.get(
        normalized_key,
        category
    )


# ==========================================
# TICKET NUMBER FORMAT
# ==========================================

# Supports:
# 0080
# 91256
# 92G 91256
# AB123
#
# Rejects special characters and unusual spacing.

TICKET_PATTERN = re.compile(
    r"^[A-Za-z0-9]+(?: [A-Za-z0-9]+)*$"
)


# ==========================================
# LOTTERY RESULT VALIDATION
# ==========================================

def validate_lottery_result(data):
    """
    Validate AI-extracted or admin-reviewed lottery data.

    Recognized prize category aliases are converted
    into standard database category names.

    Returns a list of validation errors.

    An empty list means structural checks passed,
    NOT that the lottery result is complete or accurate.
    """

    errors = []

    if not isinstance(data, dict):
        return ["Lottery result must be a JSON object."]

    # ------------------------------------------
    # LOTTERY METADATA
    # ------------------------------------------

    lottery_name = data.get("lottery_name")

    if (
        not isinstance(lottery_name, str)
        or not lottery_name.strip()
    ):
        errors.append("Lottery name is missing.")

    result_date = data.get("result_date")

    try:
        datetime.strptime(
            result_date,
            "%Y-%m-%d"
        )
    except (ValueError, TypeError):
        errors.append(
            "Invalid result date. Expected YYYY-MM-DD."
        )

    draw_time = data.get("draw_time")

    try:
        datetime.strptime(
            draw_time,
            "%H:%M:%S"
        )
    except (ValueError, TypeError):
        errors.append(
            "Invalid draw time. Expected HH:MM:SS."
        )

    # ------------------------------------------
    # PRIZE CATEGORIES
    # ------------------------------------------

    prizes = data.get("prizes")

    if not isinstance(prizes, list) or not prizes:
        errors.append("Prize categories are missing.")
        return errors

    seen_categories = set()

    for index, prize in enumerate(prizes, start=1):

        if not isinstance(prize, dict):
            errors.append(
                f"Prize {index} must be an object."
            )
            continue

        original_category = prize.get("category_name")

        category = normalize_prize_category(
            original_category
        )

        # Update the reviewed data so downstream
        # verification receives standard category names.
        if category in VALID_CATEGORIES:
            prize["category_name"] = category

        if category not in VALID_CATEGORIES:
            errors.append(
                f"Prize {index}: Invalid category "
                f"'{original_category}'."
            )

        elif category in seen_categories:
            errors.append(
                f"Prize {index}: Duplicate category "
                f"'{category}'."
            )

        else:
            seen_categories.add(category)

        # ------------------------------------------
        # PRIZE AMOUNT
        # ------------------------------------------

        amount = prize.get("prize_amount")

        if amount is not None:

            try:
                numeric_amount = Decimal(str(amount))

                if (
                    not numeric_amount.is_finite()
                    or numeric_amount < 0
                ):
                    errors.append(
                        f"Prize {index}: Invalid prize amount."
                    )

            except (InvalidOperation, ValueError, TypeError):
                errors.append(
                    f"Prize {index}: Prize amount must be numeric."
                )

        # ------------------------------------------
        # WINNING NUMBERS
        # ------------------------------------------

        numbers = prize.get("winning_numbers")

        if not isinstance(numbers, list):
            errors.append(
                f"Prize {index}: Winning numbers must be a list."
            )
            continue

        if not numbers:
            errors.append(
                f"Prize {index}: No winning numbers found."
            )

        seen_numbers = set()

        for position, number in enumerate(
            numbers,
            start=1
        ):

            if (
                not isinstance(number, str)
                or not number.strip()
            ):
                errors.append(
                    f"Prize {index}, number {position}: "
                    "Invalid winning number."
                )
                continue

            # Preserve leading zeros and ticket series.
            # Trim only outer whitespace.
            cleaned_number = number.strip()

            if not TICKET_PATTERN.fullmatch(cleaned_number):
                errors.append(
                    f"Prize {index}, number {position}: "
                    f"Invalid ticket format '{cleaned_number}'."
                )
                continue

            # Case-insensitive duplicate detection.
            # Leading zeros remain significant.
            normalized_number = cleaned_number.upper()

            if normalized_number in seen_numbers:
                errors.append(
                    f"Prize {index}: Duplicate winning "
                    f"number '{cleaned_number}' "
                    f"in {category}."
                )
            else:
                seen_numbers.add(normalized_number)

    return errors
