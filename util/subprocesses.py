import subprocess
from typing import Dict


def run_subprocess(script: str, env: Dict) -> str:
    process = subprocess.run(["sh", script], text=True, env=env, stdout=subprocess.PIPE)
    if process.returncode:
        raise Exception(f"Error {process.returncode}")
    return process.stdout
