
def check_lottery_completeness(
    extracted_data,
    expected_counts
):
    """
    Compare extracted winning-number counts against
    independently confirmed expected counts.

    This does not verify whether individual
    winning numbers are correct.
    """

    if not isinstance(extracted_data, dict):
        raise ValueError("Invalid extracted lottery data.")

    if not isinstance(expected_counts, dict):
        raise ValueError("Expected counts must be a dictionary.")

    prizes = extracted_data.get("prizes", [])

    if not isinstance(prizes, list):
        raise ValueError("Prizes must be a list.")

    actual_counts = {}

    for prize in prizes:
        category = prize.get("category_name")
        numbers = prize.get("winning_numbers", [])

        if not isinstance(category, str) or not category.strip():
            raise ValueError("Invalid prize category.")

        if not isinstance(numbers, list):
            raise ValueError(
                f"Invalid winning numbers for {category}."
            )

        if category in actual_counts:
            raise ValueError(
                f"Duplicate prize category: {category}"
            )

        actual_counts[category] = len(numbers)

    results = []
    all_matched = True

    for category, expected in expected_counts.items():

        if type(expected) is not int or expected < 0:
            raise ValueError(
                f"Invalid expected count for {category}."
            )

        actual = actual_counts.get(category, 0)
        category_present = category in actual_counts

        matched = category_present and actual == expected

        if not matched:
            all_matched = False

        results.append({
            "category": category,
            "expected": expected,
            "actual": actual,
            "matched": matched,
            "category_present": category_present
        })

    unexpected_categories = [
        category
        for category in actual_counts
        if category not in expected_counts
    ]

    if unexpected_categories:
        all_matched = False

    return {
        "all_matched": all_matched,
        "results": results,
        "unexpected_categories": unexpected_categories
    }
