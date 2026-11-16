"""Attach the single persistent disk, drop root, and supervise API + daily worker."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path('/app')
DISK = Path(os.environ.get('FLAMESEEK_STORAGE', '/var/data'))


def main():
    for relative in ('data', 'dataset', 'outputs', 'backend/cache'):
        target = DISK / relative
        target.mkdir(parents=True, exist_ok=True)
        os.chown(target, 10001, 10001)
        link = ROOT / relative
        if not link.is_symlink():
            if link.exists():
                raise RuntimeError(f'Refusing to hide existing directory: {link}')
            link.symlink_to(target, target_is_directory=True)
    os.environ['FLAMESEEK_PIPELINE_PYTHON'] = sys.executable
    os.setgid(10001)
    os.setuid(10001)
    os.chdir(ROOT)
    children = []
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        children.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'deploy.web:app',
            '--host', '0.0.0.0', '--port', os.environ.get('PORT', '10000'), '--workers', '1'], start_new_session=True))
        if os.environ.get('FLAMESEEK_DAILY_ENABLED', 'false').lower() == 'true':
            children.append(subprocess.Popen([sys.executable, 'deploy/daily_worker.py'], start_new_session=True))
        while not stopping and all(child.poll() is None for child in children):
            time.sleep(1)
    finally:
        failed = not stopping
        stop()
        deadline = time.monotonic() + 20
        for child in children:
            try:
                child.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
