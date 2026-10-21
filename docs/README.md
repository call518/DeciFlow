# Documentation

[English](README.md) | [한국어](README.ko.md) | [Project README](../README.md)

Start with the [quick start](../README.md#quick-start--docker--laya-cpu) to run
DeciFlow and Laya. Complete [Google sign-in and HTTPS setup](authentication.md)
before starting the default Docker deployment. Use the guides below for the task you need.

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
| [DNS and TLS Certificates](dns-tls.md) | Public DNS, Certbot DNS-01/RFC2136, certificate deployment, renewal, and WSL checks |
| [Google Sign-In](authentication.md) | Default OAuth2-Proxy deployment, email allow list, HTTPS, and verification |
| [Docker deployment](../README.md#docker-deployment-details) | Published images, CPU/CUDA profiles, ports, mounts, volumes, and lifecycle commands |
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
