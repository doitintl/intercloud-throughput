import os

from util import subprocesses

GCP_DFLT = None


def dedup(lst):
    ret = []
    for i in lst:
        if i not in ret:
            ret.append(i)
    return ret


def root_dir():
    this_dir = os.path.dirname(os.path.realpath(__file__))
    return os.path.realpath(f"{this_dir}{os.sep}..")


def gcp_default_project():
    global GCP_DFLT
    if not GCP_DFLT:
        env = {"PATH": os.environ["PATH"]}
        GCP_DFLT = subprocesses.run_subprocess(
            root_dir() + "/scripts/" + "gcp-project.sh", env=env
        )
        if GCP_DFLT.endswith("\n"):
            GCP_DFLT = GCP_DFLT[:-1]

    return GCP_DFLT
