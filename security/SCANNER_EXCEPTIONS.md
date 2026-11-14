# Scoped scanner decisions

Review owner: Lead Architect, implemented by Platform and reviewed by Security.
Review deadline: before the first approved cloud deployment and after any runner,
state topology, scanner version or service-use change. These decisions are lab
constraints, not an enterprise security baseline.

Each inline exception is limited to the named bootstrap-state resource below.
They must not be copied to workload resources. Platform authors the Terraform;
Security reviews the control equivalence and rationale. The Lead Architect
approved public runner access and the local LRS/Microsoft-managed default with
independent replication and CMK options. Final
deployment review must accept the remaining lab tradeoffs; this is not a claim
of policy compliance or verified Azure enforcement.

- `azurerm_storage_account.state`, `CKV_AZURE_59`: the user approved a public state endpoint for GitHub-hosted runners. This rule checks public network access, not anonymous blob access. Compensating controls are Entra/OIDC authentication, disabled shared keys and anonymous access, separate state containers and scoped RBAC. Public endpoint exposure remains accepted residual risk.
- `azurerm_storage_account.state`, `CKV2_AZURE_33`: private endpoint infrastructure was expressly excluded by the approved runner decision. The same controls apply. A move to private runners/networking requires a new architecture decision.
- `azurerm_storage_account.state`, `CKV_AZURE_33`: Queue Storage logging is not applicable to this blob-only Terraform backend. No queue resource or queue workload is provisioned. Reassess if Queue Storage is used; do not treat this as a waiver for Blob Storage logging.
- `azurerm_storage_account.state`, `CKV_AZURE_206`: the user approved `LRS` as the lab default, with independent `ZRS` and `GZRS` choices. This Checkov rule accepts only geo-redundant variants and rejects both LRS and ZRS. LRS does not protect against a zone or regional loss; ZRS does not provide a regional copy. These availability tradeoffs are intentional lab choices, not enterprise resilience claims. The mandatory profile guard restricts allowed values and prevents coupling replication to key custody; mocked plans exercise all six combinations. Review destination, availability, recovery and cost before deploying a geo-redundant profile.
- `azurerm_key_vault.state`, `CKV_AZURE_189` and `CKV2_AZURE_32`: these resources exist only when `enable_cmk=true`; the default profile creates no vault. The approved initial topology excludes private infrastructure. The optional vault public endpoint has a deny-by-default firewall, explicit administrator IPv4 CIDRs and trusted-service bypass for Storage CMK. Public reachability from those networks and Azure trusted services remains; RBAC still applies. Reassess trusted-service scope and use private networking for an enterprise deployment when required.
- `azurerm_key_vault_key.state`, `CKV_AZURE_112`: when explicitly enabled, Standard Key Vault software RSA provides a customer-managed key with scoped encryption identity, rotation and purge/soft-delete protection. HSM-backed custody is not implemented and must not be claimed. Premium HSM costs and the production threat model require a separate decision; the coordinator selected Standard RSA for this optional lab profile rather than expanding paid-service scope solely to satisfy a scanner.
- `azurerm_storage_container.state` instances `lab-state` and `admin-state`, `CKV2_AZURE_21`: replace the legacy key-based Storage Insights graph requirement with modern Blob service diagnostics. `security/tests/blob_audit_control.py` is a mandatory semantic control in the scanner harness: it parses HCL, checks account/service and audit-workspace references, read/write/delete categories, retained Entra-only protected audit storage, shared-key denial and actual unconditional resource enablement. It rejects fourteen broken mutations. This is a scanner compatibility replacement, not a logging waiver. A built-in skip without this replacement passing fails the security job.

## Added controls and validation boundary

The default is LRS with Azure platform-managed encryption. `storage_replication_type`
accepts LRS/ZRS/GZRS independently of `enable_cmk`; changing replication does not
enable or require customer-managed keys. `enable_cmk=true` creates the encryption
identity, protected vault/key, scoped grants and vault audit setting. Blob
read/write/delete diagnostics and the protected audit workspace remain mandatory
in every profile. No `ignore_changes` hides encryption drift. An already-deployed
CMK profile cannot be casually disabled: protected resources require an approved
migration and lifecycle review.

`security/tests/state_profile_control.py` guards this scoped configuration and
rejects twelve broken mutations, including reintroduction of a moving-clock key
expiry plan gate. Terraform mocked-provider tests separately
exercise the six combinations and invalid CMK inputs. Checkov is a static source
scan: its CMK check can pass because it sees the configured dynamic CMK branch
even when the default toggle is false. That pass does not mean the default uses
customer-managed encryption. No unnecessary CMK-check suppression is added.

Expiry is format-validated in Terraform without a moving-clock plan precondition.
Before initial CMK creation/enablement, the explicit offline preflight reads the
same reviewed variable file and requires initial expiry more than 30 days away.
Fourteen frozen-clock tests cover expired/near/boundary values, default bypass,
reviewed-file values and competing environment settings. This initial-creation
procedure must not block ordinary future plans after automatic key rotation.

These are local configurations/tests, not Azure verification. Report passing,
skipped, source-guard, mocked-plan and replacement-control counts separately.
Modern Blob diagnostics are documented by Microsoft at
https://learn.microsoft.com/en-us/azure/storage/common/secure-storage . The
legacy resource requires a storage key:
https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/log_analytics_storage_insights .
