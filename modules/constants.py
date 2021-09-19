import pulumi as plm

# google cloud options
GCE_REGION = "europe-west3"
GCE_ZONE = 'europe-west-3-b'
#  network tier
GCE_NETWORK_TIER = "PREMIUM"
GCE_PROJECT = 'bachelor-thesis-otp'
PLANNER_DOMAIN = 'planner.25stunden.de'

# k8s cluster options
NODE_COUNT = 1
NODE_MACHINES = 'n2d-standard-8'
K8S_VERSION = '1.21.3-gke.900'
K8S_API_VERSION = 'networking.gke.io/v1'
INGRESS_CERT_NAME = 'planner-ssl-cert'

# docker images
OTP_IMAGE = 'milohb/otp:v210713v21'
DIGITRANSIT_IMAGE = 'milohb/digitransit:v210919'
PHOTON_IMAGE = 'milohb/photon:v210829'
INITCONTAINER_IMG = 'milohb/initcontainer:v210906'
PELIAS_IMAGE = 'mfdz/photon-pelias-adapter:9af8e59f298719566cb55a1efb0e96545d079c49'
TILESERVER_IMAGE = 'maptiler/tileserver-gl:v3.1.1'
GCE_SDK_IMAGE = 'gcr.io/google.com/cloudsdktool/cloud-sdk:352.0.0-slim'

# config for digitransit instance and environment
OTP_URL = 'https://planner.25stunden.de/otp/routers/default/'
# MAP_URL = plm.config.require_secret('maptiler_url') # external maptiler service
MAP_URL = f'https://{PLANNER_DOMAIN}/styles/osmbright/{{z}}/{{x}}/{{y}}.png'
GEOCODING_URL = f'https://{PLANNER_DOMAIN}/v1'
DIGITRANSIT_LABEL = {'app': f'digitransit-ui{plm.get_stack()}'}
DIGITRANSIT_PORT = 8080
DIGITANSIT_PORT_NAME = 'ui-port'

# config for otp instance
OTP_PORT = 8080
OTP_CONFIG_FOLDER = 'otp-configuration'
OTP_WORKER_LABEL = {'app': f'otp-worker-{plm.get_stack()}'}
CONNECT_GTFS_FILE = 'connect_gtfs.zip'
OTP_GRAPH_FILE = 'graph.obj'
OSM_DATA_FILE = 'northern_germany.osm.pbf'
OTP_MOUNT_PATH = '/var/opt/graphs'
OTP_COMMAND = '/usr/local/bin/otp'
OTP_MOUNT_NAME = 'otp-mounted-volume'

# config for tileserver instance
TILESERVER_CFG_VOLUME = 'tileserver-config'
TILESERVER_TILES_VOLUME = 'tileserver-tiles'
TILESERVER_PORT = 8095
MAPTILES_FILE = 'maptiler-germany-edu.mbtiles'
TILESERVER_LABEL = {'app': f'tileserver{plm.get_stack()}'}
TILESERVER_DATA_FILE = 'maptiler_data.7z'

# config for photon instance
PHOTON_ES_FILE = 'photon_es_data.7z'
PHOTON_LABEL = {'app': f'photon{plm.get_stack()}'}
PHOTON_MOUNT_NAME = 'photon-mounted-volume'
PHOTON_PORT = 2322

# config for pelias-adapter
PELIAS_LABEL = {'app': f'pelias{plm.get_stack()}'}
PELIAS_PORT = 8075

