"""Diff patch application with retry logic.

Provides the shared apply-and-retry pipeline used by all diff-based
code generation modes (generation / barrier repair).

Ported from MLEvolve; the logger name was changed to "kares" and
format_planning_result_for_plan was dropped (KARES has no planning_result
concept).
"""

from __future__ import annotations

import logging
import re
from typing import Tuple, Optional, Callable

from .patcher import SearchReplacePatcher

logger = logging.getLogger("kares")


def _diagnose_failed_patches(diff_response: str, original_code: str) -> str:
    """
    Diagnose why SEARCH/REPLACE patches failed and return a detailed message.

    Args:
        diff_response: SEARCH/REPLACE text from the LLM
        original_code: the original source code

    Returns:
        A diagnostic message string.
    """
    import difflib

    patcher = SearchReplacePatcher()
    patches = list(patcher.PATCH_PATTERN.finditer(diff_response))

    if not patches:
        return ""

    diagnostics = []
    for i, block in enumerate(patches[:3], 1):  # diagnose at most the first 3 blocks
        search = patcher._strip_trailing_whitespace(block.group(1))
        replace = patcher._strip_trailing_whitespace(block.group(2))

        # try to match
        matched_search, pos = patcher._find_indented_match(search, original_code)

        if pos == -1:
            # SEARCH block not found
            search_lines = search.strip().splitlines()
            if search_lines:
                # find the closest match
                original_lines = original_code.splitlines()
                search_len = len(search_lines)
                best_match = None
                best_ratio = 0.0
                best_start_line = 0

                for j in range(max(0, len(original_lines) - search_len + 1)):
                    candidate_lines = original_lines[j:j + search_len]
                    candidate_text = "\n".join(candidate_lines)
                    search_block = "\n".join(search_lines)
                    ratio = difflib.SequenceMatcher(None, search_block, candidate_text).ratio()
                    if ratio > best_ratio and ratio > 0.5:
                        best_ratio = ratio
                        best_match = candidate_lines
                        best_start_line = j + 1

                if best_match and best_ratio > 0.5:
                    diagnostics.append(
                        f"Patch #{i}: SEARCH did not match exactly. "
                        f"Closest position is line {best_start_line} (similarity {best_ratio:.0%}). "
                        f"Check that indentation and spacing match exactly."
                    )

                    # show the mismatch
                    diff_lines = []
                    for s, m in zip(search_lines[:3], best_match[:3]):
                        if s != m:
                            diff_lines.append(f"  SEARCH: '{s}'")
                            diff_lines.append(f"  actual: '{m}'")
                    if diff_lines:
                        diagnostics.append("Mismatch examples (first 3 lines):\n" + "\n".join(diff_lines[:6]))
                else:
                    diagnostics.append(
                        f"Patch #{i}: no close match for the SEARCH block anywhere in the code (best similarity {best_ratio:.0%}). "
                        "Make sure the SEARCH snippet is copied from the current code."
                    )
        else:
            diagnostics.append(f"Patch #{i}: matched (character {pos+1})")

    return "\n".join(diagnostics) if diagnostics else ""


def apply_diff_with_retry(
    diff_response: str,
    original_code: str,
    max_retries: int = 3,
    regenerate_fn: Optional[Callable[[str, str], str]] = None,
) -> Tuple[Optional[str], int, str]:
    """
    Apply SEARCH/REPLACE diff patches to original_code with retry.

    Args:
        diff_response: SEARCH/REPLACE text from the LLM
        original_code: the original source code
        max_retries: maximum number of retries
        regenerate_fn: retry callback (current_code, retry_note) -> str that
            returns fresh LLM output

    Returns:
        (patched_code, total_applied, retry_note)
        - patched_code: the patched code; None on total failure
        - total_applied: number of patches successfully applied
        - retry_note: description of the last failure (empty string on success)
    """
    current_code = original_code
    total_applied = 0
    retry_note = ""
    current_response = diff_response
    last_valid_code = original_code  # last known valid code
    consecutive_empty_responses = 0  # consecutive empty responses

    for attempt in range(max_retries):
        try:
            logger.info(f"Applying diff patches (attempt {attempt + 1}/{max_retries})...")

            if current_response and (
                "<<<<<<< SEARCH" in current_response
                or "< SEARCH" in current_response
                or "<<<<<<<" in current_response
                # simplified format: the LLM emits SEARCH / REPLACE without angle brackets
                or re.search(r"^SEARCH\s*\n", current_response, re.MULTILINE)
            ):
                if "<<<<<<< SEARCH" in current_response:
                    search_markers = current_response.count("<<<<<<< SEARCH")
                    replace_markers = current_response.count(">>>>>>> REPLACE")
                elif "< SEARCH" in current_response:
                    search_markers = current_response.count("< SEARCH")
                    replace_markers = current_response.count("> REPLACE")
                elif re.search(r"^SEARCH\s*\n", current_response, re.MULTILINE):
                    search_markers = len(re.findall(r"^SEARCH\s*\n", current_response, re.MULTILINE))
                    replace_markers = len(re.findall(r"^REPLACE\s*\n", current_response, re.MULTILINE))
                else:
                    search_markers = 1
                    replace_markers = 0
                has_incomplete_block = search_markers > replace_markers

                patcher = SearchReplacePatcher()
                updated_code, count = patcher.apply_patch(current_response, current_code, strict=False)

                # diagnose which patches failed
                if count == 0 and search_markers > 0:
                    failed_blocks = _diagnose_failed_patches(current_response, current_code)
                    if failed_blocks:
                        retry_note = failed_blocks
                    else:
                        retry_note = (
                            f"Detected {search_markers} SEARCH/REPLACE block(s), but none could be applied. "
                            "Make sure each SEARCH snippet matches the code **exactly** (indentation, spacing, newlines)."
                        )
                    consecutive_empty_responses = 0  # not an empty response; reset
                elif count > 0 and updated_code and updated_code != current_code:
                    current_code = updated_code
                    total_applied += count
                    last_valid_code = current_code  # remember the valid code
                    consecutive_empty_responses = 0  # applied; reset

                # decide whether we are done
                if total_applied > 0 and current_code != original_code:
                    # no incomplete blocks: return success right away
                    if not has_incomplete_block:
                        logger.info(f"Successfully applied {total_applied} diff patch(es)")
                        return current_code, total_applied, ""

                    # incomplete blocks remain, but some patches already applied
                    # decide whether retrying still helps (too many empty responses)
                    if consecutive_empty_responses >= 2:
                        logger.warning(
                            f"{consecutive_empty_responses} consecutive retries produced no new patches; "
                            f"accepting the {total_applied} applied patch(es)"
                        )
                        return current_code, total_applied, (
                            f"Partial success ({total_applied} patch(es) applied), but the incomplete block was never completed"
                        )

                    # keep retrying: ask for the missing REPLACE parts
                    retry_note = (
                        "The previous diff output looks truncated (missing the closing '>>>>>>> REPLACE' marker). "
                        f"{total_applied} patch(es) were applied; please continue with the remaining patches."
                    )
                    logger.warning(
                        f"diff attempt {attempt + 1}/{max_retries}: "
                        f"count={count}, total_applied={total_applied}, "
                        f"code_changed={current_code != original_code}, "
                        f"search_markers={search_markers}, replace_markers={replace_markers}, "
                        f"has_incomplete_block={has_incomplete_block}"
                    )

                    if attempt < max_retries - 1 and regenerate_fn:
                        logger.info("Regenerating diff...")
                        current_response = regenerate_fn(current_code, retry_note)
                        continue
                    else:
                        # max retries reached; accept partial success
                        logger.info(f"Max retries reached; returning the {total_applied} applied patch(es)")
                        return current_code, total_applied, retry_note
                else:
                    # nothing applied at all
                    logger.warning(
                        f"diff attempt {attempt + 1}/{max_retries}: "
                        f"count={count}, total_applied={total_applied}, "
                        f"code_changed={current_code != original_code}, "
                        f"search_markers={search_markers}, replace_markers={replace_markers}, "
                        f"has_incomplete_block={has_incomplete_block}"
                    )

                    if attempt < max_retries - 1 and regenerate_fn:
                        logger.info("Regenerating diff...")
                        current_response = regenerate_fn(current_code, retry_note)
                        continue
                    else:
                        return None, 0, retry_note
            else:
                # response has no SEARCH/REPLACE format (empty response or malformed)
                consecutive_empty_responses += 1
                retry_note = (
                    "The previous output contained no valid SEARCH/REPLACE blocks. "
                    "Output complete SEARCH/REPLACE blocks only (no other text)."
                )
                logger.warning(
                    f"diff attempt {attempt + 1}/{max_retries}: response has no SEARCH/REPLACE format "
                    f"({consecutive_empty_responses} in a row)"
                )

                # partial success plus repeated empty responses: accept it
                if total_applied > 0 and consecutive_empty_responses >= 2:
                    logger.warning(
                        f"{consecutive_empty_responses} consecutive empty responses; "
                        f"accepting the {total_applied} applied patch(es)"
                    )
                    return current_code, total_applied, (
                        f"Partial success ({total_applied} patch(es) applied), but later retries returned nothing"
                    )

                if attempt < max_retries - 1 and regenerate_fn:
                    logger.info("Regenerating diff...")
                    current_response = regenerate_fn(current_code, retry_note)
                    continue
                else:
                    # final retry still produced nothing
                    if total_applied > 0:
                        logger.info(f"Retries exhausted; returning the {total_applied} applied patch(es)")
                        return current_code, total_applied, retry_note
                    return None, 0, retry_note

        except Exception as e:
            logger.warning(f"diff attempt {attempt + 1}/{max_retries} raised: {e}")
            retry_note = (
                f"The previous diff application failed: {e}. "
                "Output minimal SEARCH/REPLACE blocks that match the current code exactly, and make sure every block is complete."
            )
            if attempt < max_retries - 1 and regenerate_fn:
                logger.info("Regenerating diff...")
                try:
                    current_response = regenerate_fn(current_code, retry_note)
                except Exception as retry_e:
                    logger.error(f"Failed to regenerate diff: {retry_e}")
                continue
            else:
                # final retry failed; return partial success if any
                if total_applied > 0 and current_code != original_code:
                    logger.info(f"Returning the {total_applied} applied patch(es) after exception")
                    return current_code, total_applied, retry_note
                return None, 0, retry_note

    # unreachable in principle, kept as a safeguard
    if total_applied > 0 and current_code != original_code:
        logger.info(f"Loop ended; returning the {total_applied} applied patch(es)")
        return current_code, total_applied, retry_note
    return None, 0, retry_note
