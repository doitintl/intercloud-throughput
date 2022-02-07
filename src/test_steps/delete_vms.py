import logging
import threading

from cloud.clouds import CloudRegion, Cloud
from test_steps.create_vms import env_for_singlecloud_subprocess
from util.subprocesses import run_subprocess
from util.utils import thread_timeout, Timer


def delete_vms(run_id, regions: list[CloudRegion]):
    with Timer("delete_vms"):
        del_aws_thread = threading.Thread(
            name=f"delete-AWS", target=__delete_aws_vms, args=(run_id, regions)
        )
        del_gcp_thread = threading.Thread(
            name=f"delete-GCP", target=__delete_gcp_vms, args=(run_id, regions)
        )
        del_aws_thread.start()
        del_gcp_thread.start()
        del_aws_thread.join(timeout=thread_timeout)
        if del_aws_thread.is_alive():
            logging.info("%s timed out", del_aws_thread)
        del_gcp_thread.join(timeout=6 * 60)
        if del_gcp_thread.is_alive():
            logging.info("%s timed out", del_gcp_thread)


def __delete_aws_vms(run_id, regions):
    with Timer("__delete_aws_vms"):

        def delete_aws_vm(aws_cloud_region: CloudRegion):
            assert aws_cloud_region.cloud == Cloud.AWS, aws_cloud_region
            logging.info(
                "Will delete EC2 VMs from run-id %s in %s", run_id, aws_cloud_region
            )
            env = env_for_singlecloud_subprocess(run_id, aws_cloud_region)
            script = cloud_region.deletion_script()
            _ = run_subprocess(script, env)

        aws_regions = [r for r in regions if r.cloud == Cloud.AWS]
        del_aws_threads = []
        for cloud_region in aws_regions:
            del_one_aws_region_thread = threading.Thread(
                name=f"delete-{cloud_region}",
                target=delete_aws_vm,
                args=(cloud_region,),
            )
            del_aws_threads.append(del_one_aws_region_thread)
            del_one_aws_region_thread.start()

        for del_one_aws_region_thread in del_aws_threads:
            del_one_aws_region_thread.join(timeout=thread_timeout)
            if del_one_aws_region_thread.is_alive():
                logging.info("%s timed out", del_one_aws_region_thread)
            logging.info("Deletion %s done", del_one_aws_region_thread.name)


def __delete_gcp_vms(run_id, regions):
    with Timer("__delete_gcp_vms"):
        gcp_regions = [r for r in regions if r.cloud == Cloud.GCP]
        if gcp_regions:
            # One arbitrary region, for getting list of VMs;   deletion commands are run in sequence inside the command
            cloud_region = gcp_regions[0]
            logging.info("Will delete GCE VMs from run-id %s", run_id)
            env = env_for_singlecloud_subprocess(run_id, cloud_region)
            _ = run_subprocess(cloud_region.deletion_script(), env)
        else:
            # No gcp, nothing to delete
            pass
