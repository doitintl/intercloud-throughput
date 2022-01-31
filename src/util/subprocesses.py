import subprocess
from typing import Dict


def run_subprocess(script: str, env: Dict) -> str:
    process = subprocess.run([script], text=True, env=env, stdout=subprocess.PIPE)
    if process.returncode:
        raise ChildProcessError(f"Error {process.returncode}")
    return process.stdout
