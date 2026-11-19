# Host scan, Phase 0

This folder holds Phase 0 of issue 1239: a test of the design that the issue proposes for host
vulnerabilities. It holds no product code. The test ran on 2026-11-19, with Trivy 0.76.2 and Grype
0.121.3 in the JAVV scanner images.

## What ran

| File | What it does |
|---|---|
| `cluster.sh` | Makes a k3d cluster with one node. The node gets the package database and the release files of the test machine, read-only and at their real paths. The test machine runs Ubuntu 24.04 with kernel `7.0.0-42-generic`. |
| `collector.py`, `collector.yaml` | The collector: a DaemonSet on the scanner image. It reads the files of its node from read-only mounts and serves a copy of them on port 8080. A headless Service lists the collector pods. |
| `scan.py`, `scan-job.yaml` | The central scan: a Job for each scanner. It gets the copy of each node, runs the scanner, and reads the report with the adapters of the scanner package. It builds a host envelope with `build_envelope` of the scanner package and prints one line with the measurements. |
| `run.sh` | Starts the collector and the two Jobs. |

To repeat the test:

```bash
docker build -f scanner/Dockerfile.trivy --build-arg TRIVY_VERSION=0.76.2 -t local1/javv-scanner-trivy:0.76.2-hostscan .
docker build -f scanner/Dockerfile.grype --build-arg GRYPE_VERSION=0.121.3 -t local1/javv-scanner-grype:0.121.3-hostscan .
KUBECONFIG_OUT=/tmp/hostscan.kubeconfig docs/research/host-scan/cluster.sh
k3d image import -c hostscan local1/javv-scanner-trivy:0.76.2-hostscan local1/javv-scanner-grype:0.121.3-hostscan
KUBECONFIG_OUT=/tmp/hostscan.kubeconfig docs/research/host-scan/run.sh
```

`cluster.sh` does not change the default kubeconfig. `scan.py` can also scan folders in place of
the collectors. Set `ROOTS` to the folders, with commas between them, and run it in a scanner image.

## Results on the Ubuntu node

The node is the test machine: 1,759 packages in `/var/lib/dpkg/status`.

| | Trivy | Grype |
|---|---|---|
| Time of the scan (two runs) | 2.6 s and 3.2 s | 147 s and 149 s |
| Memory peak of the container (two runs) | 443 MB and 475 MB | 600 MB and 801 MB |
| Findings in the report | 8,015 | 10,591 |
| Findings after the adapter | 8,015 | 10,591 |
| Different IDs | 1,685 | 3,791 |
| Packages with a finding | 272 | 470 |
| With a fixed version | 1,895 | 1,137 |
| KEV | 0 | 9 |
| Kernel that runs: findings (packages) | 3,235 (5) | 2,016 (3) |
| Other kernel packages: findings (packages) | 3,343 (8) | 1,991 (5) |
| All other packages: findings (packages) | 1,437 (259) | 6,584 (462) |
| Host envelope | 2.08 MB, 49 KB with gzip | 2.97 MB, 82 KB with gzip |

- The two runs gave the same counts and envelope sizes. Only the time and the memory changed.
- The adapters keep each row of the reports. They need no field of an image.
- The memory peak comes from `memory.peak` of the cgroup of the container. The download of the
  database runs in an init container, so it is not in the peak.
- The kernel packages are 82% of the Trivy findings and 38% of the Grype findings. A package of
  the kernel that runs has the version of `/proc/sys/kernel/osrelease` without its flavour, for
  example `linux-headers-7.0.0-42` and `linux-image-7.0.0-42-generic`. The other kernel
  packages are `linux-libc-dev`, `linux-tools-common` and the packages of kernel 43, which is
  installed but does not run.
- The largest envelope has 2.97 MB. `JAVV_INGEST_MAX_BODY_BYTES` is 60 MiB.
- The research of the issue counted 7,542 Trivy findings on 2026-11-17. A scan of the same files
  today with the Trivy database of 2026-11-13 gives 7,542 again. So the newer database gives the
  473 more findings, not a change of the packages.

## The collector

- **The copy**: the four files have 1,845,874 bytes. The copy that the collector serves has
  426,393 bytes with gzip.
- **The Pod Security level**: a namespace with `pod-security.kubernetes.io/enforce=baseline`
  refuses the collector pod. The API server gives one reason: `hostPath volumes (volumes
  "dpkg-status", "os-release", "usr-os-release", "lsb-release")`. So the collector needs the
  Privileged level only for the `hostPath` volumes.
- The collector runs as user 65532, with a read-only root file system, all capabilities dropped,
  and read-only mounts. It needs no `privileged` flag, no `hostPID` and no host network. It holds
  no service account token.
- The scan Job finds the collectors through the DNS name of the headless Service. It needs no
  Kubernetes API access.

## Other package systems

The test copied the release files and the package database of three images. Each copy ran two
times: with all of the release files, and with `etc/os-release` and the package database only.

| System | Files of the copy | Size | Trivy | Grype |
|---|---|---|---|---|
| Rocky Linux 9.9 | `var/lib/rpm/rpmdb.sqlite` | 6.1 MB | 147 packages, 0 findings | 147 packages, 527 findings, 2 with a fixed version |
| Amazon Linux 2023 | `var/lib/rpm/rpmdb.sqlite` | 3.0 MB | No OS and no packages without `etc/system-release`. With it: 106 packages, 0 findings | 106 packages, 0 findings |
| Alpine 3.20.10 | `lib/apk/db/installed` | 14 KB | 14 packages, 2 findings | 6 findings |

- **Amazon Linux needs `/etc/system-release` for Trivy.** In the image, `/etc/system-release` is a
  link to `/usr/lib/system-release`. The collector must copy the file that the link names.
- The other systems need only `etc/os-release` and the package database. For Grype, all three
  need only these two files.
- The rpm database of these systems is SQLite. Its files `rpmdb.sqlite-wal` and
  `rpmdb.sqlite-shm` were empty in the images. On a node that installs packages, the WAL file can
  hold the newest changes, so the collector must copy it too. The test did not show this case.
- The images are new, so they have few findings. The rows show which files the scanners read, not
  how many findings a real node has.

## A node with no package database

A k3d node has `etc/os-release` (`PRETTY_NAME="K3s v1.35.5+k3s1"`) and no package database. Both
scanners exit with 0 and report no OS, no packages and no findings. A node with no package
database thus looks the same as a node with no findings. The design must tell the two apart, for
example from the files that the collector found.

## Not tested

- A node of a real cloud cluster, and the systems with no package database in the usual place:
  Talos, Bottlerocket, Flatcar, Container-Optimized OS. Also Windows nodes.
- The guard of the copy. A NetworkPolicy is part of the design of Phase 2 (operator,
  2026-11-19).
- Red Hat Enterprise Linux. The research names a limit of Trivy for Red Hat.
- The time and memory of the central scan for many nodes.

## Open questions

- On Rocky Linux 9, Trivy reports 0 findings and Grype reports 527, with 2 that have a fixed
  version. The test does not show why. JAVV shows each scanner as it is, so this is not a fault
  of the test.
- Grype finds about twice as many packages with a finding as Trivy on the Ubuntu node (470 and
  272). The test does not show why.
