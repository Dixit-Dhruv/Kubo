# Kubo — Component Architecture Document

**Document ID:** KUBO-ARCH-COMP-001  
**Version:** 0.1  
**Status:** Draft — Review Required  
**Parent Document:** KUBO-ARCH-001

---

## 1. Purpose

This document defines the internal logical components of Kubo, their responsibilities, interfaces, dependencies, and interaction patterns.

The objective is to establish clear component boundaries before implementation begins.

This document describes logical components. It does not require each component to run as an independent process, service, or container.

## 2. Architectural Principles

1. Separation of concerns between API handling, business logic, persistence, and infrastructure execution.
2. Explicit interfaces between components.
3. Centralized enforcement of authentication and authorization policies.
4. Independent resource lifecycle management.
5. Replaceable infrastructure providers.
6. Durable tracking of asynchronous operations.
7. Explicit error propagation and recovery behavior.
8. No direct access to privileged infrastructure from the frontend.
9. Testable business logic independent of host-specific implementations.
10. Observable operations with correlation identifiers and audit events.

## 3. Component Architecture Diagram

```mermaid
flowchart TB
    UI["Management Console"]

    subgraph CONTROL["Kubo Control Plane"]
        API["API Router"]
        Auth["Authentication Component"]
        Authz["Authorization Policy Engine"]
        Validation["Request Validation"]
        IAM["Identity and Access Manager"]
        Compute["Compute Manager"]
        Storage["Object Storage Manager"]
        Queue["Queue Manager"]
        Network["Network Manager"]
        Operations["Operation Coordinator"]
        Quota["Quota Manager"]
        Events["Audit and Event Publisher"]
    end

    subgraph PORTS["Domain Interfaces"]
        ComputePort["Compute Provider Interface"]
        StoragePort["Object Storage Interface"]
        QueuePort["Queue Backend Interface"]
        NetworkPort["Network Provider Interface"]
    end

    subgraph ADAPTERS["Infrastructure Adapters"]
        Container["Container Runtime Adapter"]
        Firecracker["Firecracker Adapter - Future"]
        ObjectBackend["Object Storage Adapter"]
        QueueBackend["Queue Backend Adapter"]
        NetworkBackend["Network Backend Adapter"]
    end

    subgraph PERSISTENCE["Persistence Components"]
        Repositories["Repository Layer"]
        Metadata[("Metadata Database")]
        ObjectData[("Object Data Store")]
        QueueData[("Queue Persistence")]
    end

    UI --> API
    API --> Auth
    API --> Validation
    Auth --> IAM
    API --> Authz
    Authz --> IAM

    API --> Compute
    API --> Storage
    API --> Queue
    API --> Network

    Compute --> Quota
    Compute --> Operations
    Storage --> Quota
    Queue --> Operations
    Network --> Quota

    Compute --> ComputePort
    Storage --> StoragePort
    Queue --> QueuePort
    Network --> NetworkPort

    ComputePort --> Container
    ComputePort -.-> Firecracker
    StoragePort --> ObjectBackend
    QueuePort --> QueueBackend
    NetworkPort --> NetworkBackend

    Operations --> Repositories
    IAM --> Repositories
    Compute --> Repositories
    Storage --> Repositories
    Queue --> Repositories
    Network --> Repositories

    Repositories --> Metadata
    ObjectBackend --> ObjectData
    QueueBackend --> QueueData

    Compute --> Events
    Storage --> Events
    Queue --> Events
    Network --> Events
    IAM --> Events