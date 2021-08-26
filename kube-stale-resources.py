#!/usr/bin/env python

import argparse
import re
import sys

from typing import (IO, List, Tuple)

import requests
import yaml

K8sResourceIdentifier = Tuple[str, str, str, str]

HEADERS = {"Content-Type": "application/json"}

BLACKLIST_REGEXS = [
    # Kubernetes inherent blacklist (should apply to every k8s cluster out there)
    r'^.*:apps/v1:ControllerRevision:.*$',
    r'^.*:apps/v1:ReplicaSet:.*$',
    r'^.*:batch/v1:Job:.*-\d{10,}$',  # jobs created by cron jobs with unix timestamp suffix
    r'^.*:events.k8s.io/v1:Event:.*$',
    r'^.*:metrics.k8s.io/v1beta1:PodMetrics:.*$',
    # CM with CA bundle to verify kube-apiserver connections,
    # see https://github.com/kubernetes/kubernetes/blob/master/CHANGELOG/CHANGELOG-1.20.md#introducing-rootcaconfigmap
    r'^.*:v1:ConfigMap:kube-root-ca.crt$',
    r'^.*:v1:Endpoints:.*$',
    r'^.*:.*:EndpointSlice:.*$',
    r'^.*:v1:Event:.*$',
    r'^.*:v1:Pod:.*$',
    r'^.*:v1:Secret:.*-token-\S{5}$',  # secrets with token for service accounts
    r'^.*:v1:ServiceAccount:default$',
    r'^default:v1:Service:kubernetes$',
    r'^kube-node-lease:.*$',
    r'^kube-public:.*$',
    r'^kube-system:.*$',

    # GKE specific parts (should apply to every GKE-managed k8s cluster)
    # '^.*:v1:ResourceQuota:gke-resource-quotas$',
    # '^default:v1:LimitRange:limits$,
]


def get_live_namespaced_resources(url: str) -> List[K8sResourceIdentifier]:
    """
    Returns list of Kubernetes resource identifiers of namespaced resources out of the live cluster reachable at url.
    """

    result = []

    # merges https://kubernetes.io/docs/reference/using-api/#api-groups

    # legacy API group
    apiVersions = requests.get(url + '/api', headers=HEADERS).json()['versions']
    for apiVersion in apiVersions:
        apiResources = requests.get(url + '/api/' + apiVersion, headers=HEADERS).json()['resources']
        for apiResource in apiResources:
            if not ('list' in apiResource['verbs'] and apiResource['namespaced']):
                continue

            items = requests.get(url + '/api/' + apiVersion + '/' + apiResource['name'],
                                 headers=HEADERS).json()['items']
            for item in items:
                result.append(
                    (item['metadata']['namespace'], apiVersion, apiResource['kind'], item['metadata']['name']))

    # named API groups
    apiGroups = requests.get(url + '/apis', headers=HEADERS).json()['groups']
    for apiGroup in apiGroups:

        apiResources = requests.get(url + '/apis/' + apiGroup['preferredVersion']['groupVersion'],
                                    headers=HEADERS).json()['resources']
        for apiResource in apiResources:
            if not ('list' in apiResource['verbs'] and apiResource['namespaced']):
                continue

            if apiGroup['preferredVersion']['groupVersion'] == 'extensions/v1beta1' and apiResource['kind'] != 'Ingress':
                # everything else in extensions/v1beta1 should be migrated to the preferred version
                # except ingresses, see https://kubernetes.io/blog/2019/07/18/api-deprecations-in-1-16/
                continue

            items = requests.get(url + '/apis/' + apiGroup['preferredVersion']['groupVersion'] + '/' +
                                 apiResource['name'],
                                 headers=HEADERS).json()['items']
            for item in items:
                result.append((item['metadata']['namespace'], apiGroup['preferredVersion']['groupVersion'],
                               apiResource['kind'], item['metadata']['name']))

    return result


def get_target_namespaced_resources(stream: IO) -> List[K8sResourceIdentifier]:
    """
    Returns list of Kubernetes resource identifiers of namespaced resources out of the target stream.
    """
    result = []

    target_documents = list(yaml.load_all(stream, Loader=yaml.SafeLoader))
    for document in target_documents:
        if not document:
            continue
        if not 'namespace' in document['metadata']:
            continue

        result.append(
            (document['metadata']['namespace'], document['apiVersion'], document['kind'], document['metadata']['name']))

    return result


def get_compact_resource_identifiers(tuples: List[K8sResourceIdentifier]) -> List[str]:
    """
    Returns a compact, sortable string for a Kubernetes resource identifier.
    """
    return [namespace + ':' + apiVersion + ':' + kind + ':' + name for namespace, apiVersion, kind, name in tuples]


def main():
    parser = argparse.ArgumentParser(description='Utility to detect k8s configuration drift.')

    parser.add_argument('-f',
                        dest='target_manifests_file',
                        required=True,
                        help='File path (or - for stdin) to read Kubernetes manifests from for target state.')
    parser.add_argument('--url',
                        dest='k8s_apiserver_url',
                        default='http://localhost:8001',
                        help='URL of Kubernetes apiserver to retrieve live state.')
    parser.add_argument('--blacklist',
                        dest='blacklist_file',
                        help='File path to read blacklist regex entries from that will be used to filter live state.')

    args = parser.parse_args()

    blacklist_regexs: List[str] = []
    blacklist_regexs += BLACKLIST_REGEXS

    if args.blacklist_file:
        print(f'Reading blacklist file {args.blacklist_file}...')
        with open(args.blacklist_file, 'r', encoding='utf-8') as f:
            blacklist_regexs += list(filter(lambda x: not re.match(r'^\s*$', x), f.read().split('\n')))

    print('Retrieving target state...')
    if args.target_manifests_file == '-':
        target_tuples = get_target_namespaced_resources(sys.stdin)
    else:
        with open(args.target_manifests_file, 'r', encoding='utf-8') as f:
            target_tuples = get_target_namespaced_resources(f)

    print(f'Retrieving live state from {args.k8s_apiserver_url}...')
    raw_live_strings = get_compact_resource_identifiers(get_live_namespaced_resources(args.k8s_apiserver_url))

    live_strings = list(filter(lambda s: not re.match('|'.join(blacklist_regexs), s), raw_live_strings))

    starget = set(get_compact_resource_identifiers(target_tuples))
    slive = set(live_strings)

    print('Live dynamic configmaps that are not in target (stale):')
    counter = 0
    for x in sorted(list(slive - starget)):
        if re.match('^.*:v1:ConfigMap:.*-[a-z0-9]{10}', x):
            counter += 1
            print('  ' + x)
    print("..", counter, "entries")

    print()
    print('Live resources w/o dynamic configmaps that are not in target (stale):')
    counter = 0
    for x in sorted(list(slive - starget)):
        if not re.match('^.*:v1:ConfigMap:.*-[a-z0-9]{10}', x):
            counter += 1
            print('  ' + x)
    print("..", counter, "entries")

    sys.exit(len(list(slive - starget)))


if __name__ == "__main__":
    main()
