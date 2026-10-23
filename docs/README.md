# Documentation

[English](README.md) | [한국어](README.ko.md) | [Project README](../README.md)

Choose one installation method in the recommended order:

1. [PyPI / uv tool](tool-install.md): recommended installation from PyPI without cloning the repository.
2. [Git clone + Docker Compose](../README.md#alternative-installation-docker--laya-cpu): container deployment with optional local Laya.
3. [Git clone + native Python](native.md): run the CLI from a source checkout.

Check [environment file locations](configuration.md#environment-file-locations)
before editing `.env`; the three methods do not automatically share this file.
For non-container authentication, follow [OAuth2-Proxy binary installation](oauth2-proxy-install.md).
Google sign-in and HTTPS are optional. Configure [authentication](authentication.md)
only when enabling OAuth2-Proxy.

For Remote File, register SSH Keys and SSH Hosts in Settings first. Then follow
Source → Criteria → optional Actions → Tasks, and inspect current/latest Task results in Main.

## Use and configure DeciFlow

| Guide | Read it when you need to… |
| --- | --- |
| [Sources](sources.md) | Register local or SSH file sources and select them in Tasks |
| [Usage](usage.md) | Analyze logs, filter results, review predictions, reconnect, or understand metrics |
| [Configuration](configuration.md) | Set environment variables, choose Laya/Jev models, or adjust request budgets |
| [Sample VOC Asia Culture Center Consulting QnA](voc.md) | Run the sample, author full Criteria, and validate conversation decisions |
| [Sample VOC Central Gov Consulting QnA](voc.md#government-qna-sample) | Run the government QnA sample with its Source, Korean Criteria, and Task |
| [Sample VOC Local Gov Consulting QnA](voc.md#local-government-qna-sample) | Run the local government QnA sample with its Source, Korean Criteria, and Task |
| [Criteria](criteria.md) | Field-by-field authoring, decision types, examples, and save-error troubleshooting |
| [Python Actions](actions.md) | Run Python Code after classification and manage execution environments |
| [Tasks](tasks.md) | Reusable executions, cron schedules, continuous monitoring, and durable run history |
| [Result Storage](result-storage.md) | Manage SQLite storage, page sizes, configuration records, backups, and database adapters |

## Deploy and integrate

| Reference | Contents |
| --- | --- |
| [PyPI / uv tool Installation](tool-install.md) | Recommended command installation, init/config commands, engine connection, and optional authentication |
| [Docker deployment](../README.md#docker-deployment-details) | Published images, CPU/CUDA profiles, ports, mounts, volumes, and lifecycle commands |
| [Git Checkout Native Installation](native.md) | Source-based local demo, engine selection, startup/shutdown, and optional native OAuth2-Proxy |
| [DNS and TLS Certificates](dns-tls.md) | Public DNS, Certbot DNS-01/RFC2136, certificate deployment, renewal, and WSL checks |
| [Google Sign-In](authentication.md) | Optional OAuth2-Proxy deployment, email allow list, HTTPS, and verification |
| [Dockerfile and Compose](../README.md#dockerfile-and-compose-responsibilities) | UI runtime image and how Compose configures its services |
| [Laya integration](laya-integration.md) | Request contract, response validation, server settings, and limits |
| [Request/result JSON](results.md) | Shared Laya/Jev schema, state, typed decisions, answers, and field reference |

## Evaluate Laya

[Laya log validation](laya-validation.md) explains how to evaluate category
predictions against labeled logs and read the generated report. The evaluator is
an optional development tool; it is not needed to start DeciFlow.

## JSON examples

- [Laya request](examples/laya-request.json)
- [Laya result](examples/laya-result.json)

These are illustrative examples checked against the classifier, not live inference
measurements. [Request/result JSON](results.md) explains how they relate to Jev.
