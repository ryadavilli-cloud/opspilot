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

@description('Azure OpenAI account name. Must be globally unique; lowercase alphanumeric + hyphens.')
param openAiAccountName string = toLower('${namePrefix}oai${uniqueString(resourceGroup().id)}')

@description('Chat model to deploy (Azure OpenAI catalog name). gpt-5-mini is the currently-GA cheap tier; the entire gpt-4o/gpt-4.1 family is Deprecating in eastus2 and blocked for new deployments.')
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

@description('Cosmos DB account name: the durable store holding completed investigations and the RetailEase corpus the application reads. Must be globally unique; lowercase alphanumeric + hyphens.')
param cosmosAccountName string = toLower('${namePrefix}-cosmos-${uniqueString(resourceGroup().id)}')

@description('Create the Cosmos DB Built-in Data Contributor role assignment for the app identity. This is a Microsoft.DocumentDB data-plane role assignment (plain Contributor on the account is enough to create it), unlike the Microsoft.Authorization assignments above — kept as its own guard for symmetry and in case the deploy principal ever needs it bootstrapped imperatively instead.')
param manageCosmosRoleAssignment bool = true

@description('Cosmos SQL database holding the application\'s own writable state. Must match AZURE_COSMOS_DATABASE (config.COSMOS_DATABASE).')
param cosmosDatabaseName string = 'opspilot'

@description('Container for completed investigation records. Partitioned by /investigation_id.')
param cosmosInvestigationContainerName string = 'investigations'

@description('Cosmos SQL database holding the RetailEase corpus the application only ever reads. Separate from the OpsPilot database so the read-only grant is scoped to a database rather than enumerated per container.')
param retailEaseDatabaseName string = 'retailease'

@description('Categorized knowledge container: runbooks, service knowledge, and incident history in one container, distinguished by a collection category field. Partitioned by /category, which is what retrieval routes on.')
param knowledgeContainerName string = 'knowledge'

@description('Operational records container: incidents, alerts, deployments, dependencies, logs, and metric series. Hierarchically partitioned by /kind then /service, matching how the capabilities query it.')
param operationalRecordsContainerName string = 'operational-records'

@description('Azure OpenAI embedding deployment used by corpus preparation at load time and by retrieval at query time.')
param embeddingDeploymentName string = 'text-embedding-3-small'

@description('Embedding model for the deployment above. Its dimension count must match the knowledge container vector policy.')
param embeddingModelName string = 'text-embedding-3-small'

@description('Vector dimensions the embedding model emits. Cosmos fixes this per embedding path; changing it means removing and re-adding the path, so it is a parameter rather than a literal.')
param embeddingDimensions int = 1536

@description('Object id of the principal that runs corpus preparation. Corpus preparation writes the RetailEase containers; the application never does, so this grant belongs to a different principal than the app identity. Empty (the default) creates no assignment, which is correct for an environment nobody seeds from.')
param corpusSetupPrincipalId string = ''

@description('Entra tenant id that issues reviewer tokens for the HITL decision endpoint. Injected as AZURE_TENANT_ID. Defaults to the deployment tenant; override only for a cross-tenant setup.')
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
var cosmosDataReaderRoleId = '00000000-0000-0000-0000-000000000001'

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

// Embedding deployment: corpus preparation embeds passages at load time and retrieval embeds the
// query at read time, so both sides must resolve to the same model. It is declared after the chat
// deployment and depends on it, because an Azure OpenAI account serializes deployment writes and
// two parallel creates on the same account intermittently fail with a conflict.
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: embeddingDeploymentName
  dependsOn: [chatDeployment]
  sku: {
    name: 'Standard'
    capacity: 30
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModelName
      version: '1'
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

// Azure Cosmos DB: the durable store holding completed investigations and the RetailEase
// corpus the application reads. Serverless: pay-per-request, no fixed base
// cost at this app's traffic (unlike the ACR Basic tier above, this has none while idle). Keyless:
// disableLocalAuth means the ONLY way in is an Entra token from the app's managed identity via the
// data-plane role assignment below.
//
// The database and containers ARE declared here rather than left to the app. Both
// clients call create_*_if_not_exists, which reads first and only creates on a 404 — but the app
// authenticates with the Cosmos Built-in Data Contributor role, and that is a DATA-plane role:
// it grants item operations, queries, change feed, and readMetadata, NOT container creation, which
// is a management-plane action. So the app can never create these; it can only find them. Declaring
// them here is what makes the read path succeed, and it gives each workload its own container and
// partition key rather than one opaque store.
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-08-15' = {
  name: cosmosAccountName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      { locationName: location, failoverPriority: 0 }
    ]
    // EnableNoSQLVectorSearch cannot be added to an existing account; it is only settable at
    // creation. Verified 2026-08-09 against the previous account, which rejected every container
    // vector policy with "the capability has not been enabled on your account" and could not be
    // updated to gain it. The account was therefore recreated rather than amended.
    capabilities: [
      { name: 'EnableServerless' }
      { name: 'EnableNoSQLVectorSearch' }
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

// One container per workload, each with the partition key its client actually writes. Several
// workloads modeled as one store is what these are separate to avoid:
//
//  - investigations:       /investigation_id   one logical partition per attempt.
//
// The `checkpoints` and `investigation-index` containers were removed when the account was
// recreated for vector search (2026-08-09). Both belonged to the rejected durable-pause and
// idempotency-index machinery. The application holds a running investigation in memory and
// writes it once, on completion, so no code path can recreate either container.
//
// TTL is ENABLED with no default expiry (-1) rather than left off. Off would mean a later TTL
// change needs a container rebuild; -1 keeps items forever today while leaving a real TTL
// available as a property update.
var cosmosContainers = [
  { name: cosmosInvestigationContainerName, partitionKey: '/investigation_id' }
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

// --- RetailEase: the corpus the application reads and never writes -----------------------------
// A separate database, not just separate containers, so the application's read-only grant is one
// assignment scoped to a database rather than one per container that must be extended every time a
// container is added.
resource retailEaseDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-08-15' = {
  parent: cosmos
  name: retailEaseDatabaseName
  properties: {
    resource: {
      id: retailEaseDatabaseName
    }
  }
}

// Knowledge: one container holding the three routed logical collections, distinguished by
// `category`, which is also the partition key because routing selects a category filter.
//
// The vector policy is declared here, but it is NOT a point of no return. Probed 2026-08-09: a
// vectorEmbeddingPolicy can be added to a container that lacks one, and an existing path can be
// removed and re-added at a different dimension. Only in-place modification of a live path is
// refused. The partition key is the genuinely fixed choice.
//
// `/embedding` is excluded from the normal index deliberately. The vector index already covers it,
// and range-indexing a 1536-element float array costs storage and RU for queries nobody issues.
// Pinned to 2024-11-15 rather than the 2024-08-15 used by the other Cosmos resources here:
// `vectorEmbeddingPolicy` and `indexingPolicy.vectorIndexes` were added to the deployment schema in
// 2024-11-15 and do not exist in the earlier contract. The service accepts them either way, but
// declaring them against an API version that does not define them relies on behavior outside the
// declared contract, and Bicep says so (BCP037). Only this resource needs the newer version, so
// only this resource takes it.
resource knowledgeContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  parent: retailEaseDb
  name: knowledgeContainerName
  properties: {
    resource: {
      id: knowledgeContainerName
      partitionKey: {
        paths: ['/category']
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [{ path: '/*' }]
        excludedPaths: [{ path: '/"_etag"/?' }, { path: '/embedding/*' }]
        vectorIndexes: [{ path: '/embedding', type: 'diskANN' }]
      }
      vectorEmbeddingPolicy: {
        vectorEmbeddings: [
          {
            path: '/embedding'
            dataType: 'float32'
            dimensions: embeddingDimensions
            distanceFunction: 'cosine'
          }
        ]
      }
      defaultTtl: -1
    }
  }
}

// Operational records: six record kinds in one container. Hierarchically partitioned because the
// capabilities query on two different axes and no single field serves both. Logs, metrics, and
// deployments are always scoped by service; incidents and alerts by incident, and incidents carry
// no service field at all. `/kind` then `/service` scopes the service-keyed queries fully and
// leaves the 19 service-less documents (7 incidents, 12 dependency edges) under an undefined
// second level, which Cosmos permits.
resource operationalRecordsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-08-15' = {
  parent: retailEaseDb
  name: operationalRecordsContainerName
  properties: {
    resource: {
      id: operationalRecordsContainerName
      partitionKey: {
        paths: ['/kind', '/service']
        kind: 'MultiHash'
        version: 2
      }
      defaultTtl: -1
    }
  }
}

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
            // A running investigation is deliberately ephemeral: it lives in the process that
            // serves the request and is written once, on completion, over the `investigations`
            // container declared above. There is no setting here that could select a durable
            // intermediate store, because the application no longer has one to select.
            {
              name: 'AZURE_COSMOS_ENDPOINT'
              value: cosmos.properties.documentEndpoint
            }
            {
              name: 'AZURE_COSMOS_DATABASE'
              value: cosmosDatabaseName
            }
            {
              name: 'AZURE_COSMOS_INVESTIGATION_CONTAINER'
              value: cosmosInvestigationContainerName
            }
            // The RetailEase corpus the application reads and never writes. Named here so the
            // runtime resolves the same containers corpus preparation wrote, rather than each side
            // defaulting independently.
            {
              name: 'AZURE_COSMOS_RETAILEASE_DATABASE'
              value: retailEaseDatabaseName
            }
            {
              name: 'AZURE_COSMOS_KNOWLEDGE_CONTAINER'
              value: knowledgeContainerName
            }
            {
              name: 'AZURE_COSMOS_OPERATIONAL_RECORDS_CONTAINER'
              value: operationalRecordsContainerName
            }
            {
              name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT'
              value: embeddingDeploymentName
            }
            {
              name: 'AZURE_OPENAI_EMBEDDING_DIMENSIONS'
              value: string(embeddingDimensions)
            }
            // Reviewer identity for the HITL decision endpoint. The tenant + audience are
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

// Corpus preparation embeds passages at load time, so the setup principal needs the OpenAI
// data-plane role as well as its Cosmos write grant. Being subscription Owner does not grant it:
// calling a deployment is a data action, and the control-plane role does not imply it.
// `principalType` is deliberately unset because this principal may be a user or a service
// principal depending on who seeds; ARM infers it, and asserting the wrong one fails the create.
resource openAiUserCorpusSetup 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (manageOpenAiRoleAssignment && !empty(corpusSetupPrincipalId)) {
  name: guid(openai.id, corpusSetupPrincipalId, openAiUserRoleId)
  scope: openai
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId)
    principalId: corpusSetupPrincipalId
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

resource cosmosDataReaderRoleDefinition 'Microsoft.DocumentDB/databaseAccounts/sqlRoleDefinitions@2024-08-15' existing = {
  parent: cosmos
  name: cosmosDataReaderRoleId
}

// The application holds ONE identity with TWO differently scoped data-plane grants, not an
// account-wide one. `runtime-and-deployment.md` requires read and write on the investigations
// container and read-only on every RetailEase container, with the write boundary "enforced by the
// role assignment, not by application convention" (NFR-1). The hosted suite checks exactly that:
// the application writes the Record and is refused a write to any RetailEase container. An
// account-wide contributor grant would make that check unpassable, because the application would
// genuinely be able to rewrite the corpus it is reading.
resource cosmosDataContributor 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-08-15' = if (manageCosmosRoleAssignment) {
  parent: cosmos
  name: guid(cosmos.id, app.id, cosmosDataContributorRoleId, cosmosInvestigationContainerName)
  properties: {
    roleDefinitionId: cosmosDataContributorRoleDefinition.id
    principalId: app.identity.principalId
    scope: '${cosmos.id}/dbs/${cosmosDatabaseName}/colls/${cosmosInvestigationContainerName}'
  }
  dependsOn: [cosmosContainerResources]
}

// Read-only over the whole RetailEase database rather than per container, so adding a corpus
// container later does not silently arrive ungranted or tempt a widening of the grant above.
resource cosmosDataReaderRetailEase 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-08-15' = if (manageCosmosRoleAssignment) {
  parent: cosmos
  name: guid(cosmos.id, app.id, cosmosDataReaderRoleId, retailEaseDatabaseName)
  properties: {
    roleDefinitionId: cosmosDataReaderRoleDefinition.id
    principalId: app.identity.principalId
    scope: '${cosmos.id}/dbs/${retailEaseDatabaseName}'
  }
  dependsOn: [knowledgeContainer, operationalRecordsContainer]
}

// The write half of the corpus boundary, held by a DIFFERENT principal than the application.
// `system-design.md` places corpus preparation outside the application's permissions: the setup
// task writes the RetailEase collections and the application only reads them. Declaring the grant
// here rather than granting it by hand keeps "the setup identity is the only writer" a property of
// the template that survives a redeploy, instead of an undocumented assignment somebody made once.
// Scoped to the RetailEase database only: corpus preparation has no business in `investigations`.
resource cosmosDataContributorCorpusSetup 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-08-15' = if (manageCosmosRoleAssignment && !empty(corpusSetupPrincipalId)) {
  parent: cosmos
  name: guid(cosmos.id, corpusSetupPrincipalId, cosmosDataContributorRoleId, retailEaseDatabaseName)
  properties: {
    roleDefinitionId: cosmosDataContributorRoleDefinition.id
    principalId: corpusSetupPrincipalId
    scope: '${cosmos.id}/dbs/${retailEaseDatabaseName}'
  }
  dependsOn: [knowledgeContainer, operationalRecordsContainer]
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
