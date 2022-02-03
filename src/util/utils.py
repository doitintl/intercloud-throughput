import os
import random
import string
from typing import List

from util import subprocesses

__gcp_default = None

thread_timeout = 5 * 60



def set_cwd():
    previous_cwd = os.getcwd()

    parent = previous_cwd
    lst = os.listdir(parent)
    while parent != "/" and not all(
        map(lambda s: s in lst, ["scripts", "startup-scripts", "src"])
    ):
        parent = os.path.abspath(parent + "/" + "..")
        os.chdir(parent)
        lst = os.listdir(parent)
    if parent == "/":
        raise FileNotFoundError(f"Cannot find project root path from {previous_cwd}")

    _new_cwd = os.getcwd()


def chunks(lst: List, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def random_id():
    vowel = "aeiou"
    cons = list(filter(lambda l: l not in vowel, string.ascii_lowercase))
    k = 3
    consonants = random.choices(cons, k=k)
    vowels = random.choices(vowel, k=k)
    s = ["".join(i) for i in zip(consonants, vowels)]
    return "".join(s)


def gcp_default_project():
    global __gcp_default
    if not __gcp_default:
        env = {"PATH": os.environ["PATH"]}
        __gcp_default = subprocesses.run_subprocess("./scripts/gcp-project.sh", env=env)
        if __gcp_default.endswith("\n"):
            __gcp_default = __gcp_default[:-1]

    return __gcp_default


def dedup(seq):
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]
