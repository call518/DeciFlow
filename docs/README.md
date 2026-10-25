# Documentation

[English](README.md) | [한국어](README.ko.md) | [Project README](../README.md)

**[Complete Installation and Configuration: INSTALL.md](../INSTALL.md)**

Choose one installation method:

- [PyPI / pip or uv tool](../INSTALL.md#pypi) **(Recommended)**: install with pip or uv tool without cloning the repository.
- [Git clone + Docker Compose](../INSTALL.md#docker-compose): container deployment with optional local Laya.
- [Git clone + native Python](../INSTALL.md#direct-processes): run the CLI from a source checkout.

Check [environment file locations](configuration.md#environment-file-locations)
before editing `.env`; the three methods do not automatically share this file.
INSTALL covers quick HTTP startup and `.env` settings. Laya runs in Docker;
optional [Docker Google sign-in](authentication.md) is configured separately.

For Remote File, register SSH Keys and SSH Hosts in Settings first.
The usual setup order is Source → Criteria → optional Actions → Tasks.

## Use and configure DeciFlow

| Guide | Read it when you need to… |
| --- | --- |
| [Sources](sources.md) | Register local or SSH file sources and select them in Tasks |
| [Usage](usage.md) | Analyze logs, filter results, review predictions, reconnect, or understand metrics |
| [Configuration](configuration.md) | Environment variables, engines, storage, backups, logging, and maintenance |
| [Sample VOC Asia Culture Center Consulting QnA](voc.md) | Run the sample, author full Criteria, and validate conversation decisions |
| [Sample VOC Central Gov Consulting QnA](voc.md#government-qna-sample) | Run the government QnA sample with its Source, Korean Criteria, and Task |
| [Sample VOC Local Gov Consulting QnA](voc.md#local-government-qna-sample) | Run the local government QnA sample with its Source, Korean Criteria, and Task |
| [Criteria](criteria.md) | Field-by-field authoring, decision types, examples, and save-error troubleshooting |
| [Python Actions](actions.md) | Run Python Code after classification and manage execution environments |
| [Tasks](tasks.md) | Reusable executions, cron schedules, continuous monitoring, and durable run history |

## Deploy and integrate

| Reference | Contents |
| --- | --- |
| [PyPI / pip or uv tool Installation](../INSTALL.md#pypi) | Recommended command installation, init/config commands, Docker Laya connection, and HTTP demo |
| [Docker deployment](../INSTALL.md#docker-compose) | Published images, CPU/CUDA profiles, ports, mounts, volumes, and lifecycle commands |
| [Git Checkout Native Installation](../INSTALL.md#direct-processes) | Source-based local demo, engine selection, startup/shutdown, and Docker Laya |
| [DNS and TLS Certificates](dns-tls.md) | Public DNS, Certbot DNS-01/RFC2136, certificate deployment, renewal, and WSL checks |
| [Google Sign-In](authentication.md) | Optional OAuth2-Proxy deployment, email allow list, HTTPS, and verification |
| [Dockerfile and Compose](development.md#docker-runtime) | UI runtime image and how Compose configures its services |
| [Laya Integration and Validation](laya.md) | Request contract, response validation, server settings, model evaluation, and limits |
| [Request/result JSON](results.md) | Shared Laya/Jev schema, state, typed decisions, answers, and field reference |

See [Development and Releases](development.md) for test prerequisites and publication.

## Evaluate Laya

[Laya log validation](laya.md#evaluation) explains how to evaluate category
predictions against labeled logs and read the generated report. The evaluator is
an optional development tool; it is not needed to start DeciFlow.

## JSON examples

- [Laya request](examples/laya-request.json)
- [Laya result](examples/laya-result.json)

These are illustrative examples checked against the classifier, not live inference
measurements. [Request/result JSON](results.md) explains how they relate to Jev.
