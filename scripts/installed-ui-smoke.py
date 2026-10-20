"""Probe packaged UIs through native accessibility on disposable Windows CI."""
import os
from pathlib import Path
import time

from pywinauto import Application


class PackagedUI:
    def __init__(self, label: str):
        if (os.environ.get('GITHUB_ACTIONS') != 'true'
                or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'):
            raise RuntimeError('Packaged UI probe is restricted to disposable CI')
        self.label = label
        self.window = None
        self.expected_count = None

    def environment(self) -> dict[str, str]:
        return os.environ.copy()

    def connect(self, process) -> None:
        app = Application(backend='uia').connect(process=process.pid, timeout=30)
        spec = app.window(title_re=f'Zimo {self.label}.*', control_type='Window')
        spec.wait('exists visible', timeout=60)
        self.window = spec.wrapper_object()
        print(f'PASS: {self.label} packaged main window is visible', flush=True)

    def wait_for(self, predicate, description: str):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.2)
        raise RuntimeError(f'{self.label}: {description}')

    def buttons(self, name: str):
        return [control for control in self.window.descendants(control_type='Button')
                if control.window_text() == name and control.is_visible()]

    def conversations(self):
        return [control for control in self.window.descendants(control_type='Button')
                if control.window_text().startswith('新会话 ') and control.is_visible()]

    def exercise(self) -> None:
        self.wait_for(lambda: self.buttons('新建会话'), 'new conversation button did not render')
        skip = self.buttons('跳过启动视频')
        if skip:
            skip[0].invoke()
            self.wait_for(lambda: not self.buttons('跳过启动视频'), 'startup video did not close')
        names = [control.window_text() for control in self.window.descendants()]
        if not any('Zimo ' + self.label in name for name in names):
            raise RuntimeError(f'{self.label}: missing product identity in rendered UI')
        if not any(os.environ['RELEASE_VERSION'] in name for name in names):
            raise RuntimeError(f'{self.label}: missing version in rendered UI')
        count = len(self.conversations())
        for expected in range(count + 1, count + (4 if self.label == 'Local' else 3)):
            self.buttons('新建会话')[0].invoke()
            self.wait_for(lambda: len(self.conversations()) == expected, 'conversation creation did not settle')
        self.expected_count = len(self.conversations())
        target = self.conversations()[0]
        target.invoke()
        self.wait_for(lambda: 'current=page' in target.element_info.element.CurrentAriaProperties,
                      'selected conversation did not become current')
        print(f'PASS: {self.label} packaged UI rendered and conversations were created/switched', flush=True)

    def verify_isolation(self) -> None:
        if len(self.conversations()) != self.expected_count:
            raise RuntimeError(f'{self.label}: other product changed conversation list')

    def close(self) -> None:
        pass

    def capture(self) -> None:
        if self.window:
            output = Path(os.environ['RUNNER_TEMP']) / 'zimo-installed-ui'
            output.mkdir(exist_ok=True)
            self.window.capture_as_image().save(output / f'{self.label}.png')
