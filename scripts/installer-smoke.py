"""Exercise official installers only on disposable GitHub-hosted runners."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import time


def run(args, **kwargs):
    return subprocess.run(args, check=True, timeout=180, **kwargs)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(tag, name, destination):
    repo = os.environ['GITHUB_REPOSITORY']
    raw = run(['gh', 'api', f'repos/{repo}/releases/tags/{tag}'], capture_output=True, text=True)
    assets = json.loads(raw.stdout)['assets']
    matches = [asset for asset in assets if asset['name'] == name]
    require(len(matches) == 1, f'Missing exact asset: {name}')
    expected = matches[0].get('digest', '')
    require(expected.startswith('sha256:'), f'Missing GitHub digest: {name}')
    run(['gh', 'release', 'download', tag, '--repo', repo, '--pattern', name, '--dir', str(destination)])
    artifact = destination / name
    require(digest(artifact) == expected[7:], f'Artifact digest mismatch: {name}')
    return artifact


def sentinel(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'installer-acceptance-sentinel.txt'
    path.write_text('preserve this product data', encoding='utf-8')
    return path


def assert_sentinel(path):
    require(path.read_text(encoding='utf-8') == 'preserve this product data', f'Data changed: {path}')


def live_processes(executables):
    processes = []
    try:
        for executable in executables:
            processes.append(subprocess.Popen([str(executable)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        time.sleep(12)
        require(all(p.poll() is None for p in processes), 'Installed desktop exited during startup')
        print('PASS: installed Local and Cloud start concurrently', flush=True)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


def windows(root, old, local, cloud):
    local_dir, cloud_dir = root / 'Local', root / 'Cloud'
    local_exe, cloud_exe = local_dir / 'Zimo.exe', cloud_dir / 'ZimoCloud.exe'

    def install(artifact, directory):
        run([str(artifact), '/S', '/D=' + str(directory)], creationflags=subprocess.CREATE_NO_WINDOW)

    def uninstall(directory, executable):
        run([str(directory / 'uninstall.exe'), '/S', '_?=' + str(directory)], creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(20):
            if not executable.exists():
                break
            time.sleep(0.5)
        require(not executable.exists(), 'Uninstall did not remove its executable')

    install(old, local_dir)
    require(local_exe.exists(), 'Legacy Local install failed')
    local_data = sentinel(Path(os.environ['LOCALAPPDATA']) / 'com.zimo.app')
    install(local, local_dir)
    require(local_exe.exists(), 'Local upgrade failed')
    assert_sentinel(local_data)
    install(cloud, cloud_dir)
    require(cloud_exe.exists(), 'Cloud install failed')
    cloud_data = sentinel(Path(os.environ['LOCALAPPDATA']) / 'com.zimo.cloud')
    local_digest, cloud_digest = digest(local_exe), digest(cloud_exe)
    live_processes([local_exe, cloud_exe])
    uninstall(cloud_dir, cloud_exe)
    require(digest(local_exe) == local_digest, 'Cloud uninstall changed Local')
    assert_sentinel(local_data)
    assert_sentinel(cloud_data)
    install(cloud, cloud_dir)
    uninstall(local_dir, local_exe)
    require(digest(cloud_exe) == cloud_digest, 'Local uninstall changed Cloud')
    assert_sentinel(local_data)
    assert_sentinel(cloud_data)
    print('PASS: Local 2.0.5 upgrade, coexistence, independent uninstall and data retention', flush=True)


def macos(root, old, local, cloud, version):
    import plistlib
    applications = root / 'Applications'
    applications.mkdir()
    support = Path.home() / 'Library' / 'Application Support'

    def install(dmg, name, identifier, expected_version):
        mount = root / ('mount-' + name.replace(' ', '-'))
        mount.mkdir()
        run(['hdiutil', 'attach', str(dmg), '-readonly', '-nobrowse', '-mountpoint', str(mount)])
        try:
            apps = list(mount.glob('*.app'))
            require(len(apps) == 1, 'DMG must contain exactly one application')
            with (apps[0] / 'Contents/Info.plist').open('rb') as stream:
                info = plistlib.load(stream)
            require(info['CFBundleIdentifier'] == identifier, 'Wrong macOS product identifier')
            require(info['CFBundleShortVersionString'] == expected_version, 'Wrong macOS version')
            destination = applications / (name + '.app')
            require(not destination.exists(), 'Unexpected existing application')
            run(['ditto', str(apps[0]), str(destination)])
            return destination / 'Contents/MacOS' / info['CFBundleExecutable']
        finally:
            run(['hdiutil', 'detach', str(mount)])

    old_exe = install(old, 'Zimo', 'com.zimo.app', '2.0.5')
    local_data = sentinel(support / 'com.zimo.app')
    # Model replacing the old application, while retaining its existing data.
    (applications / 'Zimo.app').rename(root / 'previous-Zimo.app')
    local_exe = install(local, 'Zimo Local', 'com.zimo.app', version)
    cloud_exe = install(cloud, 'Zimo Cloud', 'com.zimo.cloud', version)
    cloud_data = sentinel(support / 'com.zimo.cloud')
    assert_sentinel(local_data)
    live_processes([local_exe, cloud_exe])
    local_digest = digest(local_exe)
    # Deletion is confined to the fixture's exact application directory.
    cloud_app = applications / 'Zimo Cloud.app'
    require(cloud_app.resolve().parent == applications.resolve(), 'Unsafe fixture path')
    shutil.rmtree(cloud_app)
    require(digest(local_exe) == local_digest, 'Cloud removal changed Local')
    assert_sentinel(local_data)
    assert_sentinel(cloud_data)
    print('PASS: macOS application replacement, identifiers, coexistence and data retention', flush=True)


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'Must run in disposable GitHub-hosted runner')
    version = os.environ['RELEASE_VERSION']
    require(re.fullmatch(r'\d+\.\d+\.\d+', version), 'Invalid release version')
    revision = os.environ.get('BUILD_REVISION', '1')
    require(re.fullmatch(r'[1-9][0-9]*', revision), 'Invalid build revision')
    tag_suffix = '-build.' + revision if int(revision) > 1 else ''
    root = Path(tempfile.mkdtemp(prefix='zimo-installer-qa-', dir=os.environ['RUNNER_TEMP']))
    suffix = 'win-' + version + '.exe' if platform.system() == 'Windows' else 'mac-' + version + '.dmg'
    old_name = 'Zimo-win-2.0.5.exe' if platform.system() == 'Windows' else 'Zimo-mac-2.0.5.dmg'
    old = download('v2.0.5', old_name, root)
    local = download('local-v' + version + tag_suffix, 'Zimo-Local-' + suffix, root)
    cloud = download('cloud-v' + version + tag_suffix, 'Zimo-Cloud-' + suffix, root)
    print('PASS: all installer SHA256 digests match GitHub assets', flush=True)
    if platform.system() == 'Windows':
        windows(root, old, local, cloud)
    else:
        macos(root, old, local, cloud, version)


if __name__ == '__main__':
    main()
