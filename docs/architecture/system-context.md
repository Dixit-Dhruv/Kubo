# Kubo — System Context Diagram

**Document ID:** KUBO-ARCH-CTX-001  
**Version:** 0.1  
**Status:** Draft

## 1. Purpose

This diagram defines Kubo's external actors, system boundary and principal relationships with host infrastructure.

It does not prescribe the internal service decomposition or deployment topology.

## 2. System Context

```mermaid
flowchart TB
    Developer["Developer / Cloud Learner"]
    Admin["Kubo Administrator"]
    Client["API Client / Automation"]

    subgraph KUBO["Kubo Platform"]
        Console["Management Console"]
        API["Kubo Custom API"]
        Services["Cloud Resource Services"]
    end

    subgraph HOST["User-Controlled Infrastructure"]
        Compute["Compute Runtime"]
        Storage["Persistent Storage"]
        Network["Host Networking"]
    end

    Developer -->|"Manages resources"| Console
    Admin -->|"Configures users and permissions"| Console
    Client -->|"HTTPS / API requests"| API

    Console -->|"Resource operations"| API
    API -->|"Authorized requests"| Services

    Services -->|"Provision and manage workloads"| Compute
    Services -->|"Persist resource data and objects"| Storage
    Services -->|"Configure workload connectivity"| Network