import pulumi as plm
import pulumi_gcp as gcp
import modules.constants as const
import modules.functions as fun

# storage for otp files
otp_file_bucket = gcp.storage.Bucket('otp-storage',
                                     location=const.GCE_REGION,
                                     uniform_bucket_level_access=True
                                     )

# upload graph for testing otp
otp_graph = gcp.storage.BucketObject('otp-graph',
                                     bucket=otp_file_bucket,
                                     content_type='application/octet-stream',
                                     source=plm.FileAsset(f'files/blobs/{const.OTP_GRAPH_FILE}'),
                                     opts=plm.ResourceOptions(depends_on=[otp_file_bucket],
                                                              ignore_changes=['source', 'detectMd5hash']))

# storage for connect gtfs data
gtfs_data = gcp.storage.BucketObject('gtfs-data',
                                     bucket=otp_file_bucket,
                                     content_type='application/zip',
                                     name='connect-gtfs.zip',
                                     source=plm.FileAsset(f'files/blobs/{const.CONNECT_GTFS_FILE}'),
                                     opts=plm.ResourceOptions(ignore_changes=['source', 'detectMd5hash',
                                                                              'contentType']))

# storage for osm pbf data
osm_data = gcp.storage.BucketObject('osm_data',
                                    bucket=otp_file_bucket,
                                    content_type='application/octet-stream',
                                    source=plm.FileAsset(f'files/blobs/{const.OSM_DATA_FILE}'),
                                    opts=plm.ResourceOptions(ignore_changes=['source', 'detectMd5hash']))

# storage for photon elasticsearch data (compressed)
photon_data = gcp.storage.BucketObject('photon_data',
                                       bucket=otp_file_bucket,
                                       content_type='application/octet-stream',
                                       source=plm.FileAsset(f'files/blobs/{const.PHOTON_ES_FILE}'),
                                       opts=plm.ResourceOptions(ignore_changes=['source', 'detectMd5hash']))

# storage for photon elasticsearch data (compressed)
tileserver_data = gcp.storage.BucketObject('tileserver-data',
                                           bucket=otp_file_bucket,
                                           content_type='application/octet-stream',
                                           source=plm.FileAsset(f'files/blobs/{const.TILESERVER_DATA_FILE}'),
                                           # opts=plm.ResourceOptions(ignore_changes=['source', 'detectMd5hash']))
                                           )

# build google cloud storage urls
otp_graph_bucket_url = plm.Output.concat("gs://", otp_file_bucket.name, "/", otp_graph.name)
gtfs_data_bucket_url = plm.Output.concat("gs://", otp_file_bucket.name, "/", gtfs_data.output_name)
osm_data_bucket_url = plm.Output.concat("gs://", otp_file_bucket.name, "/", osm_data.name)
photon_data_bucket_url = plm.Output.concat("gs://", otp_file_bucket.name, "/", photon_data.name)
tileserver_data_bucket_url = plm.Output.concat("gs://", otp_file_bucket.name, "/", tileserver_data.name)

# update build-config.json with dynamic values
build_config = plm.Output.all(otp_graph_bucket_url, gtfs_data_bucket_url, osm_data_bucket_url).apply(
    lambda url: fun.read_config_file('build-config.json', const.OTP_CONFIG_FOLDER).
        replace('PLACEHOLDER_GRAPH_URI', url[0]).
        replace('PLACEHOLDER_GTFS_URI', url[1]).
        replace('PLACEHOLDER_OSM_URI', url[2])
)
