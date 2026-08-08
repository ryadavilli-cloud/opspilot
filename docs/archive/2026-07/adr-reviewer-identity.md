# ADR — Reviewer identity for the HITL decision endpoint (G-01)

**Status:** accepted · **Stage:** 5c (#36) · **Closes:** [G-01](./status.md#g-01) · **Companion to**
`architecture.md` §8 and §13.1 ("Human approval — bound to a verified identity and exact bytes").

This ADR records the *security-failure behaviour* decision that code-guidelines §19 requires an ADR
for, and carries the **manual Entra bootstrap runbook** that `infra/main.bicep` and
`scripts/smoke_deployment.py` both point at with "see the ADR". The high-level choice (a verified
Entra principal, not a self-declared string) was already settled in `architecture.md` §13.1; this
document is the *how*, the *why it fails the way it does*, and the *steps a human must run once*.

---

## Context

Before this change, `POST /investigations/{id}/decision` accepted a client-supplied `approver`
string with no authentication. `curl -d '{"decision":"approve","approver":"anyone"}'` produced an
approval record that `_build_response` reported as `kind: "human"`. The HITL gate is v1's
publication control, so an unauthenticated gate was the appearance of human review with none of the
substance — worse than no gate, because it *looked* audited.

The app's own managed identity is the wrong tool: it answers "which workload is calling Azure?"
(inference, Cosmos), has no human behind it, and signing an approval with it only re-creates the
auto-approve stub. Code-guidelines §15 is explicit: **reviewer identity is a human Entra identity,
not a workload identity.**

## Decision

The reviewer's identity is derived **only** from a validated Entra ID access token on the request.
The client cannot influence it. Concretely:

1. **`approver` is deleted from the request contract**, not cross-checked. `InvestigationDecision`
   sets `extra="forbid"`, so an old client still sending it gets a 422 rather than a silently
   ignored field. Identity comes from the token via `_resume_payload`, server-side.
2. **In-app validation, no bypass backend.** `EntraJwtAuthenticator` verifies signature (RS256,
   `alg` pinned), `iss` (exactly the configured tenant), `aud` (this API — stops a token minted for
   another app in the same tenant being replayed), `exp`/`nbf`, and the approver **role**. There is
   deliberately no `insecure`/`none` authenticator: tests drive the *real* validator against a
   self-signed keypair through the JWKS seam, so no unauthenticated path exists in the shipped image.
3. **Authorization is separate from authentication.** Being signed into the tenant is not consent to
   publish a production RCA; the token must carry the `Approver` app role or the endpoint returns
   403 (distinct from the 401 for an unproven identity).
4. **`kind` derives from the verified `auth_method`, never a string compare.** A workload token
   (the deploy smoke gate authenticates as a service principal) is *accepted* but recorded as
   `service_principal`, never `human`. An approval with no proven identity at all degrades to
   `deterministic_auto_approval` — unknown provenance takes the weakest claim, not the strongest.
5. **The audit record binds the immutable `oid`** (`entra_jwt:<oid>`), plus tenant and the
   display-name-at-decision-time, to the `report_hash`. Display names are reassignable; the `oid`
   is not.

## Security-failure behaviour (all fail-closed)

| Failure | Behaviour | Why |
|---|---|---|
| No / malformed `Authorization` header | 401, run untouched | An approval must be affirmatively proven, never defaulted. |
| Bad signature, wrong `iss`/`aud`, expired | 401, coarse reason | Detailed reasons at an unauthenticated endpoint are a probing oracle; the precise cause is logged server-side. |
| JWKS unreachable / unknown `kid` | 401 | An approval is not accepted because the key service was down. |
| Authenticated but missing the role | 403 | Distinguished from 401 so a real reviewer missing a grant gets an actionable answer. |
| Auth config unset (no tenant/audience) | `build_reviewer_authenticator()` raises → 500 on the decision endpoint | A misconfigured deployment refuses to decide rather than accepting unvalidated tokens. |
| Auth runs **before** the record lookup | 401 for a real id and an unknown id are indistinguishable | The endpoint is not an investigation-id oracle for an anonymous caller. |

## Consequences

- Pulls in `pyjwt[crypto]` as a **core** dependency (not an optional group): "the auth library
  isn't installed" must be impossible, not a path that degrades to unauthenticated approval.
- Requires an Entra **app registration**, which is Microsoft Graph, not ARM — Bicep cannot create
  it. Hence the one-time manual bootstrap below; Bicep carries only the *config* (`AZURE_TENANT_ID`,
  audience, role name, console client id).
- The operator console signs in with **MSAL-style authorization-code + PKCE**, hand-written rather
  than vendoring ~200KB of MSAL, to keep the console a single self-contained same-origin page.
- The deploy smoke gate cannot be a human. It authenticates as the deploy service principal and is
  asserted to record `service_principal`, so the path is proven without laundering a workload into
  human review.

---

## Bootstrap runbook (run once, by a tenant admin)

All commands assume `az login` as a principal that can create app registrations and assign app
roles. Replace `opspilot-api` / `opspilot-console` names as desired.

### 1. Register the API and expose it

```bash
# Create the API app registration.
api_app_id=$(az ad app create --display-name opspilot-api \
  --sign-in-audience AzureADMyOrg --query appId -o tsv)

# Set the Application ID URI — this becomes OPSPILOT_API_AUDIENCE (api://<app-id>).
az ad app update --id "$api_app_id" --identifier-uris "api://$api_app_id"
```

### 2. Define the `Approver` app role

```bash
# Allowed for both users and applications, so the smoke service principal can also hold it.
az ad app update --id "$api_app_id" --app-roles '[{
  "allowedMemberTypes": ["User", "Application"],
  "displayName": "Approver",
  "description": "May approve or reject an investigation report.",
  "value": "Approver",
  "id": "'"$(python -c 'import uuid; print(uuid.uuid4())')"'",
  "isEnabled": true
}]'

# A service principal for the API app so role assignments can target it.
az ad sp create --id "$api_app_id"
```

### 3. Register the console as a public SPA client

```bash
console_app_id=$(az ad app create --display-name opspilot-console \
  --sign-in-audience AzureADMyOrg \
  --query appId -o tsv)

# SPA redirect URI = the deployed console page. Repeat for localhost during dev.
az ad app update --id "$console_app_id" \
  --set spa.redirectUris='["https://<app-fqdn>/console"]'

# Let the console request the API's scope (delegated). Grant admin consent in the portal,
# or via: az ad app permission admin-consent --id "$console_app_id"
```

### 4. Grant the approver role

```bash
# To a human reviewer (their user object id):
#   Enterprise applications → opspilot-api → Users and groups → Add, role "Approver".
# To the deploy smoke service principal (so the smoke gate can drive the path):
az rest --method POST \
  --uri "https://graph.microsoft.com/v1.0/servicePrincipals/<smoke-sp-object-id>/appRoleAssignments" \
  --body '{
    "principalId": "<smoke-sp-object-id>",
    "resourceId": "<opspilot-api-sp-object-id>",
    "appRoleId": "<the-Approver-role-id-from-step-2>"
  }'
```

### 5. Token version — issue v2.0 tokens, validate on the app-id

`auth.py` trusts the v2.0 issuer (`https://login.microsoftonline.com/<tid>/v2.0`), so the API must
issue v2 tokens or every real token fails the issuer check. Set it, and note the consequence for the
audience:

```bash
az rest --method PATCH \
  --uri "https://graph.microsoft.com/v1.0/applications/<api-object-id>" \
  --headers "Content-Type=application/json" \
  --body '{"api":{"requestedAccessTokenVersion":2}}'
```

With v2 tokens the `aud` claim is the API's **application (client) id GUID**, *not* `api://<id>`.
So `OPSPILOT_API_AUDIENCE` / `entraApiAudience` is the **bare GUID**. The console requests the scope
`<guid>/.default` (the bare-GUID scope form is accepted); the smoke gate uses
`az account get-access-token --scope "<guid>/.default"` — `--scope`, not `--resource`, or it would
request a v1-shaped token that fails the issuer check.

### 6. Wire the config into the deploy

Pass these into `az deployment group create` (and set the smoke env in the workflow):

| Bicep param / env | Value |
|---|---|
| `entraApiAudience` | the API app-id **GUID** (not `api://…`) |
| `entraConsoleClientId` | the console app id |
| `entraApproverRole` | `Approver` (default) |
| `entraTenantId` | defaults to the deployment tenant |
| `OPSPILOT_SMOKE_AUDIENCE` (workflow env) | the API app-id GUID — flips the smoke decision leg from "verified pause only" to full approve-resume |

### 7. Local manual testing

Pre-authorize the Azure CLI public client on the API once, so `az` can obtain a delegated token
without an interactive-consent prompt:

```bash
az rest --method PATCH \
  --uri "https://graph.microsoft.com/v1.0/applications/<api-object-id>" \
  --headers "Content-Type=application/json" \
  --body '{"api":{"preAuthorizedApplications":[{"appId":"04b07795-8ddb-461a-bbee-02f9e1bf7b46","delegatedPermissionIds":["<scope-id>"]}]}}'

az account get-access-token --scope "<api-app-id-guid>/.default" --query accessToken -o tsv
# Use as: Authorization: Bearer <token>  (your user must hold the Approver role)
```

Until step 6 sets `entraApiAudience`, the deployed decision endpoint fails closed (500) and the
smoke gate exercises the pause + unauthenticated-rejection only, logging loudly that the approval
resume was not tested.

---

## Bootstrap record — this tenant (completed 2026-07-22)

Tenant `9ab80f09-0725-4795-9efb-44c2e1138b07`, resource group `rg-opspilot`, done by
`ryadavillicloud@gmail.com`. **Values below are not secrets** (app ids and object ids are public
identifiers); no client secret exists for either app — reviewers authenticate as themselves and the
console is a public PKCE client.

| Thing | Value |
|---|---|
| API app (client) id — **the audience** | `c9de5ba9-8a5f-4d8f-9d9c-36ba680d71cd` |
| API app object id | `5ebe8a58-ebcb-4232-9b45-4242b0228d72` |
| API service-principal object id | `5f9e37e7-0046-4afc-82ea-d3cacf1f1b3a` |
| `Approver` app-role id | `c4d6ba82-58f9-4d23-b073-9e9499820358` |
| `user_impersonation` scope id | `dc56519c-02ed-4c79-a7b2-16637248294a` |
| Console app (client) id | `72cce6bd-507a-4105-8242-eb2e57e95f01` |
| Console redirect URIs (SPA) | `https://opspilot-api.purplecliff-7bac9746.eastus2.azurecontainerapps.io/console`, `http://localhost:8000/console` |
| `requestedAccessTokenVersion` | `2` (aud = the GUID above, iss = …/v2.0) |
| Role grants | reviewer `ryadavillicloud@gmail.com` (oid `b322d4b0-672c-43f6-8124-f84426b56051`); deploy SP (appId `e73bcc6e-d2b0-45ea-a53a-a9363459a97c`, oid `2504d080-60d7-476b-809b-c3626e3d615d`) |
| Repo variables set | `ENTRA_API_AUDIENCE` = the GUID, `ENTRA_CONSOLE_CLIENT_ID` = the console id |

The deploy workflow passes `entraApiAudience` / `entraConsoleClientId` from those repo variables and
sets `OPSPILOT_SMOKE_AUDIENCE`. **The authenticated path is live** (deploy green #47; the smoke gate
drives the full approve-resume leg, `approval_kind=service_principal`). Verified against a real
token: `iss …/v2.0`, `aud` the GUID, `roles: ["Approver"]`, `ver 2.0`.
