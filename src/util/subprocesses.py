import subprocess


def run_subprocess(script: str, env: dict) -> str:
    process = subprocess.run([script], text=True, env=env, stdout=subprocess.PIPE)
    if process.returncode:
        raise ChildProcessError(f"Error {process.returncode}")
    else:
        return process.stdout
