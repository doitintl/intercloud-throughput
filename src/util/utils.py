import datetime
import logging
import math
import os
import random
import string
from threading import Lock
from time import time
from typing import Union, Iterable, Any

import numpy as np

from util import subprocesses

__gcp_default = None

thread_timeout = 5 * 60


def init_logger():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
        datefmt="%H:%M:%S",
    )


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


def chunks(lst: list, n: int):
    """Yield successive n-sized chunks from lst."""
    if n == math.inf:
        # One chunk
        yield lst
    else:
        for i in range(0, len(lst), n):
            yield lst[i : i + n]


def random_id():
    vowel = "aeiou"
    cons = list(filter(lambda l: l not in vowel, string.ascii_lowercase))
    k = 3
    return __random_id(vowel, cons, k)


def random_id2():
    letters = string.ascii_lowercase
    digits = "0123456789"
    k = 3
    return __random_id(letters, digits, k)


def __random_id(chars1, chars2, k):
    let = random.choices(chars1, k=k)
    dig = random.choices(chars2, k=k)
    return "".join(["".join(i) for i in zip(let, dig)])


__gcp_default_project_lock = Lock()


def gcp_default_project():
    global __gcp_default
    if not __gcp_default:
        __gcp_default_project_lock.acquire()
        try:
            if not __gcp_default:
                env = {"PATH": os.environ["PATH"]}
                __gcp_default = subprocesses.run_subprocess(
                    "./scripts/gcp-project.sh", env=env
                )
                if __gcp_default.endswith("\n"):  # It does have this \n
                    __gcp_default = __gcp_default[:-1]
        finally:
            __gcp_default_project_lock.release()
    return __gcp_default


def dedup(seq):
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]


class Timer(object):
    def __init__(self, description):
        self.description = description

    def __enter__(self):
        self.start = time()

    def __exit__(self, type_, value, traceback):
        self.end = time()
        logging.info(f"{self.description}: {round(self.end - self.start, 1)} s")


def date_s():
    return datetime.datetime.utcnow().isoformat() + "Z"


def parse_infinity(a: str) -> Union[int, float]:
    if a == "inf" or a == math.inf:
        return math.inf
    else:
        return int(a)


def geo_mean(iterable):
    a = np.array(iterable)
    return a.prod() ** (1.0 / len(a))


def shallow_flatten(lst: Union[list[Any], tuple[Any]]) -> Iterable[Any]:
    """Deep-Flatten a list using generators comprehensions."""
    """Flatten a list using generators comprehensions.
        Returns a flattened version of list lst.
    """

    for sublist in lst:
        if isinstance(sublist, (list, tuple)):
            for item in sublist:
                yield item
        else:
            yield sublist


print(list(shallow_flatten([(1, [1, [5, 6]]), (3, 4), (5, (7, 8))])))
