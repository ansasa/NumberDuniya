import os
import json

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

from services.lottery_validation_service import (
    validate_lottery_result
)
from services.lottery_completeness_service import (
    check_lottery_completeness
)
from services.lottery_count_presets import (
    get_expected_prize_counts
)


load_dotenv()

ALLOWED_FILE_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png"
}

MAX_FILE_SIZE = 10 * 1024 * 1024

GEMINI_MODEL = "gemini-2.5-flash"


def validate_extraction_completeness(
    extracted_data,
    expected_counts=None
):
    """
    Check extracted prize counts against independently
    configured expected counts.

    Returns a list of completeness errors.

    This does not prove individual ticket accuracy.
    """

    if expected_counts is None:
        expected_counts = get_expected_prize_counts(
            lottery_name=extracted_data.get("lottery_name"),
            result_date=extracted_data.get("result_date"),
            draw_time=extracted_data.get("draw_time")
        )

    if expected_counts is None:
        return []

    result = check_lottery_completeness(
        extracted_data,
        expected_counts
    )

    errors = []

    for item in result["results"]:
        if not item["matched"]:
            errors.append(
                f"{item['category']}: "
                f"Expected {item['expected']} winning numbers, "
                f"but Gemini extracted {item['actual']}."
            )

    for category in result["unexpected_categories"]:
        errors.append(
            f"Unexpected prize category: {category}."
        )

    if not result["all_matched"] and not errors:
        errors.append(
            "Lottery extraction completeness check failed."
        )

    return errors


def extract_lottery_result(
    file_bytes,
    file_type,
    expected_counts=None
):
    """
    Extract structured lottery results using Gemini AI.

    Optionally compare results against independently
    confirmed expected prize counts.

    This function never writes to Supabase.
    """

    if not isinstance(file_bytes, bytes) or not file_bytes:
        raise ValueError(
            "Invalid or empty lottery result file."
        )

    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError(
            "File exceeds the 10 MB limit."
        )

    if file_type not in ALLOWED_FILE_TYPES:
        raise ValueError(
            "Unsupported file type."
        )

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        try:
            api_key = st.secrets.get("GEMINI_API_KEY")
        except (FileNotFoundError, KeyError):
            api_key = None

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is missing."
        )

    # Expected counts must come from a trusted draw
    # configuration, not Gemini's own prediction.
    expected_counts = (
        dict(expected_counts)
        if expected_counts is not None
        else None
    )

    # Give Gemini the known table structure.
    count_instructions = ""

    if expected_counts:
        lines = [
            f"- {category}: {count} winning number(s)"
            for category, count in expected_counts.items()
        ]

        count_instructions = (
            "\nEXPECTED PRIZE TABLE COUNTS "
            "(reference only, never invent numbers):\n"
            + "\n".join(lines)
            + "\nIf fewer numbers are readable, return "
              "only the readable numbers. Never fill "
              "missing entries by guessing.\n"
        )

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            api_version="v1beta"
        )
    )

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(
                    data=file_bytes,
                    mime_type=file_type
                ),
                """
                Analyze the supplied lottery result document
                and extract structured information.

                REQUIRED OUTPUT FIELDS:

                - lottery_name
                - result_date (YYYY-MM-DD)
                - draw_time (HH:MM:SS, 24-hour format)
                - prizes containing:
                    category_name
                    prize_amount
                    winning_numbers

                EXTRACTION RULES:

                1. Identify the primary lottery result.
                   Ignore unrelated advertisements
                   and other lottery result panels.

                2. Extract all clearly readable numbers
                   for every prize category.

                3. For tabular winning-number sections,
                   scan every row from left to right,
                   then proceed to the next row.

                4. Do not skip the final row or final
                   column of any table.

                5. Preserve the exact characters,
                   leading zeros, and ticket series.

                6. Store every winning number as a string.

                7. Never guess, invent, or generate
                   missing numbers to reach a count.

                8. Include Consolation Prize when present.

                9. Keep each winning number in its
                   correct prize category.

                10. Do not summarize or truncate
                    winning-number arrays.

                11. Use null for unreadable dates,
                    times, or prize amounts.

                12. Before responding, recheck the
                    first and last rows of every
                    winning-number table.

                13. Return only JSON matching the
                    supplied response schema.
                """
                + count_instructions
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema={
                    "type": "OBJECT",
                    "properties": {
                        "lottery_name": {
                            "type": "STRING"
                        },
                        "result_date": {
                            "type": "STRING",
                            "nullable": True
                        },
                        "draw_time": {
                            "type": "STRING",
                            "nullable": True
                        },
                        "prizes": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "category_name": {
                                        "type": "STRING"
                                    },
                                    "prize_amount": {
                                        "type": "NUMBER",
                                        "nullable": True
                                    },
                                    "winning_numbers": {
                                        "type": "ARRAY",
                                        "items": {
                                            "type": "STRING"
                                        }
                                    }
                                },
                                "required": [
                                    "category_name",
                                    "prize_amount",
                                    "winning_numbers"
                                ]
                            }
                        }
                    },
                    "required": [
                        "lottery_name",
                        "result_date",
                        "draw_time",
                        "prizes"
                    ]
                }
            )
        )

        if not response.text:
            raise RuntimeError(
                "Gemini returned an empty response."
            )

        extracted_data = json.loads(response.text)

        validation_errors = validate_lottery_result(
            extracted_data
        )

        completeness_errors = (
            validate_extraction_completeness(
                extracted_data,
                expected_counts=expected_counts
            )
        )

        return {
            "extracted_data": extracted_data,
            "validation_errors": (
                validation_errors + completeness_errors
            ),
            "completeness_errors": completeness_errors
        }

    finally:
        client.close()
