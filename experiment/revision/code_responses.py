"""Extract one Python response without treating fences inside strings as delimiters."""
from dataclasses import dataclass
import io
import re
import tokenize


@dataclass(frozen=True)
class CodeExtraction:
    status: str
    code: str | None
    start_line: int | None = None
    end_line: int | None = None


OPENING = re.compile(r'^\s*(`{3,})(?:python|py)\s*$', re.IGNORECASE)


def inside_unclosed_string(prefix):
    """Tokenization, not syntax success, determines whether a fence is in a string."""
    try:
        list(tokenize.generate_tokens(io.StringIO(prefix).readline))
    except tokenize.TokenError as exc:
        return exc.args[0] == 'EOF in multi-line string'
    except (IndentationError, SyntaxError):
        # Invalid indentation does not turn an outside delimiter into a string.
        return False
    return False


def extract_python(message):
    if not isinstance(message, str) or not message.strip():
        return CodeExtraction('missing_text', None)
    lines = message.splitlines(keepends=True)
    opening = next(((i, OPENING.fullmatch(line.strip())) for i, line in enumerate(lines)
                    if OPENING.fullmatch(line.strip()) and
                    not inside_unclosed_string(''.join(lines[:i]))), None)
    if opening is None:
        # Preserve the whole unfenced response; syntax/interface checks come later.
        return CodeExtraction('raw_text', message, 1, len(lines))
    start, match = opening
    closing = re.compile(r'^\s*`{' + str(len(match.group(1))) + r',}\s*$')
    for end in range(start + 1, len(lines)):
        if not closing.fullmatch(lines[end].strip()):
            continue
        code = ''.join(lines[start + 1:end])
        if inside_unclosed_string(code):
            continue
        if any(OPENING.fullmatch(line.strip()) for line in lines[end + 1:]):
            return CodeExtraction('multiple_python_blocks', None)
        return CodeExtraction('fenced_python', code, start + 2, end)
    return CodeExtraction('missing_close_or_unterminated_string', None)
