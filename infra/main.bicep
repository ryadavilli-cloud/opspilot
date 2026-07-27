// OpsPilot infrastructure — container registry + Container Apps runtime.
// Data services (AI Search, Cosmos, Content Safety) are added later, in the step
// that introduces them. This is the minimal always-deployable footprint.
targetScope = 'resourceGroup'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Short name prefix for resources.')
param namePrefix string = 'opspilot'

@description('Globally-unique ACR name (alphanumeric, 5-50 chars).')
param acrName string = 'acr${namePrefix}${uniqueString(resourceGroup().id)}'

@description('Container image to deploy. Defaults to a public placeholder until CD pushes the real image.')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Ingress target port the container listens on. 8000 matches the real app image (Dockerfile EXPOSE 8000). Only override to 80 when bootstrapping a brand-new environment from scratch that is still on the public placeholder image above.')
param targetPort int = 8000

@description('Minimum replicas. 0 = scale-to-zero (cost ~0). Set to 1 for always-on later.')
param minReplicas int = 0

@description('Create the AcrPull role assignment below. Default true for fresh/reproducible environments. The live environment bootstrapped its identity + AcrPull grant imperatively via az CLI before this template existed (see the acrPull resource comment) — its CD run passes false, since redeclaring the assignment here would collide with the one already outside this template\'s management.')
param manageAcrPullRoleAssignment bool = true

@description('Include the container app `registries` block (ACR pull via the system identity). MUST be false on a fresh bootstrap: the AcrPull role does not exist/propagate yet, so a registries block races it and times the revision out (the bootstrap runs a public placeholder image instead). Steady-state CD passes TRUE — the role already exists, so the declarative deploy OWNS the registry binding. Without this, a no-registries declarative deploy nulls out the binding a separate `az containerapp registry set` configured, and the next fresh image fails to pull (401 ImagePullBackOff).')
param configureAcrPull bool = false

@description('Diagnosis implementation the deployed app runs: single_agent (the LLM planner + triager) or deterministic (the hand-tuned floor). Injected as OPSPILOT_IMPLEMENTATION.')
@allowed([
  'single_agent'
  'deterministic'
])
param implementation string = 'single_agent'

@description('Azure OpenAI account name. Must be globally unique; lowercase alphanumeric + hyphens.')
param openAiAccountName string = toLower('${namePrefix}oai${uniqueString(resourceGroup().id)}')

@description('Chat model to deploy (Azure OpenAI catalog name). gpt-5-mini is the currently-GA cheap tier; the entire gpt-4o/gpt-4.1 family is Deprecating in eastus2 and blocked for new deployments. Interim demo tier only; production routing is Claude-on-Foundry (config.PROD_MODELS, G-45).')
param chatModelName string = 'gpt-5-mini'

@description('Chat model version. Verify it is GA in the target region before deploy (az cognitiveservices model list -l <region>).')
param chatModelVersion string = '2025-08-07'

@description('Deployment name the app calls (AZURE_OPENAI_DEPLOYMENT). Kept equal to the model name for clarity.')
param chatDeploymentName string = 'gpt-5-mini'

@description('GlobalStandard capacity for the chat deployment, in thousands of tokens/min (TPM).')
param chatModelCapacity int = 30

@description('Azure OpenAI data-plane API version the app calls (AZURE_OPENAI_API_VERSION). 2025-04-01-preview supports the gpt-5 reasoning models; 2024-10-21 predates them.')
param azureOpenAiApiVersion string = '2025-04-01-preview'

@description('Create the Cognitive Services OpenAI User role assignment for the app identity. Set false when the deploy principal lacks RBAC-write (Owner / User Access Administrator) and the grant is bootstrapped imperatively — mirrors manageAcrPullRoleAssignment.')
param manageOpenAiRoleAssignment bool = true

@description('Cosmos DB account name — the durable store behind the LangGraph checkpointer (Stage 5b) and the async investigation repository (Stage 5c), pulled forward from Stage 8. Must be globally unique; lowercase alphanumeric + hyphens.')
param cosmosAccountName string = toLower('${namePrefix}-cosmos-${uniqueString(resourceGroup().id)}')

@description('Create the Cosmos DB Built-in Data Contributor role assignment for the app identity. This is a Microsoft.DocumentDB data-plane role assignment (plain Contributor on the account is enough to create it), unlike the Microsoft.Authorization assignments above — kept as its own guard for symmetry and in case the deploy principal ever needs it bootstrapped imperatively instead.')
param manageCosmosRoleAssignment bool = true

@description('Cosmos SQL database holding every OpsPilot container. Must match AZURE_COSMOS_DATABASE (config.COSMOS_DATABASE).')
param cosmosDatabaseName string = 'opspilot'

@description('Container for LangGraph checkpoints — what makes an awaiting_approval pause survive a restart (G-02). Partition key is fixed at /partition_key by CosmosDBSaverSync.')
param cosmosCheckpointContainerName string = 'checkpoints'

@description('Container for the async investigation records the poll endpoint reads. Partitioned by /investigation_id.')
param cosmosInvestigationContainerName string = 'investigations'

@description('Idempotency index for (incident_id, summary, workflow version). Partitioned by /id, which IS the idempotency key, making create-if-not-exists an atomic compare-and-swap.')
param cosmosInvestigationIndexContainerName string = 'investigation-index'

@description('Entra tenant id that issues reviewer tokens for the HITL decision endpoint (G-01). Injected as AZURE_TENANT_ID. Defaults to the deployment tenant; override only for a cross-tenant setup.')
param entraTenantId string = tenant().tenantId

@description('This API\'s audience — the API app-registration\'s application (client) id GUID, which is the aud claim in the v2.0 tokens Entra issues for it (requestedAccessTokenVersion=2). The decision endpoint rejects any token whose aud does not match, so a token for another app cannot approve here. Empty until the app registration is bootstrapped (see the reviewer-identity ADR); while unset the decision endpoint returns 500 (fail-closed) rather than accepting unvalidated tokens.')
param entraApiAudience string = ''

@description('App role a principal must carry to approve (OPSPILOT_APPROVER_ROLE). Authentication proves who; this proves allowed-to-publish.')
param entraApproverRole string = 'Approver'

@description('Public Entra app (client) id the operator console signs in with (OPSPILOT_CONSOLE_CLIENT_ID). Not a secret — it is served to the browser. Empty disables the console\'s decision controls; the API still validates tokens from any other authenticated client.')
param entraConsoleClientId string = ''

var logAnalyticsName = '${namePrefix}-logs'
var environmentName = '${namePrefix}-env'
var appName = '${namePrefix}-api'
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull built-in role
// Cognitive Services OpenAI User — data-plane inference (chat/completions), NOT deployment
// management. Least privilege for a runtime that only calls the model; Bicep owns the deployment.
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
// Cosmos DB Built-in Data Contributor — the well-known built-in data-plane role id (same value in
// every Cosmos account; not a subscription-scoped built-in role definition like the two above).
var cosmosDataContributorRoleId = '00000000-0000-0000-0000-000000000002'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

// Azure OpenAI (classic) — the production LLM host. Keyless: local key auth is DISABLED
// (disableLocalAuth), so the ONLY way in is an Entra token from the app's managed identity, granted
// Cognitive Services OpenAI User below. customSubDomainName is required for token-based auth.
resource openai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: openAiAccountName
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: openAiAccountName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

// The chat model the app calls (AZURE_OPENAI_DEPLOYMENT). GlobalStandard routes globally for the
// widest quota availability; capacity is TPM in thousands. A single deployment per account is fine.
resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: chatDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: chatModelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: chatModelName
      version: chatModelVersion
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

// Azure Cosmos DB — the durable store behind both the LangGraph checkpointer (Stage 5b) and the
// async investigation resource repository (Stage 5c). Serverless: pay-per-request, no fixed base
// cost at this app's traffic (unlike the ACR Basic tier above, this has none while idle). Keyless:
// disableLocalAuth means the ONLY way in is an Entra token from the app's managed identity via the
// data-plane role assignment below.
//
// The database and containers ARE declared here (Stage 5f, G-02) rather than left to the app. Both
// clients call create_*_if_not_exists, which reads first and only creates on a 404 — but the app
// authenticates with the Cosmos Built-in Data Contributor role, and that is a DATA-plane role:
// it grants item operations, queries, change feed, and readMetadata, NOT container creation, which
// is a management-plane action. So the app can never create these; it can only find them. Declaring
// them here is what makes the read path succeed, and it is also the first slice of the G-48
// container split (each workload its own container + partition key), rather than one opaque store.
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-08-15' = {
  name: cosmosAccountName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      { locationName: location, failoverPriority: 0 }
    ]
    capabilities: [
      { name: 'EnableServerless' }
    ]
    disableLocalAuth: true
  }
}

resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-08-15' = {
  parent: cosmos
  name: cosmosDatabaseName
  properties: {
    resource: {
      id: cosmosDatabaseName
    }
  }
}

// One container per workload, each with the partition key its client actually writes (G-48's
// "several workloads modeled as one store" is why these are separate rather than a single blob):
//
//  - checkpoints:          /partition_key      LangGraph CosmosDBSaverSync's own key path. Not a
//                                              free choice — the saver queries `c.partition_key`,
//                                              so a different path silently breaks every read.
//  - investigations:       /investigation_id   one logical partition per attempt.
//  - investigation-index:  /id                 idempotency index; `id = idempotency_key` makes
//                                              create-if-not-exists an atomic compare-and-swap.
//
// TTL is ENABLED with no default expiry (-1) rather than left off. Off would mean a later TTL
// change needs a container rebuild; -1 keeps items forever today while letting G-48 set a real
// per-workload TTL (checkpoints bounded by the longest legitimate pause, investigations unbounded)
// as a property update. A checkpoint that expired under a long pause would silently destroy the
// durability this stage exists to prove, so no expiry is set here.
var cosmosContainers = [
  { name: cosmosCheckpointContainerName, partitionKey: '/partition_key' }
  { name: cosmosInvestigationContainerName, partitionKey: '/investigation_id' }
  { name: cosmosInvestigationIndexContainerName, partitionKey: '/id' }
]

resource cosmosContainerResources 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-08-15' = [
  for c in cosmosContainers: {
    parent: cosmosDb
    name: c.name
    properties: {
      resource: {
        id: c.name
        partitionKey: {
          paths: [c.partitionKey]
          kind: 'Hash'
        }
        defaultTtl: -1
      }
    }
  }
]

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: { type: 'SystemAssigned' }
  // Wait for the model deployment (not just the account) so the first revision can serve
  // single_agent immediately — the post-deploy smoke test investigates as soon as it is ready.
  dependsOn: [
    chatDeployment
  ]
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: {
        external: true
        // Historical note: this defaulted to 80 to match the public hello-world placeholder
        // image used to bootstrap the very first deploy — a real image and the AcrPull role
        // can't both be wired at create time (see the `registries` comment below), so the very
        // first revision had to run the placeholder on its own port. 8000 (the default) is
        // correct once a real image is deployed.
        targetPort: targetPort
        transport: 'auto'
      }
      // ACR pull via the app's system identity — declared here (not via a separate imperative
      // `az containerapp registry set`) so a declarative deploy cannot null it out afterward, which
      // is exactly what broke the pull before (401 ImagePullBackOff on every fresh image). Gated on
      // `configureAcrPull`: a fresh bootstrap leaves it EMPTY because the AcrPull role does not exist
      // yet and a registries block would race the not-yet-propagated grant and time the revision out
      // (that bootstrap runs a public placeholder image). Steady-state CD passes true; the role
      // already exists, so binding here is safe and durable.
      registries: configureAcrPull ? [
        {
          server: '${acrName}.azurecr.io'
          identity: 'system'
        }
      ] : []
    }
    template: {
      containers: [
        {
          name: appName
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          // LLM runtime config layered on top of the image's ENV (corpus paths + bm25 backend stay
          // baked in the Dockerfile). No key here or anywhere: AZURE_OPENAI_API_KEY is intentionally
          // absent, so the client authenticates keyless via this app's managed identity.
          env: [
            {
              name: 'OPSPILOT_IMPLEMENTATION'
              value: implementation
            }
            {
              name: 'OPSPILOT_LLM_PROVIDER'
              value: 'azure'
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: openai.properties.endpoint
            }
            {
              name: 'AZURE_OPENAI_DEPLOYMENT'
              value: chatDeploymentName
            }
            {
              name: 'AZURE_OPENAI_API_VERSION'
              value: azureOpenAiApiVersion
            }
            // HITL state stores — DURABLE (Stage 5f, G-02). Both are Cosmos-backed, keyless via the
            // app's managed identity. BOTH must be cosmos for the pause to survive a restart: the
            // checkpointer holds the LangGraph state the graph resumes from, and the repository
            // holds the record `GET /investigations/{id}` reads. Either one left in memory loses
            // half the round trip — an interrupt that cannot resume, or a resume nobody can poll.
            //
            // #41 reverted these to memory because the containers and the data-plane role assignment
            // did not exist yet, so CosmosClient init 500'd every request. Both now exist above, and
            // the containers are declared rather than self-provisioned because the data-plane role
            // cannot create them.
            {
              name: 'OPSPILOT_INVESTIGATION_REPOSITORY'
              value: 'cosmos'
            }
            {
              name: 'OPSPILOT_CHECKPOINTER'
              value: 'cosmos'
            }
            {
              name: 'AZURE_COSMOS_ENDPOINT'
              value: cosmos.properties.documentEndpoint
            }
            {
              name: 'AZURE_COSMOS_DATABASE'
              value: cosmosDatabaseName
            }
            {
              name: 'AZURE_COSMOS_CHECKPOINT_CONTAINER'
              value: cosmosCheckpointContainerName
            }
            {
              name: 'AZURE_COSMOS_INVESTIGATION_CONTAINER'
              value: cosmosInvestigationContainerName
            }
            {
              name: 'AZURE_COSMOS_INVESTIGATION_INDEX_CONTAINER'
              value: cosmosInvestigationIndexContainerName
            }
            // Reviewer identity for the HITL decision endpoint (G-01). The tenant + audience are
            // what a reviewer token is validated against; the approver role is what it must carry
            // to publish. These are configuration, not secrets — the app holds no client secret,
            // because reviewers authenticate as themselves and the console is a public PKCE client.
            // AZURE_OPENAI_API_KEY-style absence of any secret is deliberate and total here too.
            {
              name: 'AZURE_TENANT_ID'
              value: entraTenantId
            }
            {
              name: 'OPSPILOT_API_AUDIENCE'
              value: entraApiAudience
            }
            {
              name: 'OPSPILOT_APPROVER_ROLE'
              value: entraApproverRole
            }
            {
              name: 'OPSPILOT_CONSOLE_CLIENT_ID'
              value: entraConsoleClientId
            }
          ]
          // Port is the app's actual listen port (Dockerfile EXPOSE 8000), independent of the
          // bootstrap-only `targetPort` ingress override above — the real image always listens
          // on 8000.
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health/live'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health/ready'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
              successThreshold: 1
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: 3
      }
    }
  }
}

// Let the app's managed identity pull images from ACR.
// The live environment's role assignment was bootstrapped imperatively via `az` CLI before this
// resource existed (a `registries` block races AcrPull at create time — see the ingress comment
// above), so it is NOT managed by this guid(...)-named resource there. Azure rejects a second role
// assignment with the same (scope, roleDefinitionId, principalId) even under a different name, so
// CD against that environment passes manageAcrPullRoleAssignment=false. Fresh/reproducible
// environments (no prior imperative bootstrap) should leave the true default in place.
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (manageAcrPullRoleAssignment) {
  name: guid(acr.id, app.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Keyless auth to Azure OpenAI: grant the app's managed identity data-plane inference on the
// account. Guarded like AcrPull — creating a role assignment needs Owner / User Access Administrator
// on the scope; set manageOpenAiRoleAssignment=false when the deploy principal has only Contributor
// and the grant is bootstrapped imperatively (`az role assignment create`).
resource openAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (manageOpenAiRoleAssignment) {
  name: guid(openai.id, app.id, openAiUserRoleId)
  scope: openai
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId)
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Keyless auth to Cosmos DB: grant the app's managed identity data-plane read/write on the account.
// Unlike the two assignments above, this is a Microsoft.DocumentDB data-plane role assignment, not
// a Microsoft.Authorization one — creating it only needs plain Contributor on the Cosmos account
// (which the deploy principal already has via Contributor on the resource group), not Owner / User
// Access Administrator. Guard param kept for symmetry with the other two regardless.
resource cosmosDataContributorRoleDefinition 'Microsoft.DocumentDB/databaseAccounts/sqlRoleDefinitions@2024-08-15' existing = {
  parent: cosmos
  name: cosmosDataContributorRoleId
}

resource cosmosDataContributor 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-08-15' = if (manageCosmosRoleAssignment) {
  parent: cosmos
  name: guid(cosmos.id, app.id, cosmosDataContributorRoleId)
  properties: {
    roleDefinitionId: cosmosDataContributorRoleDefinition.id
    principalId: app.identity.principalId
    scope: cosmos.id
  }
}

output acrLoginServer string = acr.properties.loginServer
output acrName string = acr.name
output appName string = app.name
output appFqdn string = app.properties.configuration.ingress.fqdn
output environmentName string = env.name
output openAiEndpoint string = openai.properties.endpoint
output openAiAccountName string = openai.name
output cosmosAccountName string = cosmos.name
output cosmosEndpoint string = cosmos.properties.documentEndpoint
output implementation string = implementation
