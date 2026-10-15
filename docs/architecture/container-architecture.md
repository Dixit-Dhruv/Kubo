
```markdown
# Kubo — Container Architecture Diagram

**Document ID:** KUBO-ARCH-CNT-001  
**Version:** 0.1  
**Status:** Draft — Technology Decisions Pending

## 1. Purpose

Describe the proposed logical applications, services, data stores and infrastructure interfaces that make up Kubo.

In the C4 model, a container is an independently executable application or data store. It does not necessarily mean a Docker container.

The diagram describes logical boundaries. It does not yet establish which components run as separate processes or deployment units.

## 2. Container Diagram

```mermaid
flowchart TB
    User["User / Administrator"]
    Client["API Client"]

    subgraph PLATFORM["Kubo Platform"]
        subgraph PRESENTATION["Presentation Layer"]
            UI["Management Console"]
        end

        subgraph CONTROL["Control Plane"]
            API["API Layer"]
            IAM["IAM Service"]
            Coordinator["Operation Coordinator"]
            Compute["Compute Service"]
            ObjectStorage["Object Storage Service"]
            Queue["Queue Service"]
            Networking["Networking Service"]
        end

        subgraph DATA["Persistence Layer"]
            Metadata[("Metadata Store\nTechnology TBD")]
            Objects[("Object Storage Backend\nTechnology TBD")]
            Messages[("Queue Persistence\nTechnology TBD")]
        end
    end

    subgraph EXECUTION["Host Infrastructure"]
        Provider["Compute Provider Interface"]
        Docker["Container Runtime Adapter"]
        Firecracker["Firecracker Adapter\nFuture Linux/KVM"]
        Runtime["Container Runtime"]
        MicroVM["Firecracker Runtime"]
        HostNetwork["Host Networking"]
    end

    User -->|"Uses console"| UI
    Client -->|"Custom API requests"| API
    UI -->|"HTTPS requests"| API

    API -->|"Authenticate and authorize"| IAM
    API -->|"Resource operations"| Compute
    API -->|"Object operations"| ObjectStorage
    API -->|"Queue operations"| Queue
    API -->|"Network operations"| Networking

    IAM <-->|"Identity and permissions"| Metadata
    Compute <-->|"Resource metadata and state"| Metadata
    ObjectStorage <-->|"Object metadata"| Metadata
    Queue <-->|"Queue metadata"| Metadata
    Networking <-->|"Network configuration"| Metadata

    ObjectStorage -->|"Read and write object data"| Objects
    Queue -->|"Persist and retrieve messages"| Messages

    Compute -->|"Provisioning requests"| Coordinator
    Coordinator -->|"Schedule execution operations"| Provider
    Provider -->|"Container operations"| Docker
    Provider -.->|"Future provider"| Firecracker

    Docker --> Runtime
    Firecracker --> MicroVM

    Networking -->|"Configure connectivity"| HostNetwork
    Docker -.->|"Runtime networking integration"| HostNetwork
    Firecracker -.->|"Guest networking integration"| HostNetwork