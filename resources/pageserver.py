# Creates a Kubernetes deployment for the pageserver using the kubernetes python client
import kopf
import kubernetes
from kubernetes.client import V1ResourceRequirements, ApiException


def deploy_pageserver(
                      kube_client: kubernetes.client.ApiClient,
                      namespace: str,
                      resources: V1ResourceRequirements,
                      remote_storage_endpoint: str,
                      remote_storage_bucket_name: str,
                      remote_storage_bucket_region: str,
                      remote_storage_prefix_in_bucket: str,
                      image_pull_policy: str = "IfNotPresent",
                      image: str = "neondatabase/neon"):
    """
    Deploys the pageserver resources to the kubernetes cluster
    :param kube_client: kubernetes api client
    :param namespace: namespace to deploy to
    :param resources: resource requirements for the pageserver
    :param image_pull_policy: image pull policy for the pageserver container image (default: IfNotPresent)
    :param image: pageserver container image (default: neondatabase/neon)
    :return: if successful, returns None, otherwise returns an ApiException
    """
    deployment = pageserver_statefulset(namespace, resources, image_pull_policy, image)
    kopf.adopt(deployment)
    service = pageserver_service(namespace)
    kopf.adopt(service)
    configmap = pageserver_configmap(namespace,remote_storage_endpoint,remote_storage_bucket_name,remote_storage_bucket_region,remote_storage_prefix_in_bucket)
    kopf.adopt(configmap)
    pvc = pageserver_pvc(namespace)
    kopf.adopt(pvc)

    apps_client = kubernetes.client.AppsV1Api(kube_client)
    core_client = kubernetes.client.CoreV1Api(kube_client)
    try:
        apps_client.create_namespaced_stateful_set(namespace=namespace, body=deployment)
        core_client.create_namespaced_service(namespace=namespace, body=service)
        core_client.create_namespaced_config_map(namespace=namespace, body=configmap)
        core_client.create_namespaced_persistent_volume_claim(namespace=namespace, body=pvc)
    except ApiException as e:
        print("Exception when calling Api: %s\n" % e)

def update_pageserver(
                        kube_client: kubernetes.client.ApiClient,
                        namespace: str,
                        resources: V1ResourceRequirements,
                        image_pull_policy: str = "IfNotPresent",
                        image: str = "neondatabase/neon"):
    """
    Updates the pageserver resources in the kubernetes cluster
    :param kube_client: kubernetes api client
    :param namespace: namespace to update in
    :param resources: resource requirements for the pageserver
    :param image_pull_policy: image pull policy for the pageserver container image (default: IfNotPresent)
    :param image: pageserver container image (default: neondatabase/neon)
    :return: if successful, returns None, otherwise returns an ApiException
    """
    deployment = pageserver_statefulset(namespace, resources, image_pull_policy, image)
    kopf.adopt(deployment)
    service = pageserver_service(namespace)
    kopf.adopt(service)
    configmap = pageserver_configmap(namespace)
    kopf.adopt(configmap)
    pvc = pageserver_pvc(namespace)
    kopf.adopt(pvc)

    apps_client = kubernetes.client.AppsV1Api(kube_client)
    core_client = kubernetes.client.CoreV1Api(kube_client)
    try:
        apps_client.patch_namespaced_stateful_set(namespace=namespace, name="pageserver", body=deployment)
        core_client.patch_namespaced_service(namespace=namespace, name="pageserver", body=service)
        core_client.patch_namespaced_config_map(namespace=namespace, name="pageserver", body=configmap)
        core_client.patch_namespaced_persistent_volume_claim(namespace=namespace, name="pageserver", body=pvc)
    except ApiException as e:
        print("Exception when calling Api: %s\n" % e)

def delete_pageserver(
                        kube_client: kubernetes.client.ApiClient,
                        namespace: str,
):
    """
    Deletes the pageserver resources from the kubernetes cluster
    :param kube_client: kubernetes api client
    :param namespace: namespace to delete from
    :return: if successful, returns None, otherwise returns an ApiException
    """
    apps_client = kubernetes.client.AppsV1Api(kube_client)
    core_client = kubernetes.client.CoreV1Api(kube_client)
    try:
        apps_client.delete_namespaced_stateful_set(namespace=namespace, name="pageserver")
        core_client.delete_namespaced_service(namespace=namespace, name="pageserver")
        core_client.delete_namespaced_config_map(namespace=namespace, name="pageserver")
        core_client.delete_namespaced_persistent_volume_claim(namespace=namespace, name="pageserver")
    except ApiException as e:
        print("Exception when calling Api: %s\n" % e)

def pageserver_statefulset(namespace: str,
                           resources: V1ResourceRequirements,
                           image_pull_policy: str,
                           image: str) -> kubernetes.client.V1StatefulSet:
    """
    Creates a kubernetes statefulset for the pageserver
    :param namespace: namespace to deploy to
    :param resources: resource requirements for the pageserver
    :param image_pull_policy: image pull policy for the pageserver container image (default: IfNotPresent)
    :param image: default pageserver container image (default: neondatabase/neon)
    :return: returns a kubernetes statefulset object
    """
    container = kubernetes.client.V1Container(
        name="pageserver",
        image=image,
        image_pull_policy=image_pull_policy,
        ports=[
            kubernetes.client.V1ContainerPort(container_port=9898),
            kubernetes.client.V1ContainerPort(container_port=6400),
        ],
        #TODO: inject the id of the pod into the container
        command=[
            "pageserver", "-D", "/data/.neon/", "-c", "id=$POD_INDEX", "-c",
            "broker_endpoint='http://storage-broker." + namespace + ".svc.cluster.local:50051'"
        ],
        env=[
            # NOTE: Only works with kubernetes 1.28+
            kubernetes.client.V1EnvVar(
                name="POD_INDEX",
                value_from=kubernetes.client.V1EnvVarSource(
                    field_ref=kubernetes.client.V1ObjectFieldSelector(
                        field_path="metadata.labels['app.kubernetes.io/pod-index']",
                    ),
                ),
            ),
            # Add BROKER_ENDPOINT, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
            kubernetes.client.V1EnvVar(
                name="BROKER_ENDPOINT",
                value="http://storage-broker." + namespace + ".svc.cluster.local:50051",
            ),
            kubernetes.client.V1EnvVar(
                name="AWS_ACCESS_KEY_ID",
                value_from=kubernetes.client.V1EnvVarSource(
                    secret_key_ref=kubernetes.client.V1SecretKeySelector(
                        key="AWS_ACCESS_KEY_ID",
                        name="neon-storage-credentials",
                    ),
                ),
            ),
            kubernetes.client.V1EnvVar(
                name="AWS_SECRET_ACCESS_KEY",
                value_from=kubernetes.client.V1EnvVarSource(
                    secret_key_ref=kubernetes.client.V1SecretKeySelector(
                        key="AWS_SECRET_ACCESS_KEY",
                        name="neon-storage-credentials",
                    ),
                ),
            ),
        ],
        volume_mounts=[
            kubernetes.client.V1VolumeMount(
                name="pageserver-data-volume",
                mount_path="/data/.neon/",
            ),
        ],
        resources=resources,
    )

    template = kubernetes.client.V1PodTemplateSpec(
        metadata=kubernetes.client.V1ObjectMeta(
            labels={"app": "pageserver"},
        ),
        spec=kubernetes.client.V1PodSpec(
            containers=[container],
            volumes=[
                kubernetes.client.V1Volume(
                    name="pageserver-config-volume",
                    config_map=kubernetes.client.V1ConfigMapVolumeSource(
                        name="pageserver-config",
                        items=[
                            kubernetes.client.V1KeyToPath(
                                key="pageserver.toml",
                                path="pageserver.toml",
                            )]
                    )),
                kubernetes.client.V1Volume(
                    name="pageserver-data-volume",
                    persistent_volume_claim=kubernetes.client.V1PersistentVolumeClaimVolumeSource(
                        claim_name="pageserver-data-volume",
                    ),
                ),
            ]
        ),
    )

    spec = kubernetes.client.V1DeploymentSpec(
        replicas=3,
        selector=kubernetes.client.V1LabelSelector(
            match_labels={"app": "pageserver"},
        ),
        template=template,
    )

    deployment = kubernetes.client.V1StatefulSet(
        api_version="apps/v1",
        kind="Deployment",
        metadata=kubernetes.client.V1ObjectMeta(
            name="pageserver",
            labels={"app": "pageserver"},
        ),
        spec=spec,
    )

    return deployment


def pageserver_service(
        namespace: str,
) -> kubernetes.client.V1Service:
    spec = kubernetes.client.V1ServiceSpec(
        selector={"app": "pageserver"},
        ports=[
            kubernetes.client.V1ServicePort(port=9898, name="http", target_port=9898),
            kubernetes.client.V1ServicePort(port=6400, name="pg", target_port=6400),
        ],
        type="ClusterIP"
    )

    service = kubernetes.client.V1Service(
        api_version="v1",
        kind="Service",
        metadata=kubernetes.client.V1ObjectMeta(
            name="pageserver",
            namespace=namespace,
            labels={"app": "pageserver"},
        ),
        spec=spec,
    )

    return service


def pageserver_configmap(
        namespace: str,
        remote_storage_endpoint: str = "http://minio:9000",
        remote_storage_bucket_name: str = "neon",
        remote_storage_bucket_region: str = "eu-north-1",
        remote_storage_prefix_in_bucket: str = "/pageserver/",
) -> kubernetes.client.V1ConfigMap:
    configmap = kubernetes.client.V1ConfigMap(
        api_version="v1",
        kind="ConfigMap",
        metadata=kubernetes.client.V1ObjectMeta(
            name="pageserver",
            namespace=namespace,
            labels={"app": "pageserver"},
        ),
        data={"pageserver.toml": f"""
listen_pg_addr = '0.0.0.0:6400'
listen_http_addr = '0.0.0.0:9898'

[remote_storage]
endpoint={remote_storage_endpoint}
bucket_name={remote_storage_bucket_name}
bucket_region={remote_storage_bucket_region}
prefix_in_bucket={remote_storage_prefix_in_bucket}
    """},
    )

    return configmap


def pageserver_pvc(
        namespace: str,
        access_modes=None,
        storage_capacity: str = "1Gi") -> kubernetes.client.V1PersistentVolumeClaim:
    if access_modes is None:
        access_modes = ["ReadWriteOnce"]
    spec = kubernetes.client.V1PersistentVolumeClaimSpec(
        access_modes=access_modes,
        resources=kubernetes.client.V1ResourceRequirements(
            requests={"storage": storage_capacity},
        ),
    )

    pvc = kubernetes.client.V1PersistentVolumeClaim(
        api_version="v1",
        kind="PersistentVolumeClaim",
        metadata=kubernetes.client.V1ObjectMeta(
            name="pageserver",
            namespace=namespace,
            labels={"app": "pageserver"},
        ),
        spec=spec,
    )

    return pvc