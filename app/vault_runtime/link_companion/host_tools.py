"""Native Companion host worker: paired Vault HTTP -> per-agent loopback Link MCP.

Run as the Link agent's owner. No new listener; keys remain on the host.
This file is executable with the Python standard library alone.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import stat
import time
import urllib.request
from urllib.parse import urlsplit

LIMIT = 4 * 1024 * 1024
MAX_LIST_PAGES = 16
PUBLISH_SECONDS = 5.0          # discovery interval while the tool list keeps changing
PUBLISH_MAX_SECONDS = 60.0     # an unchanged list is re-read less and less often
ERROR_MAX_SECONDS = 60.0


def jitter(seconds):
    return seconds * random.uniform(0.8, 1.2)


def list_tools(mcp):
    """Every page of tools/list (bounded). An empty-string cursor is valid; a repeat is a loop."""
    tools, cursor, seen = [], None, set()
    for _ in range(MAX_LIST_PAGES):
        listing = mcp('tools/list', {} if cursor is None else {'cursor': cursor})
        tools.extend(listing.get('tools', []))
        cursor = listing.get('nextCursor')
        if cursor is None:
            return tools
        if not isinstance(cursor, str) or cursor in seen:
            raise ValueError('Link MCP cursor is invalid')
        seen.add(cursor)
    raise ValueError('Link MCP tool list is too long')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def private_json(path):
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077 or st.st_uid != os.getuid() or st.st_size > 65536:
        raise ValueError('Unsafe Companion settings file')
    return json.loads(path.read_text())


def request(url, token, body):
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Companion calls require explicit host loopback')
    data = json.dumps(body).encode()
    if len(data) > LIMIT:
        raise ValueError('Request too large')
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': 'Bearer '+token, 'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=35) as response:
        raw = response.read(LIMIT+1)
        if len(raw) > LIMIT:
            raise ValueError('Response too large')
        return json.loads(raw)


def run(settings_path, token_path):
    last_publish = 0
    allowed = set()
    published = None
    interval = wait = PUBLISH_SECONDS
    failures = 0
    while True:
        try:
            settings = private_json(settings_path)
            # Endpoint token copies are raw private files, never passed on argv.
            st = token_path.lstat()
            if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077 or st.st_uid != os.getuid() or st.st_size > 4096:
                raise ValueError('Unsafe Companion token file')
            token = token_path.read_text().strip()
            if not token or any(c.isspace() for c in token):
                raise ValueError('Invalid Companion token')
            def mcp(method, params):
                answer = request(settings['mcp_url'], settings['key'],
                    {'jsonrpc':'2.0','id':'companion','method':method,'params':params})
                if 'error' in answer:
                    raise ValueError('Link MCP refused request')
                return answer.get('result', {})
            if time.monotonic()-last_publish > wait:
                tools = list_tools(mcp)
                if tools != published:
                    request('http://127.0.0.1:8766/link-companion/tools/publish', token, {'tools':tools})
                    published, interval = tools, PUBLISH_SECONDS
                else:
                    interval = min(interval * 2, PUBLISH_MAX_SECONDS)
                allowed = {t['name'] for t in tools}
                last_publish, wait = time.monotonic(), jitter(interval)
            pending = request('http://127.0.0.1:8766/link-companion/tools/poll',token,{})
            for call in pending.get('calls', []):
                if call.get('name') not in allowed:
                    result = {'isError':True,'content':[{'type':'text','text':'Link tool is unavailable.'}]}
                else:
                    # Never retry an ambiguous tool call. The queue claims it once.
                    try:
                        result = mcp('tools/call', {'name':call['name'],'arguments':call.get('arguments',{}),
                            '_meta':{'com.resonolabs.link/idempotencyKey':call['id']}})
                    except Exception:
                        result = {'isError':True,'content':[{'type':'text','text':'Link tool outcome unknown; not retried.'}]}
                request('http://127.0.0.1:8766/link-companion/tools/complete',token,{'id':call['id'],'result':result})
            failures = 0
        except Exception:
            # No credentials, arguments, tool results or platform errors in journal.
            last_publish, published, interval, wait = 0, None, PUBLISH_SECONDS, PUBLISH_SECONDS
            failures += 1
            time.sleep(jitter(min(2 * 2 ** (failures - 1), ERROR_MAX_SECONDS)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--settings', type=Path, required=True)
    parser.add_argument('--companion-token-file', type=Path, required=True)
    args = parser.parse_args()
    run(args.settings, args.companion_token_file)
