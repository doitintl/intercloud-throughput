import re
from enum import Enum
from typing import Optional, Dict

from util import utils
from util.utils import gcp_default_project


class Cloud(Enum):
    GCP = "GCP"
    AWS = "AWS"


class CloudRegion:
    def __init__(
        self,
        cloud: Cloud,
        region: str,
        gcp_project: Optional[str] = None,
        *,
        lat: float = None,
        long: float = None,
    ):
        assert re.match(r"[a-z][a-z-]+\d$", region)
        if Cloud.GCP and not gcp_project:
            gcp_project = gcp_default_project()
        self.lat = lat
        self.long = long
        self.cloud = cloud
        self.region = region
        self.gcp_project = gcp_project

    def script(self):
        return f"{utils.root_dir()}/scripts/{self.lowercase_cloud_name()}-launch.sh"

    def deletion_script(self):
        return f"{utils.root_dir()}/scripts/{self.lowercase_cloud_name()}-delete-instances.sh"

    def script_for_test_from_region(self):
        return f"{utils.root_dir()}/scripts/do-one-test-from-{self.lowercase_cloud_name()}.sh"

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
