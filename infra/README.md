# Infrastructure templates

Read ../docs/GOOGLE_CLOUD_DEVELOPMENT.md before using these files. No cloud resources have been created. The vLLM manifest is a template with unresolved model/GPU/image/PVC choices, not a complete infrastructure stack. The network policy is an ingress boundary, not complete cluster security.

Provision namespaces, service identities and IAM, model cache, API-key secret integration, CPU/GPU node pools, driver/device plugin, enforced network policies, private SQL connectivity, storage, outbox/Pub/Sub, application services, public TLS entry point, internal TLS/mTLS, egress controls, monitoring, and backups separately through reviewed IaC. These omissions are planned B17 work, not implied resources.

After rendering templates to an ignored directory, validate with kubectl apply --dry-run=server against the selected cluster, then test identity/network behavior. Also test /health behavior on the pinned image and an authenticated /v1/models request from an allowed caller. A successful YAML parse is insufficient. Recreate strategy minimizes extra GPU demand for this single-replica example but causes inference downtime; choose a capacity-backed rolling/canary design if the availability target requires it.
