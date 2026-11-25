# Mainnet Launch Readiness Checklist

Use this checklist to record the evidence and approvals required before launching Shade on Stellar mainnet. Complete it against the exact release commit and deployment configuration described in the [Deployment Runbook](deployment.md). Do not treat an unchecked item or missing evidence as complete.

Replace each owner role with a named person before review. Replace every evidence placeholder with a link to the relevant report, transaction, dashboard, runbook record, or other durable evidence.

## Security

| Complete | Requirement | Owner | Evidence |
|---|---|---|---|
| [ ] | Independent security audit is complete for the release candidate, and every finding is resolved or has a documented, explicitly accepted disposition. | [Security lead] | [Link to audit report and finding dispositions] |
| [ ] | Contract invariants and critical payment, authorization, and accounting properties are covered by tests, and the relevant test suite passes on the release commit. | [Engineering lead] | [Link to test results and invariant coverage] |
| [ ] | The public [`SECURITY.md`](../../SECURITY.md) policy is present, current, and reachable from the repository. | [Security lead] | [Link to published policy] |

## Keys and administration

| Complete | Requirement | Owner | Evidence |
|---|---|---|---|
| [ ] | The intended mainnet admin is controlled by the approved multisig, and its authorization flow has been verified before deployment. | [Protocol/governance lead] | [Link to multisig configuration and authorization test] |
| [ ] | The platform account and its signing/administrative access are secured, and the intended account has been independently confirmed. | [Operations lead] | [Link to access-control review and account confirmation] |

## Build and release

| Complete | Requirement | Owner | Evidence |
|---|---|---|---|
| [ ] | Two independent builds from the same tagged commit and recorded toolchain produce matching optimized WASM hashes. | [Release owner] | [Link to build records and matching hash comparison] |
| [ ] | The optimized WASM hashes for every deployed contract are published with the release and match the artifacts approved for deployment. | [Release owner] | [Link to release and published checksums] |

## Operations

| Complete | Requirement | Owner | Evidence |
|---|---|---|---|
| [ ] | Production monitoring and alerting are live, tested, and have named responders for critical alerts. | [Operations lead] | [Link to dashboards, alert tests, and on-call rota] |
| [ ] | Any keeper required by the launch configuration is deployed, monitored, and has a documented recovery procedure. If no keeper is required, record that decision. | [Operations lead] | [Link to deployment and health check, or approved not-applicable decision] |
| [ ] | TTL and storage-expiration management is in place, with responsibility, monitoring, and an escalation path defined. | [Operations lead] | [Link to TTL procedure and monitoring evidence] |
| [ ] | Relevant incident, pause, deployment, and recovery runbooks have been rehearsed on testnet by the people who will operate mainnet. | [Incident commander] | [Link to rehearsal record and follow-up actions] |

## Configuration

| Complete | Requirement | Owner | Evidence |
|---|---|---|---|
| [ ] | Mainnet fees, accepted tokens, and oracle addresses and settings have been reviewed against the intended launch configuration by a second authorized reviewer. | [Protocol lead] | [Link to approved configuration and review] |

## Documentation and registry

| Complete | Requirement | Owner | Evidence |
|---|---|---|---|
| [ ] | Integrator documentation is complete, current for the release, and reviewed against the deployed interfaces and behavior. | [Documentation owner] | [Link to reviewed integrator documentation] |
| [ ] | The address registry is updated with verified mainnet contract IDs, network, release commit, and corresponding WASM hashes. | [Release owner] | [Link to updated registry and verification] |

## Staged rollout

Use a staged rollout when it is appropriate for the launch. Record the decision and the controls before enabling production traffic.

| Complete | Requirement | Owner | Evidence |
|---|---|---|---|
| [ ] | The initial rollout decision is recorded, including whether access is limited to allowlisted merchants and which merchants are included. | [Protocol lead] | [Link to approved rollout plan and allowlist] |
| [ ] | Initial transaction or volume caps, the process for changing them, and criteria for expanding or stopping the rollout are approved and configured. | [Operations lead] | [Link to approved caps, configuration, and expansion criteria] |

## Go/no-go sign-off

1. The release owner confirms that this checklist is complete for the exact release commit and proposed deployment configuration, and links the release tag, commit SHA, and deployment plan.
2. The security lead, operations lead, and protocol/governance approver independently review the evidence and record an explicit **Approve** or **Reject**, with their name, role, date, and evidence link. The release owner records the final decision and links the approval record.
3. **Go** requires all checklist items to be complete or have an explicitly documented, accepted exception, and approval from all three approver roles. A missing approval, unresolved critical/high security finding, unverified admin, or other unresolved launch blocker means **No-go**. Any approver may block launch.
4. The designated protocol/governance authority gives final authorization to deploy only after the required approvals are recorded. The operator then follows the [Deployment Runbook](deployment.md) and records deployment details in the approved operational record.
5. Any material change to the release artifact, admin, configuration, or rollout plan invalidates affected approvals and requires those checks and approvals to be repeated. Record a no-go decision and its blockers in the same approval record; do not deploy until a new go decision is documented.

| Decision | Approver role | Name | Date | Evidence / approval record |
|---|---|---|---|---|
| [Approve / Reject] | Security lead | [Name] | [Date] | [Link to review and decision] |
| [Approve / Reject] | Operations lead | [Name] | [Date] | [Link to review and decision] |
| [Approve / Reject] | Protocol/governance approver | [Name] | [Date] | [Link to review and decision] |
| [Go / No-go] | Release owner (records decision) | [Name] | [Date] | [Link to completed checklist, release commit, and final decision] |

## Related pages

- [Deployment Runbook](deployment.md) — deploy and configure the contracts.
- [Releases Runbook](releases.md) — produce reproducible builds and publish WASM hashes.
- [Admin Operations and Incident Response Runbook](admin-runbook.md) — administer the deployment and respond to incidents.
- [Security Policy](../../SECURITY.md) — vulnerability reporting and response.

← [Back to Operations](README.md)
