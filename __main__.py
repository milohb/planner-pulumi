"""Create static gcp resources for project"""

import pulumi as plm
import pulumi_gcp as gcp
from pulumi import CustomTimeouts
from pulumi_gcp.config import project
from pulumi_kubernetes import Provider
from pulumi_kubernetes.apiextensions import CustomResource
from pulumi_kubernetes.apps.v1 import Deployment, DeploymentSpecArgs, DeploymentStrategyArgs, \
    RollingUpdateDeploymentArgs
from pulumi_kubernetes.batch.v1 import JobSpecArgs, CronJob, CronJobSpecArgs, JobTemplateSpecArgs
from pulumi_kubernetes.core.v1 import Service, PodTemplateSpecArgs, PodSpecArgs, ContainerArgs, ServiceSpecArgs, \
    ServicePortArgs, ConfigMap, VolumeMountArgs, EnvVarArgs, ContainerPortArgs, VolumeArgs, ConfigMapVolumeSourceArgs, \
    ProbeArgs, EmptyDirVolumeSourceArgs
from pulumi_kubernetes.core.v1.outputs import ExecAction, HTTPGetAction
from pulumi_kubernetes.meta.v1 import LabelSelectorArgs, ObjectMetaArgs
from pulumi_kubernetes.networking.v1 import Ingress, IngressSpecArgs, IngressBackendArgs, IngressServiceBackendArgs, \
    ServiceBackendPortArgs, IngressRuleArgs, HTTPIngressPathArgs, HTTPIngressRuleValueArgs

import modules.constants as const
import modules.functions as fun
import modules.storage as storage

cfg = plm.Config()

# use preemptible nodes during test
PREEMPTIBLE_POOL = True  # use preemptible in tests

# configure static external ip
# disabled because of pulumi bug
# planner_global_ip = GlobalAddress('planner-global-ip',
#                                   name='planner-global-ip',
#                                   project=const.GCE_PROJECT,
#                                   address_type='EXTERNAL',
#                                   ip_version='IPV4',
#                                   network_tier=const.GCE_NETWORK_TIER,
#                                   )
global_ip_name = 'planner-global-ip'

# certificate for https
ingress_ssl_cert = CustomResource('ingress-ssl-cert',
                                  api_version=const.K8S_API_VERSION,
                                  kind='ManagedCertificate',
                                  metadata=ObjectMetaArgs(
                                      name=const.INGRESS_CERT_NAME
                                  ),
                                  spec={'domains': [const.PLANNER_DOMAIN]}
                                  )

# redirect http to https
http_redirect = CustomResource('http-redirect',
                               api_version='networking.gke.io/v1beta1',
                               kind='FrontendConfig',
                               metadata=ObjectMetaArgs(
                                   name='http-to-https'
                               ),
                               spec={'redirectToHttps': {'enabled': True}}
                               )

# create gce cluster for kubernetes
planner_cluster = gcp.container.Cluster('planner-cluster',
                                        min_master_version=const.K8S_VERSION,
                                        initial_node_count=const.NODE_COUNT,
                                        remove_default_node_pool=True,
                                        addons_config=gcp.container.ClusterAddonsConfigArgs(
                                            http_load_balancing=gcp.container.ClusterAddonsConfigHttpLoadBalancingArgs(
                                                disabled=False
                                            )
                                        ))

# create primary node pool on gce
primary_node_pool = gcp.container.NodePool('primary-node-pool',
                                           cluster=planner_cluster.name,
                                           node_count=const.NODE_COUNT,
                                           node_config=gcp.container.NodePoolNodeConfigArgs(
                                               preemptible=PREEMPTIBLE_POOL,
                                               machine_type=const.NODE_MACHINES,
                                               oauth_scopes=[
                                                   'https://www.googleapis.com/auth/compute',
                                                   'https://www.googleapis.com/auth/devstorage.read_write',
                                                   'https://www.googleapis.com/auth/logging.write',
                                                   'https://www.googleapis.com/auth/monitoring'
                                               ],
                                           ), )

# generate a kubeconfig for gke
cluster_info = plm.Output.all(planner_cluster.name, planner_cluster.endpoint, planner_cluster.master_auth)
cluster_config = cluster_info.apply(
    lambda info: """apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: {0}
    server: https://{1}
  name: {2}
contexts:
- context:
    cluster: {2}
    user: {2}
  name: {2}
current-context: {2}
kind: Config
preferences: {{}}
users:
- name: {2}
  user:
    auth-provider:
      config:
        cmd-args: config config-helper --format=json
        cmd-path: gcloud
        expiry-key: '{{.credential.token_expiry}}'
        token-key: '{{.credential.access_token}}'
      name: gcp
""".format(info[2]['cluster_ca_certificate'], info[1], '{0}_{1}_{2}'.format(project, const.GCE_ZONE, info[0]))
)

# build gke cluster provider
cluster_provider = Provider('gke_k8s_provider', kubeconfig=cluster_config)

# create kubernetes services
# svc for digitransit-ui
digitransit_svc = Service('digitransit-svc',
                          spec=ServiceSpecArgs(
                              type='NodePort',
                              selector=const.DIGITRANSIT_LABEL,
                              ports=[ServicePortArgs(port=const.DIGITRANSIT_PORT,
                                                     name=const.DIGITANSIT_PORT_NAME)],
                          ),
                          opts=plm.ResourceOptions(provider=cluster_provider))

# svc for open trip planner engine
otp_svc = Service('otp-svc',
                  spec=ServiceSpecArgs(
                      type='NodePort',
                      selector=const.OTP_WORKER_LABEL,
                      ports=[ServicePortArgs(port=const.OTP_PORT)]
                  ),
                  opts=plm.ResourceOptions(provider=cluster_provider))

# svc for photon geocoding
photon_svc = Service('photon-svc',
                     spec=ServiceSpecArgs(
                         type='NodePort',
                         selector=const.PHOTON_LABEL,
                         ports=[ServicePortArgs(
                             port=const.PHOTON_PORT)]
                     ),
                     opts=plm.ResourceOptions(provider=cluster_provider))

# svc for pelias photon adapter
pelias_svc = Service('pelias-svc',
                     spec=ServiceSpecArgs(
                         type='NodePort',
                         selector=const.PELIAS_LABEL,
                         ports=[ServicePortArgs(port=const.PELIAS_PORT)]
                     ),
                     opts=plm.ResourceOptions(provider=cluster_provider))

# svc for tileserver-gl
tileserver_svc = Service('tileserver-svc',
                         spec=ServiceSpecArgs(
                             type='NodePort',
                             selector=const.TILESERVER_LABEL,
                             ports=[ServicePortArgs(
                                 port=const.TILESERVER_PORT)],
                         ),
                         opts=plm.ResourceOptions(provider=cluster_provider))

# create firewall rules to access kubernetes network
planner_firewall_rules = gcp.compute.Firewall('planner-firewall-rules',
                                              description='allow http(s) and needed service ports',
                                              network='default',
                                              allows=[
                                                  gcp.compute.FirewallAllowArgs(
                                                      protocol='tcp',
                                                      ports=['443', '80',
                                                             digitransit_svc.spec.apply(
                                                                 lambda p: p.ports[0]['node_port']),
                                                             otp_svc.spec.apply(
                                                                 lambda p: p.ports[0]['node_port']),
                                                             tileserver_svc.spec.apply(
                                                                 lambda p: p.ports[0]['node_port']),
                                                             photon_svc.spec.apply(
                                                                 lambda p: p.ports[0]['node_port']),
                                                             pelias_svc.spec.apply(
                                                                 lambda p: p.ports[0]['node_port']),
                                                             ])])

# the ingress defines all routes from the external ip to the k8s services
planner_ingress = Ingress('planner-ingress',
                          metadata=ObjectMetaArgs(
                              annotations={
                                  'kubernetes.io/ingress.global-static-ip-name': global_ip_name,
                                  'networking.gke.io/managed-certificates': const.INGRESS_CERT_NAME,
                                  'kubernetes.io/ingress.class': 'gce'},
                          ),
                          spec=IngressSpecArgs(
                              default_backend=IngressBackendArgs(
                                  service=IngressServiceBackendArgs(
                                      name=digitransit_svc.metadata.name,
                                      port=ServiceBackendPortArgs(
                                          number=const.DIGITRANSIT_PORT))),
                              rules=[
                                  IngressRuleArgs(
                                      http=HTTPIngressRuleValueArgs(
                                          paths=[
                                              # routing for otp
                                              HTTPIngressPathArgs(
                                                  backend=IngressBackendArgs(
                                                      service=IngressServiceBackendArgs(
                                                          name=otp_svc.metadata.name,
                                                          port=ServiceBackendPortArgs(
                                                              number=const.OTP_PORT))),
                                                  path='/otp/*',
                                                  path_type='ImplementationSpecific'),
                                              # routing for tileserver
                                              HTTPIngressPathArgs(
                                                  backend=IngressBackendArgs(
                                                      service=IngressServiceBackendArgs(
                                                          name=tileserver_svc.metadata.name,
                                                          port=ServiceBackendPortArgs(
                                                              number=const.TILESERVER_PORT))),
                                                  path='/styles/osmbright/*',
                                                  path_type='ImplementationSpecific'
                                              ),
                                              # routing rule for pelias geocoding
                                              HTTPIngressPathArgs(
                                                  backend=IngressBackendArgs(
                                                      service=IngressServiceBackendArgs(
                                                          name=pelias_svc.metadata.name,
                                                          port=ServiceBackendPortArgs(
                                                              number=const.PELIAS_PORT))),
                                                  path='/v1/*',
                                                  path_type='ImplementationSpecific'
                                              )]))]),
                          opts=plm.ResourceOptions(depends_on=[ingress_ssl_cert]))

# open trip planner routing engine
otp_config_map = ConfigMap("otp-worker-config",
                           data={
                               'build-config.json': storage.build_config,
                               "otp-config.json": fun.read_config_file('otp-config.json', const.OTP_CONFIG_FOLDER),
                               "router-config.json": fun.read_config_file('router-config.json',
                                                                          const.OTP_CONFIG_FOLDER)
                           },
                           opts=plm.ResourceOptions(provider=cluster_provider))

otp_worker = Deployment('otp-worker',
                        spec=DeploymentSpecArgs(
                            selector=LabelSelectorArgs(match_labels=const.OTP_WORKER_LABEL),
                            replicas=2,
                            template=PodTemplateSpecArgs(
                                metadata=ObjectMetaArgs(
                                    labels=const.OTP_WORKER_LABEL,),
                                spec=PodSpecArgs(
                                    containers=[fun.get_otp_container_args(name='otp-worker',
                                                                           java_options='-Xmx8G',
                                                                           cmd_args=['--load',
                                                                                     const.OTP_MOUNT_PATH])],
                                    volumes=[VolumeArgs(
                                        name=const.OTP_MOUNT_NAME,
                                        config_map=ConfigMapVolumeSourceArgs(
                                            name=otp_config_map.metadata.name,
                                        ))])),
                            strategy=DeploymentStrategyArgs(
                                rolling_update=RollingUpdateDeploymentArgs(
                                    max_surge=1)
                            )),
                        opts=plm.ResourceOptions(provider=cluster_provider))

# digitransit-ui frontend
digitransit_ui = Deployment('digitransit',
                            spec=DeploymentSpecArgs(
                                selector=LabelSelectorArgs(match_labels=const.DIGITRANSIT_LABEL),
                                replicas=1,
                                template=PodTemplateSpecArgs(
                                    metadata=ObjectMetaArgs(labels=const.DIGITRANSIT_LABEL),
                                    spec=PodSpecArgs(
                                        containers=[ContainerArgs(
                                            name='digitransit',
                                            image=const.DIGITRANSIT_IMAGE,
                                            ports=[ContainerPortArgs(container_port=8080)],
                                            env=[
                                                EnvVarArgs(
                                                    name='OTP_URL',
                                                    value=const.OTP_URL, ),
                                                EnvVarArgs(
                                                    name='CONFIG',
                                                    value='planner'),
                                                EnvVarArgs(
                                                    name='MAP_URL',
                                                    value=const.MAP_URL,
                                                ),
                                                EnvVarArgs(
                                                    name='GEOCODING_BASE_URL',
                                                    value=const.GEOCODING_URL,
                                                )
                                            ],
                                            command=['/usr/local/bin/yarn'],
                                            args=['run', 'start'],
                                            liveness_probe=ProbeArgs(
                                                initial_delay_seconds=60,
                                                exec_=ExecAction(
                                                    command=['ls'],
                                                )))]))))


# geocoding: photon and pelias-photon-adapter
photon = Deployment('photon',
                    spec=DeploymentSpecArgs(
                        selector=LabelSelectorArgs(match_labels=const.PHOTON_LABEL),
                        replicas=1,
                        template=PodTemplateSpecArgs(
                            metadata=ObjectMetaArgs(
                                labels=const.PHOTON_LABEL),
                            spec=PodSpecArgs(
                                containers=[ContainerArgs(
                                    name='photon-geocoding',
                                    image=const.PHOTON_IMAGE,
                                    volume_mounts=[VolumeMountArgs(
                                        mount_path='/usr/local/photon/datadir',
                                        name=const.PHOTON_MOUNT_NAME,
                                        read_only=False
                                    )],
                                    command=['/bin/sh', '-c'],
                                    args=['cd /usr/local/photon; ln -s datadir/photon_data/ . ; '
                                          'java -jar photon-0.3.5.jar']
                                )],
                                volumes=[VolumeArgs(
                                    name=const.PHOTON_MOUNT_NAME,
                                    empty_dir=EmptyDirVolumeSourceArgs()
                                )],
                                init_containers=[ContainerArgs(
                                    name='initphoton',
                                    image=const.INITCONTAINER_IMG,
                                    volume_mounts=[VolumeMountArgs(
                                        mount_path='/datadir',
                                        name=const.PHOTON_MOUNT_NAME,
                                        read_only=False
                                    )],
                                    command=['/bin/sh', '-c'],
                                    args=[plm.Output.concat('gsutil cp ', storage.photon_data_bucket_url,
                                                            ' /datadir/archive.7z ; cd /datadir ;'
                                                            ' 7z x archive.7z ; echo done ; rm archive.7z')]
                                )]))),
                    opts=plm.ResourceOptions(custom_timeouts=CustomTimeouts(create='40m')))

pelias_adapter = Deployment('pelias-adapter',
                            spec=DeploymentSpecArgs(
                                selector=LabelSelectorArgs(match_labels=const.PELIAS_LABEL),
                                replicas=1,
                                template=PodTemplateSpecArgs(
                                    metadata=ObjectMetaArgs(labels=const.PELIAS_LABEL),
                                    spec=PodSpecArgs(
                                        containers=[ContainerArgs(
                                            name='pelias-adapter',
                                            image=const.PELIAS_IMAGE,
                                            ports=[ContainerPortArgs(container_port=const.PELIAS_PORT)],
                                            env=[
                                                EnvVarArgs(
                                                    name='PORT',
                                                    value=str(const.PELIAS_PORT)),
                                                EnvVarArgs(
                                                    name='PHOTON_URL',
                                                    value=plm.Output.concat('http://', photon_svc.spec.cluster_ip,
                                                                            ':', str(const.PHOTON_PORT))
                                                )
                                            ],
                                            liveness_probe=ProbeArgs(
                                                http_get=HTTPGetAction(
                                                    port=const.PELIAS_PORT,
                                                    path='/v1/search'
                                                )))]))))


# tileserver
tileserver = Deployment('tileserver',
                        spec=DeploymentSpecArgs(
                            selector=LabelSelectorArgs(match_labels=const.TILESERVER_LABEL),
                            replicas=1,
                            template=PodTemplateSpecArgs(
                                metadata=ObjectMetaArgs(
                                    labels=const.TILESERVER_LABEL),
                                spec=PodSpecArgs(
                                    containers=[ContainerArgs(
                                        name='tileserver',
                                        image=const.TILESERVER_IMAGE,
                                        ports=[ContainerPortArgs(container_port=const.TILESERVER_PORT)],
                                        volume_mounts=[
                                            VolumeMountArgs(
                                                mount_path='/data',
                                                name=const.TILESERVER_CFG_VOLUME,
                                                read_only=True),
                                        ],
                                        command=['/app/docker-entrypoint.sh'],
                                        args=['-p', str(const.TILESERVER_PORT)]
                                    )],
                                    init_containers=[ContainerArgs(
                                        name='inittileserver',
                                        image=const.INITCONTAINER_IMG,
                                        volume_mounts=[VolumeMountArgs(
                                            mount_path='/datadir',
                                            name=const.TILESERVER_CFG_VOLUME,
                                            read_only=False
                                        )],
                                        command=['/bin/sh', '-c'],
                                        args=[plm.Output.concat('gsutil cp ', storage.tileserver_data_bucket_url,
                                                                ' /datadir/archive.7z ; cd /datadir ;'
                                                                ' 7z x archive.7z ; echo done ; rm archive.7z')]
                                    )],
                                    volumes=[
                                        VolumeArgs(
                                            name=const.TILESERVER_CFG_VOLUME,
                                            empty_dir=EmptyDirVolumeSourceArgs())]
                                ))))


# cron jobs to renew gtfs data each night
# get new gtfs data
update_gtfs_cmd_arg = plm.Output.concat('curl -L ', cfg.get_secret('connect_gtfs_url'),
                                        ' | gsutil cp - ', storage.gtfs_data_bucket_url)
update_gtfs = CronJob('update-gtfs-data',
                      spec=CronJobSpecArgs(
                          # time in UTC
                          schedule='12 1 * * *',
                          concurrency_policy='Forbid',
                          job_template=JobTemplateSpecArgs(
                              spec=JobSpecArgs(
                                  template=PodTemplateSpecArgs(
                                      spec=PodSpecArgs(
                                          restart_policy='Never',
                                          containers=[ContainerArgs(
                                              name='gtfs-updater',
                                              image=const.GCE_SDK_IMAGE,
                                              command=['/bin/sh', '-c'],
                                              args=[update_gtfs_cmd_arg],
                                          )]))))))


# build new otp graph
update_graph = CronJob('update-otp-graph',
                       spec=CronJobSpecArgs(
                           # time in UTC
                           schedule='27 1 * * *',
                           concurrency_policy='Forbid',
                           job_template=JobTemplateSpecArgs(
                               spec=JobSpecArgs(
                                   template=PodTemplateSpecArgs(
                                       spec=PodSpecArgs(
                                           restart_policy='Never',
                                           containers=[
                                               fun.get_otp_container_args(name='otp-builder',
                                                                          java_options='-Xmx16G',
                                                                          cmd_args=['--build', '--save',
                                                                                    const.OTP_MOUNT_PATH],
                                                                          otp_type='builder')
                                           ],
                                           volumes=[VolumeArgs(
                                               name=const.OTP_MOUNT_NAME,
                                               config_map=ConfigMapVolumeSourceArgs(
                                                   name=otp_config_map.metadata.name,
                                               ))])),
                                   active_deadline_seconds=1800,
                                   ttl_seconds_after_finished=180,
                               ))),
                       opts=plm.ResourceOptions(custom_timeouts=CustomTimeouts(create='20m')))

