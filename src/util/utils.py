import logging
import os
import random
import string

from util import subprocesses

GCP_DFLT = None


def set_cwd():

    previous_cwd=os.getcwd()

    parent=previous_cwd
    lst=os.listdir(parent)
    while parent !="/" and not all(map(lambda s: s in lst,["scripts", "startup-scripts", "src"])):
        parent=os.path.abspath(parent+"/"+"..")
        os.chdir(parent)
        lst = os.listdir(parent)
    if parent=="/":
        raise FileNotFoundError(f"Cannot find project root path from {previous_cwd}")

    new_cwd = os.getcwd()
    if previous_cwd!=new_cwd:
        logging.info("Changed dir from %s to %s", previous_cwd, new_cwd)


def random_id():
    vowel="aeiou"
    cons=list(filter( lambda l: l not in vowel,  string.ascii_lowercase))
    k=3
    consonants=random.choices(cons, k=k)
    vowels  = random.choices(vowel, k=k)
    s=[ "".join(i)  for i in list(zip(consonants, vowels))]
    return "".join(s)



def gcp_default_project():
    global GCP_DFLT
    if not GCP_DFLT:
        env = {"PATH": os.environ["PATH"]}
        GCP_DFLT = subprocesses.run_subprocess(
             "./scripts/gcp-project.sh", env=env
        )
        if GCP_DFLT.endswith("\n"):
            GCP_DFLT = GCP_DFLT[:-1]

    return GCP_DFLT
