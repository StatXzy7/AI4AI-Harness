"""Offline tests of the versioned generator; all token counts are artificial."""
import ast
import base64
from contextlib import closing
import gzip
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import httpx

from experiment.revision.code_responses import extract_python
from experiment.revision.common_pool import ROOT, collect, prepare, publish
from experiment.revision.generation_extraction_audit import synthetic_cases


class CodeResponseTests(unittest.TestCase):
    def test_legacy_regression_inputs_preserve_complete_code(self):
        for case in synthetic_cases():
            extraction = extract_python(case['provider_response'])
            self.assertEqual(extraction.code, case['original_code'])
            ast.parse(extraction.code)

    def test_multiline_string_with_standalone_fences_and_crlf(self):
        code = 'PROMPT = """Example:\r\n```sql\r\nSELECT 1\r\n```\r\n"""\r\nx = 1\r\n'
        self.assertEqual(extract_python('```python\r\n' + code + '```\r\n').code, code)
        raw = 'DOC = """Example:\n```python\nx = 1\n```\n"""\ny = 2\n'
        self.assertEqual(extract_python(raw).code, raw)
        self.assertEqual(extract_python('Here is the file:\n```python\nx = 1\n```').code, 'x = 1\n')

    def test_syntax_is_not_used_to_select_a_more_convenient_block(self):
        reply = '```python\nx = (\n```\n```python\nx = 1\n```'
        self.assertEqual(extract_python(reply).status, 'multiple_python_blocks')
        self.assertIsNone(extract_python(reply).code)
        broken = extract_python('```python\nx = (\n```')
        self.assertEqual(broken.code, 'x = (\n')
        with self.assertRaises(SyntaxError):
            ast.parse(broken.code)

    def test_no_invented_closing_fence_or_code_completion(self):
        for reply in ('```python\nx = 1', '```python\nx = """open\n```'):
            self.assertEqual(extract_python(reply).status, 'missing_close_or_unterminated_string')
            self.assertIsNone(extract_python(reply).code)
        raw = 'x = "含中文与```sql"\r\n'
        self.assertEqual(extract_python(raw).code, raw)


class CommonPoolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'artifacts')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.protocol = self.folder / 'protocol.md'
        self.protocol.write_text('Offline fixture; tokens are artificial.', encoding='utf-8')
        self.config = dict(status='FROZEN', pool_id='offline-unit', protocol_path=str(self.protocol),
                           output=str(self.folder / 'pool'), api_key_env='UNUSED_TEST_KEY',
                           builder=dict(base_url='https://example.invalid/v1', model='mock-builder',
                                        max_tokens=100, timeout_seconds=1, temperature=0.7),
                           slots=[dict(id='slot0', generation_condition='forced', strategy='format_guard',
                                       seeds=[10, 11, 12], messages=[dict(role='user', content='Write one Python file.')])])
        self.requests = []

    def response(self, request, *, text=None, usage=True):
        self.requests.append(json.loads(request.content))
        content = '```python\nPROMPT = "Return ```sql only."\n```' if text is None else text
        payload = dict(id=f'mock-{len(self.requests)}', model='mock-builder',
                       choices=[dict(index=0, finish_reason='stop', message=dict(role='assistant', content=content))])
        if usage:
            payload['usage'] = dict(prompt_tokens=2, completion_tokens=3, total_tokens=5)
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(payload).encode('utf-8')))

    def events(self):
        with closing(sqlite3.connect(self.folder / 'pool/ledger.sqlite')) as db:
            return [json.loads(row[0]) for row in db.execute('SELECT value FROM events ORDER BY id')]

    def test_all_three_attempts_even_after_valid_code_and_exact_no_call_resume(self):
        def responder(request):
            # A syntax error in attempt1 must not skip attempt2 or trigger a replacement.
            text = '```python\nx = (\n```' if len(self.requests) == 1 else None
            return self.response(request, text=text)
        snapshot = collect(self.config, 'test-only', transport=httpx.MockTransport(responder))
        self.assertEqual([r['seed'] for r in self.requests], [10, 11, 12])
        self.assertTrue(all(r['n'] == 1 and r['messages'] == self.config['slots'][0]['messages'] for r in self.requests))
        results = sorted((t['result'] for t in snapshot['tasks']), key=lambda r:r['identity']['attempt'])
        self.assertEqual([r['syntax_error'] is not None for r in results], [False, True, False])
        self.assertTrue(all(r['admission'] == 'not_evaluated' for r in results))
        self.assertEqual(sum(r['accounting']['http_attempts'] for r in results), 3)
        events = snapshot['events']
        for response in [e for e in events if e['kind'] == 'builder_response_bytes']:
            body = base64.b64decode(response['body_base64'])
            text = json.loads(body)['choices'][0]['message']['content']
            extracted = next(e for e in events if e['kind'] == 'candidate_extracted' and e['task'] == response['task'])
            self.assertLess(response['id'], extracted['id'])
            self.assertEqual(text, extracted['result']['message'])
        before = (self.folder / 'pool/pool.json').read_bytes()
        collect(self.config, 'test-only', transport=httpx.MockTransport(responder))
        self.assertEqual(len(self.requests), 3)
        self.assertEqual((self.folder / 'pool/pool.json').read_bytes(), before)

    def test_missing_usage_preserves_response_and_code_but_stops_next_attempt(self):
        transport = httpx.MockTransport(lambda r:self.response(r, usage=False))
        with self.assertRaisesRegex(RuntimeError, 'usage unknown'):
            collect(self.config, 'test-only', transport=transport)
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(any(e['kind'] == 'candidate_extracted' for e in self.events()))
        self.assertFalse((self.folder / 'pool/POOL_COMPLETE.json').exists())
        with self.assertRaisesRegex(RuntimeError, 'Unfinished task'):
            collect(self.config, 'test-only', transport=transport)
        self.assertEqual(len(self.requests), 1)

    def test_timeout_has_no_automatic_retry_or_resume(self):
        def timeout(request):
            self.requests.append(request)
            raise httpx.ReadTimeout('offline timeout', request=request)
        transport = httpx.MockTransport(timeout)
        with self.assertRaisesRegex(RuntimeError, 'completion/cost unknown'):
            collect(self.config, 'test-only', transport=transport)
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(any(e['kind'] == 'http_unknown' for e in self.events()))
        with self.assertRaisesRegex(RuntimeError, 'Unfinished task'):
            collect(self.config, 'test-only', transport=transport)

    def test_unparseable_http_body_is_retained_exactly(self):
        body = b'provider returned invalid JSON\xff'
        with self.assertRaisesRegex(RuntimeError, 'response unusable'):
            collect(self.config, 'test-only', transport=httpx.MockTransport(
                lambda _:httpx.Response(200, stream=httpx.ByteStream(body))))
        event = next(e for e in self.events() if e['kind'] == 'builder_response_bytes')
        self.assertEqual(base64.b64decode(event['body_base64']), body)
        self.assertFalse((self.folder / 'pool/POOL_COMPLETE.json').exists())

    def test_gzip_body_is_preserved_before_separate_decoding(self):
        bodies = []
        def compressed(request):
            response = self.response(request)
            body = gzip.compress(b''.join(response.iter_raw()), mtime=0)
            bodies.append(body)
            return httpx.Response(200, headers={'content-encoding': 'gzip'}, stream=httpx.ByteStream(body))
        snapshot = collect(self.config, 'test-only', transport=httpx.MockTransport(compressed))
        events = [e for e in snapshot['events'] if e['kind'] == 'builder_response_bytes']
        self.assertEqual([base64.b64decode(e['body_base64']) for e in events], bodies)
        self.assertTrue(all(e['content_encoding'] == 'gzip' for e in events))
        self.assertTrue(all(t['result']['extraction']['status'] == 'fenced_python' for t in snapshot['tasks']))

    def test_missing_message_stops_without_completing_or_retrying(self):
        requests = []
        def malformed(request):
            requests.append(request)
            body = json.dumps(dict(choices=[dict(index=0, finish_reason='stop')],
                                   usage=dict(prompt_tokens=2, completion_tokens=3, total_tokens=5))).encode()
            return httpx.Response(200, stream=httpx.ByteStream(body))
        with self.assertRaisesRegex(RuntimeError, 'message shape'):
            collect(self.config, 'test-only', transport=httpx.MockTransport(malformed))
        self.assertEqual(len(requests), 1)
        self.assertTrue(any(e['kind'] == 'builder_response_bytes' for e in self.events()))
        with closing(sqlite3.connect(self.folder / 'pool/ledger.sqlite')) as db:
            self.assertEqual(db.execute('SELECT result FROM tasks').fetchall(), [(None,)])
        with self.assertRaisesRegex(RuntimeError, 'Unfinished task'):
            collect(self.config, 'test-only', transport=httpx.MockTransport(malformed))
        self.assertEqual(len(requests), 1)
        self.assertFalse((self.folder / 'pool/POOL_COMPLETE.json').exists())

    def test_input_change_is_permanently_invalid_even_after_restoration(self):
        original = self.protocol.read_bytes()
        def changed(request):
            self.protocol.write_text('changed', encoding='utf-8')
            return self.response(request)
        with self.assertRaisesRegex(RuntimeError, 'pool is invalid'):
            collect(self.config, 'test-only', transport=httpx.MockTransport(changed))
        self.protocol.write_bytes(original)
        with self.assertRaisesRegex(RuntimeError, 'marked invalid'):
            collect(self.config, 'test-only', transport=httpx.MockTransport(changed))
        self.assertEqual(len(self.requests), 1)

    def test_prepare_is_key_free_and_draft_cannot_issue_requests(self):
        self.config['status'] = 'DRAFT'
        self.assertEqual(prepare(self.config)['planned_attempts'], 3)
        with patch('experiment.revision.common_pool.httpx.Client') as client:
            with self.assertRaisesRegex(ValueError, 'DRAFT'):
                collect(self.config, 'test-only')
            client.assert_not_called()

    def test_export_interruption_recovers_from_completed_ledger_without_requests(self):
        transport = httpx.MockTransport(self.response)
        def interrupted(path, value):
            if path.name == 'POOL_COMPLETE.json':
                raise OSError('simulated export interruption')
            publish(path, value)
        with patch('experiment.revision.common_pool.publish', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'export interruption'):
                collect(self.config, 'test-only', transport=transport)
        self.assertEqual(len(self.requests), 3)
        self.assertFalse((self.folder / 'pool/POOL_COMPLETE.json').exists())
        before = (self.folder / 'pool/pool.json').read_bytes()
        collect(self.config, 'test-only', transport=transport)
        self.assertEqual(len(self.requests), 3)
        self.assertEqual((self.folder / 'pool/pool.json').read_bytes(), before)
        self.assertTrue((self.folder / 'pool/POOL_COMPLETE.json').exists())


if __name__ == '__main__':
    unittest.main()
