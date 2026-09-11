"""Retained loopback HTTP demonstration; never contacts a provider."""
from __future__ import annotations

import argparse
import base64
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from experiment.revision.common_pool import collect, file_hash, publish


def run(folder):
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    protocol = folder / 'DEMO_PROTOCOL.md'
    protocol.write_text('本机HTTP演练；2槽各3次；人工响应与token计数。不是科学实验或费用批准。\n', encoding='utf-8')
    requests = []
    bodies = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(request)
            code = 'PROMPT = """Example:\n```sql\nSELECT 1\n```\n"""\n'
            if len(requests) in (2, 5):
                code = 'x = (\n'
            payload = dict(id=f'loopback-{len(requests)}', model='artificial-builder',
                           choices=[dict(index=0, finish_reason='stop',
                                         message=dict(role='assistant', content='```python\n' + code + '```'))],
                           usage=dict(prompt_tokens=2, completion_tokens=3, total_tokens=5))
            body = gzip.compress(json.dumps(payload, ensure_ascii=False).encode('utf-8'), mtime=0)
            bodies.append(body)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Encoding', 'gzip')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = dict(status='FROZEN', pool_id='loopback-only-demo', protocol_path=str(protocol),
                  output=str(folder / 'pool'), api_key_env='UNUSED_DEMO_KEY',
                  builder=dict(base_url=f'http://127.0.0.1:{server.server_port}/v1',
                               model='artificial-builder', max_tokens=100, temperature=0.7, timeout_seconds=5),
                  slots=[dict(id=condition, generation_condition=condition, strategy=None,
                              seeds=[10, 11, 12], messages=[dict(role='user', content='生成一个Python文件。')])
                         for condition in ('free', 'forced')])
    publish(folder / 'config.json', config)
    try:
        snapshot = collect(config, 'loopback-only')
        original = (folder / 'pool/pool.json').read_bytes()
        first_count = len(requests)
        collect(config, 'loopback-only')
        raw = [base64.b64decode(e['body_base64']) for e in snapshot['events']
               if e['kind'] == 'builder_response_bytes']
        report = dict(scope='loopback HTTP only; artificial responses and token counts; no provider calls',
                      first_requests=first_count, repeat_requests=len(requests) - first_count,
                      raw_compressed_bodies_match=raw == bodies,
                      repeat_export_identical=original == (folder / 'pool/pool.json').read_bytes(),
                      syntax_failures=sum(t['result']['syntax_error'] is not None for t in snapshot['tasks']),
                      completed_attempts=len(snapshot['tasks']), admission='not_evaluated',
                      source_sha256=file_hash(__file__))
        publish(folder / 'requests.json', requests)
        publish(folder / 'report.json', report)
        if not (first_count == 6 and report['repeat_requests'] == 0
                and report['raw_compressed_bodies_match'] and report['repeat_export_identical']
                and report['syntax_failures'] == 2):
            raise RuntimeError('loopback demonstration failed; artifacts retained')
        return report
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), ensure_ascii=False, indent=2))
