import os
import re
from enum import Enum
from typing import Optional, Dict


class Cloud(Enum):
    GCP = 0
    AWS = 1


def _root_dir():
    this_dir = os.path.dirname(os.path.realpath(__file__))
    return os.path.realpath(f"{this_dir}{os.sep}..")


class CloudRegion:
    def __init__(self, cloud: Cloud, region: str, gcp_project: Optional[str] = None):
        assert re.match(r"[a-z][a-z-]+\d$", region)
        assert (cloud == Cloud.GCP) == bool(gcp_project)

        self.cloud = cloud
        self.region = region
        self.gcp_project = gcp_project

    def script(self):
        return f"{_root_dir()}/scripts/{self.lowercase_cloud_name()}-launch.sh"

    def deletion_script(self):
        return f"{_root_dir()}/scripts/{self.lowercase_cloud_name()}-delete-instances.sh"

    def script_for_test_from_region(self):
        return f"{_root_dir()}/scripts/do-one-test-from-{self.lowercase_cloud_name()}.sh"

    def __repr__(self):
        return f"{self.cloud.name}{self.region}"

    def env(self) -> Dict[str, str]:
        return {"PROJECT_ID": self.gcp_project} if self.cloud == Cloud.GCP else {}

    def lowercase_cloud_name(self):
        return self.cloud.name.lower()

    def __eq__(self, other):
        return (
            self.region == other.region
            and self.cloud == other.cloud
            and self.gcp_project == other.gcp_project
        )
