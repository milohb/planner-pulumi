# helper functions
from pulumi_kubernetes.core.v1 import ContainerArgs, ContainerPortArgs, VolumeMountArgs, EnvVarArgs, ProbeArgs
from pulumi_kubernetes.core.v1.outputs import ExecAction

import modules.constants as const


def read_config_file(filename, folder='.'):
    with open(f'files/{folder}/{filename}', 'r') as config_file:
        return config_file.read()


def get_otp_container_args(name, java_options, cmd_args, otp_type='worker'):
    probe_args = None
    if otp_type == 'worker':
        # fail between 2:00 and 3:00 to restart pod
        probe_args = ProbeArgs(failure_threshold=1,
                               initial_delay_seconds=3600,
                               period_seconds=600,
                               exec_=ExecAction(
                                   command=['/bin/sh', '-c', 'exit $(test $(date +%H) -eq 4 && echo 1 || echo 0)'],
                               ))
    else:
        # don't fail
        probe_args = ProbeArgs(
            failure_threshold=1,
            initial_delay_seconds=60,
            period_seconds=600,
            exec_=ExecAction(
                command=['ls']
            )
        )

    container_args = ContainerArgs(name=name,
                                   image=const.OTP_IMAGE,
                                   ports=[ContainerPortArgs(
                                       container_port=8080)],
                                   volume_mounts=[VolumeMountArgs(
                                       mount_path=const.OTP_MOUNT_PATH,
                                       name=const.OTP_MOUNT_NAME)],
                                   env=[EnvVarArgs(
                                       name='JAVA_OPTIONS',
                                       value=java_options)],
                                   command=[const.OTP_COMMAND],
                                   args=cmd_args,
                                   liveness_probe=probe_args,
                                   )
    return container_args
