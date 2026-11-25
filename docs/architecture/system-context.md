# Kubo — System Context

**Document ID:** KUBO-ARCH-CTX-001  
**Version:** 1.0
**Status:** Accepted baseline

## Purpose

This view shows Kubo's users, API clients, system boundary, and infrastructure that Kubo operates. It does not show internal service deployment.

```mermaid
flowchart LR
    User["User / Organization Member"]
    Admin["Kubo Operator"]
    Client["API Client / Automation"]

    subgraph KUBO["Kubo Platform"]
        Gateway["Kubo API Gateway"]
        IAM["IAM Service"]
        Compute["Compute Service"]
        Network["Networking Service"]
        Broker["Internal RabbitMQ"]
    end

    subgraph HOST["Operator-Controlled Linux Host"]
        Docker["Docker Engine"]
        Disk["Persistent host storage"]
        Firewall["Host networking and firewall"]
    end

    User -->|"Uses custom API"| Gateway
    Admin -->|"Configures platform and approved images"| Gateway
    Client -->|"HTTPS / custom API"| Gateway
    Gateway --> IAM
    Gateway --> Compute
    Gateway --> Network
    Compute -->|"Internal lifecycle work"| Broker
    Broker -->|"Consumed by compute worker"| Compute
    Compute -->|"Privileged adapter boundary"| Docker
    Compute --> Disk
    Network --> Firewall
    Docker --> Firewall
```

The first milestone has no management console. Users and administrators use the custom API and its documented client interfaces. Object Storage, the user-facing Queue Service, and Firecracker are later capabilities.

Kubo does not promise AWS API compatibility. Organization authorization is enforced by Kubo services; the host operator remains trusted to administer the Linux host and Docker Engine.
