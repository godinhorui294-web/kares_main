"""SEARCH/REPLACE diff mode prompt constants.

Ported from MLEvolve; format markers and code examples kept in English.
"""

from __future__ import annotations


# ============ SEARCH/REPLACE format template ============

DIFF_SYS_FORMAT = """
***You must explain the improvement plan in detail and mark code changes clearly with the SEARCH/REPLACE diff format specified below (follow the format strictly, without deviation).***

# Code format:
<<<<<<< SEARCH
# the original code snippet to replace (must match exactly, including indentation)
=======
# the new code snippet to use instead
>>>>>>> REPLACE

Example of a valid diff:
<<<<<<< SEARCH
for i in range(m):
    for j in range(p):
        for k in range(n):
            C[i, j] += A[i, k] * B[k, j]
=======
# adjust loop order to improve the memory access pattern
for i in range(m):
    for k in range(n):
        for j in range(p):
            C[i, j] += A[i, k] * B[k, j]
>>>>>>> REPLACE

* Every SEARCH block must be copied **verbatim** from the current file, including indentation.
  - **Critical**: the SEARCH pattern must match the original code **exactly**, including:
    * the exact number of leading spaces (do not decrease or increase indentation)
    * exact whitespace characters (spaces vs tabs)
    * exact newlines and blank lines
  - **Common mistake**: using 2 spaces where the original code uses 4 (or vice versa), which makes the diff fail.
  - **How to avoid it**: copy directly from the code block provided above instead of retyping.
* **Critical**: every SEARCH must have exactly one matching REPLACE (paired within the same block). Never write a SEARCH without a corresponding REPLACE.
* Multiple independent changes are allowed. Lay out the SEARCH/REPLACE blocks one after another and add **no other text between blocks**.
* Make sure the file still runs after the change.
* Do not rewrite the entire file; revise only the necessary parts."""


# ============ diff mode instruction builders ============

def build_base_diff_instructions(learning_guidance: str = "") -> str:
    """Build the base instructions for diff mode (plan execution rules + SEARCH pattern rules)."""
    learning_line = f"    - {learning_guidance}\n" if learning_guidance else ""

    base_instructions = f"""    # Diff mode instructions

    ## Plan execution requirements

    - **You must implement the improvement plan given above.** Modify only the components and aspects specified in the plan.
    {learning_line}    - **Preserve all interfaces, variable names and compatibility constraints** (as stated in the plan).
    - **Make minimal, targeted changes** - focus only on the improvements listed in the plan.

    ## Critical: SEARCH pattern requirements

    **When creating SEARCH patterns, you must:**
    1. **Copy verbatim from the code provided above, including:**
       - exact indentation (spaces/tabs) - count the spaces carefully!
       - exact whitespace (leading/trailing spaces)
       - exact line breaks
       - exact comments and formatting

    2. **Do not modify indentation inside the SEARCH pattern** - it must match the original code character for character.

    3. **To ensure accuracy:**
       - copy directly from the provided code (do not retype)
       - count spaces carefully when in doubt (Python typically uses 4 spaces per level)
       - verify the SEARCH matches exactly before writing the REPLACE
       - if the code lives inside a function, keep the function's indentation level

    4. **Common mistakes:**
       - reducing indentation (e.g. the original code has 4 spaces and you use 2)
       - adding extra indentation
       - normalizing whitespace - keep it exactly as-is

    - **You must modify code using the SEARCH/REPLACE diff format specified below.** Follow the format requirements strictly.
    """
    return base_instructions


def build_diff_format_suffix() -> str:
    """Build the diff format suffix (appended to the user prompt to force
    SEARCH/REPLACE output)."""
    # Compact final reminder; the template already carries the full format spec.
    suffix = (
        "\n\n**Critical requirement**: you must provide code changes in SEARCH/REPLACE format. "
        "Do not return a full code block. Copy each SEARCH snippet exactly from the code being modified. "
        "Format: <<<<<<< SEARCH / original code / ======= / new code / >>>>>>> REPLACE"
    )
    return suffix
