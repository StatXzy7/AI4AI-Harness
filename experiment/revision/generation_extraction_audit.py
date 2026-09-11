"""Audit legacy Python-fence extraction using synthetic text and saved logs only.

No builder, provider, candidate import, or benchmark is executed. Archived .py
files are already-extracted prefixes, not complete provider responses.
"""
from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / 'experiment/phase2/generate.py'
OUT = ROOT / 'artifacts/revision_20260910/generation_extraction'
BUILDERS = ('deepseek', 'ernie', 'glm', 'kimi', 'minimax', 'qwen')
EXPECTED_LOGS = {f'{arm}_{builder}_s{seed}.json': (arm, builder, seed)
                 for arm in ('C', 'D') for builder in BUILDERS for seed in range(3)}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def legacy_extractor():
    source = GENERATOR.read_text(encoding='utf-8')
    node = next(n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name == 'extract_block')
    namespace = {'re': re}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(GENERATOR), 'exec'), namespace)
    return namespace['extract_block']


def syntax_error(code):
    try:
        ast.parse(code)
    except SyntaxError as exc:
        return dict(message=exc.msg, line=exc.lineno, offset=exc.offset)
    return None


def synthetic_cases():
    code = {
        'plain_control': 'def prompt():\n    return "Return SQL only."\n',
        'inline_sql_fence': 'def prompt():\n    return "Return only a ```sql fenced answer."\n',
        'docstring_sql_fence': '"""Require a ```sql fenced answer."""\ndef prompt():\n    return "SQL"\n',
        'regex_sql_fence': 'import re\nPATTERN = re.compile(r"^```sql(.*?)```$")\n',
    }
    extract = legacy_extractor()
    cases = []
    for name, original in code.items():
        response = '```python\n' + original + '```'
        extracted, truncated = extract(response, 'python')
        cases.append(dict(case=name, original_code=original, provider_response=response,
                          original_syntax_error=syntax_error(original), extracted_code=extracted,
                          extracted_syntax_error=syntax_error(extracted),
                          legacy_truncated_flag=truncated, code_preserved=extracted == original.strip()))
    return cases


def audit():
    log_paths = sorted((ROOT / 'artifacts/phase2/gen').glob('[CD]_*.json'))
    if {path.name for path in log_paths} != set(EXPECTED_LOGS):
        raise ValueError('expected the fixed C/D x six builders x three seeds log roster')
    bindings = {GENERATOR.relative_to(ROOT).as_posix(): digest(GENERATOR),
                Path(__file__).relative_to(ROOT).as_posix(): digest(Path(__file__))}
    rows = []
    counts = {arm: Counter() for arm in ('C', 'D')}
    for path in log_paths:
        data = json.loads(path.read_text(encoding='utf-8'))
        arm = data['arm']
        if (arm, data['builder'], data['seed']) != EXPECTED_LOGS[path.name]:
            raise ValueError(f'log identity mismatch: {path}')
        bindings[path.relative_to(ROOT).as_posix()] = digest(path)
        selected = [(index, row) for index, row in enumerate(data['results'])
                    if row['strategy'] == 'format_guard']
        if len(selected) != 1:
            raise ValueError(f'expected exactly one format_guard slot: {path}')
        slot_index, row = selected[0]
        if (row['harness'] != f'p2_{path.stem}_format_guard' or row['n_raw'] != 3 or
                len(row['attempts']) != 3 or {a['attempt'] for a in row['attempts']} != {0, 1, 2}):
            raise ValueError(f'format slot identity or fixed three attempts mismatch: {path}')
        total = counts[arm]
        total['slots'] += 1
        total['admitted'] += int(row['admitted'])
        total['neutral_valid_attempts'] += sum(int(a['neutral_valid']) for a in row['attempts'])
        for index, attempt in enumerate(row['attempts']):
            total['attempts'] += 1
            detail = str(attempt.get('neutral_detail', ''))
            total['syntax_error_logged'] += int('SyntaxError' in detail)
            total['unterminated_logged'] += int('unterminated' in detail)
            total['truncated_true'] += int(attempt.get('truncated') is True)
            raw = ROOT / 'artifacts/phase2/raw' / path.stem / f"{row['harness']}_raw{attempt['attempt']}.py"
            present = raw.is_file()
            raw_conflicts_with_log = present and attempt.get('reason') == 'no python fence'
            total['extracted_files_present'] += int(present)
            total['files_conflicting_with_no_fence_log'] += int(raw_conflicts_with_log)
            raw_text = raw.read_text(encoding='utf-8') if present else None
            parsed_error = syntax_error(raw_text) if present else None
            if present:
                bindings[raw.relative_to(ROOT).as_posix()] = digest(raw)
                total['saved_file_syntax_error'] += int(parsed_error is not None)
            rows.append(dict(arm=arm, builder=data['builder'], seed=data['seed'],
                             log_path=path.relative_to(ROOT).as_posix(),
                             slot_index=slot_index, attempt_index=index,
                             log_record=attempt, slot_admitted=row['admitted'],
                             extracted_path=raw.relative_to(ROOT).as_posix(), extracted_present=present,
                             raw_conflicts_with_no_fence_log=raw_conflicts_with_log,
                             saved_syntax_error=parsed_error,
                             saved_tail=raw_text[-180:] if present else None))
    return dict(scope='Legacy extraction audit; no historical full-response recovery or counterfactual admission',
                source_log_count=len(log_paths), counts={k: dict(v) for k, v in counts.items()},
                synthetic_cases=synthetic_cases(), attempts=rows, bindings=bindings,
                expected_log_roster=sorted(EXPECTED_LOGS),
                limitation='The inspected generator code saves extracted code, not complete builder messages. '
                'The per-attempt logs do not bind the executed generator source SHA. '
                'Synthetic reproduction proves the parser can truncate valid code at an inner fence; '
                'saved prefixes and failure logs do not prove every historical failure had this cause. '
                'Files coexisting with a no-python-fence log are conflicting artifacts, '
                'not attributed to that logged attempt as its generated code.')


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    result = audit()
    output = OUT / 'audit.v2.json'
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if output.exists() and output.read_text(encoding='utf-8') != serialized:
        raise FileExistsError('different audit already exists; version the new output')
    output.write_text(serialized, encoding='utf-8')
    print(json.dumps(result['counts'], ensure_ascii=False))
