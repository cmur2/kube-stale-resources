# kube-stale-resources

![Build Status](https://github.com/cmur2/kube-stale-resources/workflows/ci/badge.svg?branch=add-ci)

This is a utility to detect stale resources in [Kubernetes](https://kubernetes.io/) clusters between resources from YAML manifests supplied via local file or stdin (target state) and a Kubernetes cluster (live state).
All resources that exist in the live state but not in the target state are considered *stale* as they deviate from the intended state of the Kubernetes cluster (closed world assumption). It is intended as a complement to [kubectl diff](https://kubernetes.io/blog/2019/01/14/apiserver-dry-run-and-kubectl-diff/).

Using a blacklist you can ignore resources from the live state from the comparison so they are not considered *stale* even though they do not exist in the given target state. This is useful when those resources are created by Kubernetes itself (e.g. the `kubernetes` service in the default namespace), managed by the Kubernetes cluster provider or another tool outside the scope.

A use case for `kube-stale-resources` is using it alongside `kubectl diff` on locally present YAML manifests so `kubectl diff` can detect newly created Kubernetes resources and changes to those resources and `kube-stale-resources` can alert the user on stale resources that should be deleted from the cluster.

Limitations:

- currently only works on namespaced resources
- currently requires explicit `metadata.namespace` field even for resources in default namespace
- requires unauthenticated HTTP(S) access to Kubernetes apiserver, e.g. via `kubectl proxy`
- only accounts for `apiVersion` deprecations up until Kubernetes 1.16


## Usage

You need Python 3.8 or higher.

Assuming you have a properly setup `.kube/config` (e.g. using [minikube](https://github.com/kubernetes/minikube) after a successful `minikube start`) running:

```bash
kubectl proxy &

# ignore minikube resources
cat <<EOF > blacklist.txt
^kubernetes-dashboard:.*$
^default:events.k8s.io/v1beta1:Event:minikube..*$
EOF

# orderly created resource using YAML manifest in e.g. git
cat <<EOF > version-controlled-resources.yml
---
apiVersion: v1
kind: Service
metadata:
  name: foo
  namespace: default
spec:
  type: ClusterIP
  ports:
    - port: 80
      name: http
      targetPort: 80
  selector:
    app: foo
EOF
kubectl apply -f version-controlled-resources.yml

# on-the-fly created resource using imperative command
kubectl create service clusterip bar --tcp='8080:8080'

cat version-controlled-resources.yml | python kube-stale-resources.py -f - --blacklist blacklist.txt
```

This should yield a similar output to as we ignored what minikube sets up by default (e.g. the whole `kubernetes-dashboard` namespace):

```
Reading blacklist file blacklist.txt...
Retrieving target state...
Retrieving live state from http://localhost:8001...
Live dynamic configmaps that are not in target (stale):
.. 0 entries

Live resources w/o dynamic configmaps that are not in target (stale):
  default:v1:Service:bar
.. 1 entries
```

Run `python kube-stale-resources.py -h` for full list of options.


## Blacklisting

Example blacklist file for a cluster on [GKE](https://cloud.google.com/kubernetes-engine/) that also uses [cert-manager](https://github.com/jetstack/cert-manager):

```
^.*:v1:ResourceQuota:gke-resource-quotas$
^default:v1:LimitRange:limits$

^.*:certmanager.k8s.io/v1alpha1:Order:.*$
```

In general a blacklist file contains one regular expression per line that are matched against a string of format `<namespace-name>:<apiVersion>:<kind>:<resource-name>` for each resource.


## License

kube-stale-resources is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for more information
