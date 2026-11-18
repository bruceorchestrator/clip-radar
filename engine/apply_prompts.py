"""Write overrides/gemini_worker.py: upstream file with our two prompt templates.

Usage: python3 apply_prompts.py <path to upstream gemini_worker.py> <output path>
Fails loudly if upstream renamed or reshaped a template, so a core update can
never silently drop our prompts.
"""
import re
import string
import sys

import prompts

NAMES = ("SCORE_PROMPT_TEMPLATE", "DETAIL_PROMPT_TEMPLATE")


def placeholders(template: str) -> set:
    return {field for _, field, _, _ in string.Formatter().parse(template) if field}


def replace_template(source: str, name: str, new_body: str) -> str:
    pattern = re.compile(rf'^{name} = """\n(.*?)\n"""\n', re.S | re.M)
    match = pattern.search(source)
    if not match:
        raise SystemExit(f"{name} not found in upstream gemini_worker.py")
    old = "\n" + match.group(1) + "\n"
    if placeholders(old) != placeholders(new_body):
        raise SystemExit(
            f"{name}: placeholders differ, upstream {sorted(placeholders(old))} "
            f"vs ours {sorted(placeholders(new_body))}")
    return source[: match.start()] + f'{name} = """{new_body}"""\n' + source[match.end():]


def main(src: str, dst: str) -> None:
    source = open(src, encoding="utf-8").read()
    for name in NAMES:
        source = replace_template(source, name, getattr(prompts, name))
    compile(source, dst, "exec")
    open(dst, "w", encoding="utf-8").write(source)
    print(f"wrote {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
