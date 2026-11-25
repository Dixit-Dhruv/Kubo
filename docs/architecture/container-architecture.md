# Kubo — Container Architecture

**Document ID:** KUBO-ARCH-CNT-001  
**Version:** 1.0
**Status:** Accepted baseline

In this C4 view, a container means a deployable application or data store, not necessarily a Docker container. The selected first-milestone services are independently deployable.

```mermaid
flowchart TB
    Client["API Client"]
    Proxy["TLS reverse proxy / ingress"]

    subgraph APP["Kubo application services"]
        Gateway["API Gateway"]
        IAM["IAM Service"]
        ComputeAPI["Compute API"]
        ComputeWorker["Compute Worker"]
        Network["Networking Service"]
    end

    Broker[("RabbitMQ\ninternal jobs only")]
    IAMDB[("IAM-owned store\nSQLite dev / PostgreSQL deploy")]
    ComputeDB[("Compute-owned store\nSQLite dev / PostgreSQL deploy")]
    NetworkDB[("Networking-owned store\nSQLite dev / PostgreSQL deploy")]

    subgraph HOST["Linux host boundary"]
        Adapter["Restricted compute adapter"]
        Docker["Docker Engine"]
        Volumes[("Persistent host volumes")]
        HostNet["Host firewall / networking"]
    end

    Client -->|"HTTPS"| Proxy
    Proxy --> Gateway
    Gateway --> IAM
    Gateway --> ComputeAPI
    Gateway --> Network
    IAM --> IAMDB
    ComputeAPI --> ComputeDB
    Network --> NetworkDB
    ComputeAPI -->|"Durable internal work"| Broker
    Broker --> ComputeWorker
    ComputeWorker --> ComputeDB
    ComputeWorker --> Adapter
    Adapter -->|"Privileged host API; isolated"| Docker
    ComputeWorker --> Network
    Docker --> Volumes
    Network --> HostNet

    ObjectStorage["Object Storage Service\nlater milestone"]
    UserQueue["User-facing Queue Service\nlater milestone"]
    Firecracker["Firecracker provider\nfuture Linux/KVM"]
    ObjectStorage -.-> Volumes
    UserQueue -.-> Broker
    ComputeWorker -.-> Firecracker
```

## Data ownership and communication

- IAM, Compute, and Networking each own their data store and migrations.
- Services use synchronous, authenticated HTTP for bounded cross-service requests and RabbitMQ for asynchronous work.
- Services never query another service's private database.
- RabbitMQ is not the user-facing Queue Service and does not own resource state.
- The privileged Docker adapter is isolated from public API traffic. Access to the Docker Engine is a host-level trust boundary.
- The dotted components are not part of the first milestone. The user-facing Queue Service must have separate contracts, authorization, and operational policies if it later shares broker technology.
