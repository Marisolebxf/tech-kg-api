# Repository Instructions

## Docker image source

- Pull Docker Hub images through the Huawei Cloud SWR mirror instead of directly from Docker Hub.
- Mirror prefix: `swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/`
- Preserve the original Docker Hub repository path after the prefix.
- Official images use the `library/` namespace. Example: `golang:1.22.5` becomes `swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/golang:1.22.5`.
- Namespaced images keep their namespace. Example: `minio/minio:TAG` becomes `swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/minio/minio:TAG`.
- For a known non-Docker-Hub registry mirror, replace the source registry with the matching path below `swr.cn-north-4.myhuaweicloud.com/ddn-k8s/`.
- Apply the same rule to Dockerfile `FROM` instructions, Compose `image` entries, and manual `docker pull` commands.
- Verify that the requested tag exists in SWR (for example with `docker manifest inspect`) before using it; mirror tag availability may differ from Docker Hub.
- Do not rewrite images from other registries unless a working SWR mirror path for that registry is known.
