"""Read-only, conservative prize-number parser for NumberDuniya region OCR.

No Gemini, database, pandas or pytesseract. Output is a review draft, NOT verified results.
Designed for the explicitly selected Nagaland Magic Sunday 8 PM OCR profile.
"""
from __future__ import annotations

import re
from datetime import datetime

PROFILE = 'nagaland_magic_sunday_8pm'
EXPECTED = {'first_prize': 1, 'second_prize': 10, 'third_prize': 10,
            'fourth_prize': 10, 'fifth_prize': 100}


def _numbers(text: str, digits: int) -> list[str]:
    return re.findall(rf'(?<![A-Za-z0-9])\d{{{digits}}}(?![A-Za-z0-9])', text)


def _region_map(ocr_result: dict) -> dict:
    pages = ocr_result.get('pages') or []
    if len(pages) != 1 or pages[0].get('method') != 'tesseract_regions':
        raise ValueError('Expected exactly one page of region-based OCR.')
    return {r['name']: r for r in pages[0].get('regions', [])}


def _prize_block_numbers(region: dict) -> tuple[list[str], list[str], list[str]]:
    """Use 5-digit tokens for second prize and 4-digit rows for third/fourth.

    Exclude OCR header/amount text using line structure. Require manual review.
    """
    text = region.get('text', '')
    lines = text.splitlines()
    second = []
    four_digit_lines = []
    for line in lines:
        fives = _numbers(line, 5)
        if fives:
            second.extend(fives)
        fours = _numbers(line, 4)
        # A line with at least 4 four-digit entries is a plausible winning-number row.
        if len(fours) >= 4:
            four_digit_lines.append(fours)
    fours_flat = [n for row in four_digit_lines for n in row]
    return second, fours_flat[:10], fours_flat[10:20]


def _fifth_numbers(region: dict) -> list[str]:
    # Accept 10-column rows only; don't count dates, money, or advertising text.
    rows = []
    for line in region.get('text', '').splitlines():
        tokens = _numbers(line, 4)
        if len(tokens) == 10:
            rows.extend(tokens)
    return rows


def _first_prize(region: dict) -> list[str]:
    # Require a recognizable series followed by a 5-digit number; don't guess.
    text = region.get('text', '')
    match = re.search(r'(?<![A-Za-z0-9])([0-9]{1,3}[A-Za-z])\s*[- ]?\s*(\d{5})(?!\d)', text)
    return [f'{match.group(1)} {match.group(2)}'] if match else []


def _date_candidate(regions: dict) -> str | None:
    # Date is a suggestion only, never authoritative metadata.
    for name in ('header', 'first_prize', 'footer'):
        text = regions.get(name, {}).get('text', '')
        for raw in re.findall(r'\b\d{2}[./-]\d{2}[./-]\d{2,4}\b', text):
            try:
                date = datetime.strptime(raw.replace('.', '/').replace('-', '/'),
                                         '%d/%m/%y' if len(raw.split('/')[-1]) == 2 else '%d/%m/%Y')
                return date.date().isoformat()
            except ValueError:
                continue
    return None


def parse_prize_numbers(ocr_result: dict) -> dict:
    """Return prize-wise review candidates and count warnings; never publish."""
    if ocr_result.get('layout_profile') != PROFILE:
        raise ValueError(f'This parser requires OCR layout_profile={PROFILE!r}.')
    regions = _region_map(ocr_result)
    required = {'header', 'first_prize', 'prizes_2_to_4', 'prize_5', 'footer'}
    if not required.issubset(regions):
        raise ValueError('Missing OCR regions: ' + ', '.join(sorted(required - regions.keys())))

    second, third, fourth = _prize_block_numbers(regions['prizes_2_to_4'])
    prizes = {
        'first_prize': _first_prize(regions['first_prize']),
        'second_prize': second,
        'third_prize': third,
        'fourth_prize': fourth,
        'fifth_prize': _fifth_numbers(regions['prize_5']),
    }
    warnings = []
    for name, numbers in prizes.items():
        expected = EXPECTED[name]
        if len(numbers) != expected:
            warnings.append(f'{name}: found {len(numbers)} entries; expected {expected}.')
    if not prizes['first_prize']:
        warnings.append('First prize unreadable in current crop; review original PDF / adjust crop.')
    # Flag candidate conflicts across OCR modes rather than silently choosing one.
    for name in ('first_prize', 'prizes_2_to_4', 'prize_5'):
        region = regions[name]
        candidates = region.get('candidates', [])
        if len(candidates) >= 2 and candidates[0].get('text') != candidates[1].get('text'):
            warnings.append(f'{name}: OCR candidates differ; compare against original PDF.')
    return {
        'status': 'needs_admin_review',
        'lottery_name_candidate': 'Nagaland State Lotteries' if re.search(
            r'NAGALAND\s+STATE\s+LOTTERIES', regions['header'].get('text', ''), re.I) else None,
        'result_date_candidate': _date_candidate(regions),
        'draw_time_candidate': '08:00 PM',  # from explicitly selected layout profile, not OCR proof
        'layout_profile': PROFILE,
        'prizes': {key: {'numbers': nums, 'count': len(nums), 'expected': EXPECTED[key],
                         'count_ok': len(nums) == EXPECTED[key]} for key, nums in prizes.items()},
        'warnings': warnings,
        'can_auto_publish': False,
    }
