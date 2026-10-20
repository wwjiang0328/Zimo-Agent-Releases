"""Inspect actual packaged WebView2 UIs on disposable Windows CI runners only."""
import base64
import json
import os
from pathlib import Path
import socket
import time
from urllib.request import urlopen

import websocket


class PackagedUI:
    def __init__(self, label: str):
        if (os.environ.get('GITHUB_ACTIONS') != 'true'
                or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'):
            raise RuntimeError('Packaged UI probe is restricted to disposable CI')
        self.label = label
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            self.port = listener.getsockname()[1]
        self.connection = None
        self.sequence = 0
        self.exceptions = []

    def environment(self) -> dict[str, str]:
        return {**os.environ, 'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS':
                f'--remote-debugging-port={self.port} --remote-debugging-address=127.0.0.1'}

    def connect(self, process) -> None:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f'{self.label} exited before UI became ready')
            try:
                with urlopen(f'http://127.0.0.1:{self.port}/json/list', timeout=2) as response:
                    targets = json.load(response)
                matches = [target for target in targets if target.get('type') == 'page'
                           and 'tauri.localhost' in target.get('url', '')
                           and 'pet.html' not in target.get('url', '')]
                if len(matches) == 1:
                    self.connection = websocket.create_connection(
                        matches[0]['webSocketDebuggerUrl'], timeout=10, suppress_origin=True)
                    self.call('Runtime.enable')
                    self.call('Page.enable')
                    return
            except (OSError, ValueError, websocket.WebSocketException):
                pass
            time.sleep(0.25)
        raise RuntimeError(f'{self.label} packaged WebView endpoint was not ready')

    def call(self, method: str, params=None):
        self.sequence += 1
        request_id = self.sequence
        self.connection.send(json.dumps({'id': request_id, 'method': method, 'params': params or {}}))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            reply = json.loads(self.connection.recv())
            if reply.get('method') == 'Runtime.exceptionThrown':
                self.exceptions.append(reply['params']['exceptionDetails'].get('text', 'uncaught exception'))
            if reply.get('id') != request_id:
                continue
            if 'error' in reply:
                raise RuntimeError(f'{method}: {reply["error"]}')
            return reply.get('result', {})
        raise TimeoutError(f'CDP command did not settle: {method}')

    def evaluate(self, expression: str):
        result = self.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True})
        if result.get('exceptionDetails'):
            raise RuntimeError(f'{self.label} UI evaluation failed')
        return result.get('result', {}).get('value')

    def wait_for(self, expression: str) -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.evaluate(expression):
                return
            time.sleep(0.1)
        raise RuntimeError(f'{self.label} packaged UI expectation timed out: {expression}')

    def exercise(self) -> None:
        self.wait_for("document.querySelector('#root')?.childElementCount > 0 && document.querySelector('button[aria-label=\"新建会话\"]') !== null")
        self.evaluate("document.querySelector('[aria-label=\"跳过启动视频\"]')?.click()")
        self.wait_for("document.querySelector('.zimo-startup-intro') === null")
        if not self.evaluate("document.body.innerText.includes(" + json.dumps('Zimo ' + self.label)
                             + ") && document.body.innerText.includes(" + json.dumps(os.environ['RELEASE_VERSION'])
                             + ") && typeof window.__TAURI_INTERNALS__?.invoke === 'function'"):
            raise RuntimeError(f'{self.label} packaged page is empty or incorrectly branded')
        count = self.evaluate("document.querySelectorAll('.sidebar-conversation-item').length")
        for expected_count in (count + 1, count + 2):
            self.evaluate("document.querySelector('button[aria-label=\"新建会话\"]').click()")
            self.wait_for(f"document.querySelectorAll('.sidebar-conversation-item').length === {expected_count}")
        self.evaluate("window.__probeTarget = document.querySelector('.sidebar-conversation-item:not(.is-active)'); window.__probeTarget.click()")
        self.wait_for("window.__probeTarget.matches('.is-active') && document.querySelectorAll('.sidebar-conversation-item.is-active').length === 1")
        self.evaluate("localStorage.setItem('__zimo_installer_probe', " + json.dumps(self.label) + ")")
        if self.exceptions:
            raise RuntimeError(f'{self.label} uncaught renderer exceptions: {self.exceptions}')
        print(f'PASS: {self.label} packaged UI rendered and two conversations were created/switched', flush=True)

    def verify_isolation(self) -> None:
        if self.evaluate("localStorage.getItem('__zimo_installer_probe')") != self.label:
            raise RuntimeError(f'{self.label} renderer storage is not isolated')

    def close(self) -> None:
        if self.connection:
            self.connection.close()

    def capture(self) -> None:
        if self.connection:
            output = Path(os.environ['RUNNER_TEMP']) / 'zimo-installed-ui'
            output.mkdir(exist_ok=True)
            screenshot = self.call('Page.captureScreenshot', {'format': 'png'})
            (output / f'{self.label}.png').write_bytes(base64.b64decode(screenshot['data']))
