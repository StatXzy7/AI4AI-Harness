"""Runs several prompted solver calls, extracts numeric answers, and chooses the majority answer with a judge fallback."""
try:
    from ..harness_base import MathHarness
except Exception:
    try:
        from harness_base import MathHarness
    except Exception:
        class MathHarness:
            def llm(self, prompt: str, system: str = "", temperature: float = 0.0, n: int = 1) -> str:
                raise NotImplementedError

import re
import inspect
from collections import Counter


class GsmGsmQwenS0G5(MathHarness):
    _NUMBER_RE = re.compile(
        r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?|[+-]?\.\d+(?:[eE][+-]?\d+)?"
    )

    def solve(self, question: str) -> str:
        question = (question or "").strip()
        prompts = self._prompts(question)
        system = (
            "You are a careful grade-school math solver. "
            "Solve step by step and end with #### <number>."
        )

        counts = Counter()
        ordered_answers = []
        raw_outputs = []
        majority = len(prompts) // 2 + 1

        for prompt, temperature in prompts:
            raw = self._call(prompt, system=system, temperature=temperature)
            raw_outputs.append(raw)

            answer = self._extract_answer(raw)
            if answer is not None:
                ordered_answers.append(answer)
                counts[answer] += 1
                if counts[answer] >= majority:
                    return answer

        if counts:
            max_count = max(counts.values())
            top = [answer for answer, count in counts.items() if count == max_count]

            if len(top) == 1:
                return top[0]

            judged = self._judge(question, top, system)
            if judged in top:
                return judged

            for answer in ordered_answers:
                if answer in top:
                    return answer

            return top[0]

        fallback = self._extract_answer("\n".join(raw_outputs))
        return fallback if fallback is not None else "0"

    def _prompts(self, question: str):
        q = question.strip()
        return [
            (
                f"{q}\n\nSolve step by step. End with #### <number>.",
                0.0,
            ),
            (
                f"{q}\n\nRestate the important numbers, then solve step by step. "
                "End with #### <number>.",
                0.4,
            ),
            (
                f"{q}\n\nWrite the arithmetic expression, evaluate it carefully, "
                "and give the final answer. End with #### <number>.",
                0.4,
            ),
            (
                f"{q}\n\nSolve step by step, then check your arithmetic. "
                "End with #### <number>.",
                0.6,
            ),
            (
                f"{q}\n\nAnswer concisely with short steps. End with #### <number>.",
                0.6,
            ),
        ]

    def _judge(self, question: str, candidates, system: str):
        candidates_text = ", ".join(candidates)
        prompt = (
            f"{question}\n\n"
            f"Several candidate numeric answers were produced: {candidates_text}. "
            "Solve the problem carefully and choose the correct one. "
            "Reply only with #### <number>."
        )
        raw = self._call(prompt, system=system, temperature=0.0)
        return self._extract_answer(raw)

    def _call(self, prompt: str, system: str = "", temperature: float = 0.0) -> str:
        temperatures = [temperature] if temperature == 0.0 else [temperature, 0.0]

        for temp in temperatures:
            desired_kwargs = {"system": system, "temperature": temp, "n": 1}

            try:
                sig = inspect.signature(self.llm)
            except Exception:
                sig = None

            try:
                if sig is None:
                    raw = self.llm(prompt, **desired_kwargs)
                else:
                    has_var_keyword = any(
                        p.kind == inspect.Parameter.VAR_KEYWORD
                        for p in sig.parameters.values()
                    )
                    if has_var_keyword:
                        kwargs = desired_kwargs
                    else:
                        kwargs = {
                            k: v
                            for k, v in desired_kwargs.items()
                            if k in sig.parameters
                        }
                    raw = self.llm(prompt, **kwargs)

                return self._to_text(raw)

            except TypeError:
                try:
                    raw = self.llm(prompt, **desired_kwargs)
                    return self._to_text(raw)
                except Exception:
                    try:
                        raw = self.llm(prompt, system=system, temperature=temp)
                        return self._to_text(raw)
                    except Exception:
                        try:
                            raw = self.llm(prompt)
                            return self._to_text(raw)
                        except Exception:
                            pass

            except Exception:
                pass

        return ""

    def _to_text(self, obj) -> str:
        if obj is None:
            return ""
        if isinstance(obj, str):
            return obj
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="ignore")
        if isinstance(obj, list):
            return self._to_text(obj[0]) if obj else ""
        if isinstance(obj, dict):
            for key in ("text", "output", "completion", "content", "message", "response"):
                if key in obj:
                    return self._to_text(obj[key])
            if "choices" in obj:
                return self._to_text(obj["choices"])
        return str(obj)

    def _extract_answer(self, text, allow_fallback: bool = True):
        if text is None:
            return None

        text = str(text)
        if not text.strip():
            return None

        explicit_patterns = [
            r"####\s*([^\n\r#]*)",
            r"(?:the\s+)?(?:final\s+)?answer\s*(?:is|:|=)\s*([^\n\r]*)",
            r"(?:the\s+)?(?:final\s+)?(?:total|result|value|sum|difference|product|quotient)\s*(?:is|:|=)\s*([^\n\r]*)",
            r"\\boxed\{([^}]*)\}",
            r"boxed\{([^}]*)\}",
        ]

        candidates = []
        for pattern in explicit_patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                answer = self._answer_from_snippet(match.group(1))
                if answer is not None:
                    candidates.append((match.start(), answer))

        if candidates:
            candidates.sort(key=lambda item: item[0])
            return candidates[-1][1]

        if allow_fallback:
            numbers = self._NUMBER_RE.findall(text)
            if numbers:
                return self._canonical_number(numbers[-1])

        return None

    def _answer_from_snippet(self, snippet):
        if snippet is None:
            return None

        snippet = str(snippet).strip()
        if not snippet:
            return None

        numbers = self._NUMBER_RE.findall(snippet)
        if numbers:
            return self._canonical_number(numbers[0])

        return self._canonical_number(snippet)

    def _canonical_number(self, raw):
        if raw is None:
            return None

        s = str(raw).strip()
        s = s.replace(",", "").replace("$", "").replace(" ", "")

        if s.endswith("%"):
            s = s[:-1].strip()

        if not s:
            return None

        if s.startswith("+"):
            s = s[1:]

        negative = s.startswith("-")
        if negative:
            s = s[1:]

        if not s:
            return None

        if re.fullmatch(r"\d+", s):
            value = str(int(s))
            if value == "0":
                return "0"
            return ("-" + value) if negative else value

        decimal_match = re.fullmatch(r"(\d*)\.(\d*)", s)
        if decimal_match:
            int_part, frac_part = decimal_match.groups()

            if not int_part and not frac_part:
                return None

            frac_part = frac_part.rstrip("0")

            if not frac_part:
                value = str(int(int_part)) if int_part else "0"
                if value == "0":
                    return "0"
                return ("-" + value) if negative else value

            int_value = str(int(int_part)) if int_part else "0"
            value = f"{int_value}.{frac_part}"
            return ("-" + value) if negative else value

        signed = ("-" if negative else "") + s
        try:
            value = float(signed)
        except ValueError:
            return None

        if value != value or value == float("inf") or value == float("-inf"):
            return None

        if value == 0:
            return "0"

        if value.is_integer():
            return str(int(value))

        return repr(value)