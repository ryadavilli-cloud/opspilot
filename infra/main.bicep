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
// GlobalStandard bills per token consumed, so this is a ceiling on how fast work may proceed and
// not a reservation: raising it reserves nothing and adds nothing to the bill. 30 was below what
// one investigation needs. A single run pushes 30-54k tokens through in a burst, against a limit
// that was both 30k tokens and 30 requests a minute, so the offline evaluation could not get two
// conditions of a controlled comparison through without being throttled. Sized for the full
// evaluation lane, which is the peak consumer here: it drives the scenario set, a live fixture
// run, a judge call each, and then both comparisons, and the comparisons arrive right behind that
// burst.
param chatModelCapacity int = 300

@description('Azure OpenAI data-plane API version the app calls (AZURE_OPENAI_API_VERSION). 2025-04-01-preview supports the gpt-5 reasoning models; 2024-10-21 predates them.')
param azureOpenAiApiVersion string = '2025-04-01-preview'

@description('Create the Cognitive Services OpenAI User role assignment for the app identity. Set false when the deploy principal lacks RBAC-write (Owner / User Access Administrator) and the grant is bootstrapped imperatively — mirrors manageAcrPullRoleAssignment.')
param manageOpenAiRoleAssignment bool = true

@description('Microsoft Foundry account serving the offline judge model. A separate account from the Azure OpenAI one, because Claude is a partner model served from a Foundry (AIServices) resource\'s /anthropic/ endpoint, which an OpenAI-kind account does not offer. Must be globally unique; lowercase alphanumeric + hyphens.')
param foundryAccountName string = toLower('${namePrefix}foundry${uniqueString(resourceGroup().id)}')

@description('Claude model the judge calls (Foundry catalog name, publisher Anthropic).')
param claudeModelName string = 'claude-opus-5'

@description('Claude model version, pinned. A judge is a measuring instrument, and the model changing underneath it silently breaks comparability across every earlier report, so the version is concrete here and NoAutoUpgrade below. Version 2 is the Azure-hosted realization, which runs on Azure end to end rather than on the partner\'s own infrastructure and is what the rest of this system\'s posture assumes; version 1 is the same model served from Anthropic. Verify the value against the region catalog before deploy (az cognitiveservices model list -l <region>, publisher Anthropic).')
param claudeModelVersion string = '2'

@description('Deployment name the evaluation calls (AZURE_CLAUDE_DEPLOYMENT). Kept equal to the model name for clarity.')
param claudeDeploymentName string = 'claude-opus-5'

@description('GlobalStandard capacity for the judge deployment, in thousands of tokens/min. This is the whole subscription allocation for the model, which nothing else here competes for; the judge itself needs far less, being one sequential call per scenario in an offline evaluation rather than a burst like the investigation path. Raising it above the allocation fails the deployment at preflight rather than queueing.')
param claudeModelCapacity int = 40

@description('Create the Claude model deployment. Set false where the subscription holds no quota for the model named above: Claude quota is allocated per subscription and shared across every region, so a model with a zero allocation cannot be deployed anywhere and fails the whole template at preflight. The account, project, and evaluation grant deploy either way, and the evaluation reports the judge as not run while this is off - mirrors configureAuth and configureAcrPull, which gate on the same class of dependency.')
param deployClaudeModel bool = true

@description('Object id of the principal that runs the offline evaluation. The judge is called from wherever evaluation runs, never from the application, so this grant belongs to a different principal than the app identity, which deliberately holds no access to the judge model. The same principal writes kept evaluation runs to the evaluation container below, which the application only reads. Empty (the default) creates no assignment, which is correct for an environment nobody evaluates from.')
param evaluationPrincipalId string = ''

@description('Organization name sent to Anthropic as attestation with the Claude deployment. Deploying with this block auto-accepts the Anthropic Marketplace offer terms (https://www.anthropic.com/legal/commercial-terms), so it must match the real person or legal entity deploying.')
param claudeOrganizationName string = 'ryadavilli'

@description('Two-letter ISO country code for the Claude deployment attestation.')
@minLength(2)
@maxLength(2)
param claudeCountryCode string = 'US'

@description('Industry for the Claude deployment attestation. Lowercase, from the Foundry portal\'s own list.')
@allowed([
  'technology'
  'finance'
  'healthcare'
  'education'
  'retail'
  'manufacturing'
  'government'
  'media'
  'other'
])
param claudeIndustry string = 'technology'

@description('Cosmos DB account name: the durable store holding completed investigations and the RetailEase corpus the application reads. Must be globally unique; lowercase alphanumeric + hyphens.')
param cosmosAccountName string = toLower('${namePrefix}-cosmos-${uniqueString(resourceGroup().id)}')

@description('Create the Cosmos DB Built-in Data Contributor role assignment for the app identity. This is a Microsoft.DocumentDB data-plane role assignment (plain Contributor on the account is enough to create it), unlike the Microsoft.Authorization assignments above — kept as its own guard for symmetry and in case the deploy principal ever needs it bootstrapped imperatively instead.')
param manageCosmosRoleAssignment bool = true

@description('Cosmos SQL database holding the application\'s own writable state. Must match AZURE_COSMOS_DATABASE (config.COSMOS_DATABASE).')
param cosmosDatabaseName string = 'opspilot'

@description('Container for completed investigation records. Partitioned by /investigation_id.')
param cosmosInvestigationContainerName string = 'investigations'

@description('Container for kept evaluation runs. Partitioned by /run_id. The application reads it and never writes it; the principal running evaluation writes it. Must match AZURE_COSMOS_EVALUATION_CONTAINER (config.COSMOS_EVALUATION_CONTAINER).')
param cosmosEvaluationContainerName string = 'evaluation-runs'

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

@description('Entra tenant the app identity belongs to, injected as AZURE_TENANT_ID. Defaults to the deployment tenant; override only for a cross-tenant setup.')
param entraTenantId string = tenant().tenantId

@description('Key Vault holding the one secret this system has: the client secret built-in authentication redeems an authorization code with. Nothing on a data path uses a key, and this is the front door rather than a data path.')
param keyVaultName string = 'kv${namePrefix}${uniqueString(resourceGroup().id)}'

@description('Name of the secret inside that vault.')
param authClientSecretName string = 'opspilot-auth-client-secret'

@description('Entra application (client) id built-in authentication signs callers in against. Empty until the registration exists, which Bicep cannot create: an app registration is a Graph object rather than an ARM resource.')
param authClientId string = ''

@description('Create the Key Vault Secrets User grant for the app identity. Mirrors manageAcrPullRoleAssignment: false where the grant was made outside this template and redeclaring it would collide.')
param manageKeyVaultRoleAssignment bool = true

@description('Attach the vault-backed secret and turn built-in authentication on. MUST be false on the deploy that first creates the grant above: the app resolves the secret as its own identity, and a revision that starts before that grant has propagated cannot read the vault and fails. Turn it on once the grant exists, exactly as configureAcrPull does for the registry binding.')
param configureAuth bool = false

@description('What this revision reports itself as, injected as OPSPILOT_ENV.')
@allowed([
  'dev'
  'prod'
])
param runtimeEnvironment string = 'prod'

var logAnalyticsName = '${namePrefix}-logs'
var environmentName = '${namePrefix}-env'
var appName = '${namePrefix}-api'
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull built-in role
// Cognitive Services OpenAI User — data-plane inference (chat/completions), NOT deployment
// management. Least privilege for a runtime that only calls the model; Bicep owns the deployment.
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
// Cosmos DB Built-in Data Contributor — the well-known built-in data-plane role id (same value in
// every Cosmos account; not a subscription-scoped built-in role definition like the two above).
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'
// Cognitive Services User — data-plane inference on the Foundry account for the principal that
// runs evaluation. Broader than the OpenAI-specific role above because the judge model is not an
// OpenAI model; still inference-only, with deployment management staying with this template.
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'
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

// Workspace-based, over the workspace above rather than beside it. The application's spans reach
// that workspace already, as console output the environment forwards, so this is the lens over
// telemetry that exists rather than a second sink to send it to twice. Nothing in the container
// points at this component: the connection string is an output, for the step that adopts an
// exporter speaking the ingestion protocol directly.
resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${namePrefix}-insights'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
    IngestionMode: 'LogAnalytics'
  }
}

// The one secret this system holds. Everything on a data path authenticates as the app's identity
// with no key at all; built-in authentication is the exception, because redeeming an authorization
// code is a confidential-client exchange and the platform performing it needs the credential.
//
// RBAC rather than access policies, so the grant below is a role assignment like every other grant
// here. The value is not in this template and never passes through a deployment: it is written to
// the vault once, out of band, and read from it at runtime by the identity that needs it.
resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: entraTenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    // The default, and matched to the live vault deliberately: this value cannot be lowered once
    // set, so a template naming a smaller one is rejected rather than applied.
    softDeleteRetentionInDays: 90
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

// Microsoft Foundry (AIServices) — the offline judge's model host. Keyless like everything else:
// disableLocalAuth means the ONLY way in is an Entra token, and no Anthropic API key exists
// anywhere. The application identity holds no role here and the runtime never constructs the
// judge's adapter, so nothing in a live investigation can reach this account.
//
// Claude in Foundry is sold and operated by Anthropic as a partner offering, and the offer terms
// are accepted by the deployment itself: the resource provider auto-signs the Marketplace
// agreement from the `modelProviderData` attestation the deployment below carries, refusing an
// Anthropic deployment without one. Nothing about the offering has to exist out of band, but the
// attestation is sent to Anthropic and must state the real deployer.
resource foundry 'Microsoft.CognitiveServices/accounts@2025-10-01-preview' = {
  name: foundryAccountName
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: foundryAccountName
    allowProjectManagement: true
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

// The Foundry project the supported realization files the deployment under. Organizational: the
// data plane the judge's adapter calls is the account's /anthropic/ endpoint, and the project is
// how the portal presents what is deployed there.
resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-10-01-preview' = {
  parent: foundry
  name: '${namePrefix}-evaluation'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {}
}

// The judge deployment, pinned. NoAutoUpgrade for the same reason the version parameter is
// concrete: two reports judged by silently different models are not comparable, however alike
// they look on the page.
resource claudeDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-10-01-preview' = if (deployClaudeModel) {
  parent: foundry
  name: claudeDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: claudeModelCapacity
  }
  properties: {
    model: {
      format: 'Anthropic'
      name: claudeModelName
      version: claudeModelVersion
    }
    // Required for an Anthropic deployment: the attestation the provider auto-signs the
    // Marketplace offer from, sent to Anthropic. A deployment without it fails preflight.
    modelProviderData: {
      organizationName: claudeOrganizationName
      countryCode: claudeCountryCode
      industry: claudeIndustry
    }
    versionUpgradeOption: 'NoAutoUpgrade'
    raiPolicyName: 'Microsoft.DefaultV2'
  }
  // Foundry serializes writes under one account, the same way the OpenAI account above
  // serializes its two deployments; and the project must exist before the deployment the
  // portal files under it.
  dependsOn: [foundryProject]
}

// Data-plane inference on the Foundry account for whoever runs the evaluation. `principalType`
// is deliberately unset for the same reason as the corpus-setup grant below: this may be a user
// or a service principal depending on who evaluates, ARM infers it, and asserting the wrong one
// fails the create.
resource claudeUserEvaluation 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(evaluationPrincipalId)) {
  name: guid(foundry.id, evaluationPrincipalId, cognitiveServicesUserRoleId)
  scope: foundry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalId: evaluationPrincipalId
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
//  - evaluation-runs:      /run_id             one kept evaluation run per document, written by
//                                              the evaluation principal and only read by the app.
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
  { name: cosmosEvaluationContainerName, partitionKey: '/run_id' }
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
      // Sourced from the vault rather than passed in. The value never enters this template, a
      // deployment parameter, or a pipeline variable: the platform reads it from the vault as the
      // app's own identity, which is the same way the app reaches Cosmos and the model deployments.
      // Rotating it is a write to the vault, with no redeploy and nothing to update here.
      //
      // Gated for the same reason `registries` is: the grant below has to exist and propagate
      // before a revision can resolve this, and a revision that cannot resolve its secrets does
      // not start.
      secrets: configureAuth ? [
        {
          name: 'auth-client-secret'
          keyVaultUrl: '${vault.properties.vaultUri}secrets/${authClientSecretName}'
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
            // Kept evaluation runs, which the application lists and reads for its read-only view
            // and never writes: the grant below is read-only on this container.
            {
              name: 'AZURE_COSMOS_EVALUATION_CONTAINER'
              value: cosmosEvaluationContainerName
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
            // The tenant the app's identity belongs to. Read by the credential chain, and by
            // built-in authentication when it is configured. Configuration rather than a secret.
            {
              name: 'AZURE_TENANT_ID'
              value: entraTenantId
            }
            // Which environment this revision believes it is. Without it the deployed application
            // reports itself as a local one, which is the sort of thing an operator reads once and
            // then distrusts every other field beside it.
            {
              name: 'OPSPILOT_ENV'
              value: runtimeEnvironment
            }
            // The image this revision was started from. The platform injects the revision name on
            // its own but not the tag, and a process cannot read the tag it was started from, so
            // the one place that knows it is the template that set it.
            {
              name: 'OPSPILOT_IMAGE'
              value: containerImage
            }
            // Spans go to stdout, which the environment forwards to the workspace, which is where
            // a query by investigation id reads them. The default discards every span, so a
            // revision left on it is instrumented and silent.
            {
              name: 'OPSPILOT_TRACE_EXPORTER'
              value: 'stdout'
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
        // One. A run holds its whole investigation in the process serving the request, so a second
        // replica cannot help that run and would only spread health and telemetry across two.
        maxReplicas: 1
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

// Read of the one secret, for the identity that needs it. Guarded like the grants around it,
// because creating a role assignment needs more than Contributor on the scope.
resource authSecretRead 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (manageKeyVaultRoleAssignment) {
  name: guid(vault.id, app.id, keyVaultSecretsUserRoleId)
  scope: vault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Who may call this application. The platform answers it before a request reaches the container, so
// the application holds no authentication code: presence of an authenticated caller is the whole
// check, and every caller that passes it can do everything the application does.
//
// Three things this template cannot create, because they are Microsoft Graph or data-plane objects
// rather than ARM resources. Each is made once, by hand, and an environment rebuilt from this file
// alone will deploy and then refuse every caller until they exist:
//
//   1. the app registration `authClientId` names, with this app's callback as a redirect URI, an
//      identifier URI of `api://<client-id>`, and an audience admitting the accounts it should;
//   2. an app role on that registration, assigned to the principal the deployment workflow runs
//      as. Entra needs a granted permission before it will issue that principal a token for this
//      API; nothing here reads the role, and a person signing in holds none;
//   3. the client secret, written into the vault under `authClientSecretName`. It expires, and
//      when it does this configuration keeps deploying while every sign-in fails, which is why the
//      smoke run authenticates rather than only checking health.
//
// The health paths are excluded because the probes are the platform's own and carry no principal.
// Requiring authentication on them fails every probe, the revision never becomes healthy, and the
// deployment fails on what reads as a broken application. What they disclose is that the source
// answered and which retrieval backend came up, which is the price of being probeable.
resource auth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = if (configureAuth) {
  parent: app
  name: 'current'
  properties: {
    platform: {
      enabled: true
    }
    globalValidation: {
      // Refuse rather than redirect, which is what lets a caller presenting a bearer token be
      // admitted at all: in redirect mode the platform answers a token with a 500 whatever its
      // audience and issuer, so the deployment could be signed into by a person and reached by
      // nothing else. That would leave the smoke run unable to drive an investigation, and the
      // proof that this revision works is worth more than the shape of one refusal.
      //
      // A person is not left holding a 401. `/` is excluded and redirects to the sign-in the
      // platform serves, so the address to share is still the bare one: a visitor lands there,
      // signs in, and arrives at the screen.
      unauthenticatedClientAction: 'Return401'
      excludedPaths: [
        '/'
        '/health'
        '/health/live'
        '/health/ready'
      ]
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: authClientId
          clientSecretSettingName: 'auth-client-secret'
          // Any tenant, which is what the registration's own audience admits. `common` rather
          // than `organizations`, and the difference is not cosmetic: both are multi-tenant, but
          // the metadata `organizations` publishes declares its issuer as a template with the
          // tenant left as a placeholder, and the platform does not substitute it when validating
          // a token presented directly. A caller holding a perfectly good token is answered with
          // a server error rather than a refusal, which is how it was found: the error says the
          // check failed, not that the token did.
          //
          // Personal accounts are not admitted by the wider endpoint. The registration decides
          // that, and it admits work and school accounts only, so `common` costs nothing here.
          //
          // The host comes from the deployment environment rather than being written down, so this
          // is not a template that works in one cloud alone.
          openIdIssuer: '${environment().authentication.loginEndpoint}common/v2.0'
        }
        validation: {
          // Both forms. A token requested for the identifier URI arrives carrying the bare client
          // id as its audience, because the registration issues v2 tokens, so listing only the URI
          // matches nothing that is ever presented.
          allowedAudiences: [
            'api://${authClientId}'
            authClientId
          ]
        }
      }
    }
    login: {
      preserveUrlFragmentsForLogins: false
    }
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

// The application holds ONE identity with THREE differently scoped data-plane grants, not an
// account-wide one: write on the investigations container, read on the evaluation container, and
// read on the RetailEase database. `runtime-and-deployment.md` requires read and write on the investigations
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

// The application reads kept evaluation runs and never writes one. Read-only on that container,
// so no request can write a run: evaluation stays offline after the view exists because the grant
// says so, not because a route declines to.
resource cosmosDataReaderEvaluation 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-08-15' = if (manageCosmosRoleAssignment) {
  parent: cosmos
  name: guid(cosmos.id, app.id, cosmosDataReaderRoleId, cosmosEvaluationContainerName)
  properties: {
    roleDefinitionId: cosmosDataReaderRoleDefinition.id
    principalId: app.identity.principalId
    scope: '${cosmos.id}/dbs/${cosmosDatabaseName}/colls/${cosmosEvaluationContainerName}'
  }
  dependsOn: [cosmosContainerResources]
}

// The write half of that boundary, held by the principal that runs evaluation and scoped to the
// one container it keeps runs in. The same arrangement as corpus preparation below: a different
// principal writes, the application reads. `principalType` is left for ARM to infer, as it is
// there, because whoever keeps runs may be a user or a service principal.
resource cosmosDataContributorEvaluation 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-08-15' = if (manageCosmosRoleAssignment && !empty(evaluationPrincipalId)) {
  parent: cosmos
  name: guid(cosmos.id, evaluationPrincipalId, cosmosDataContributorRoleId, cosmosEvaluationContainerName)
  properties: {
    roleDefinitionId: cosmosDataContributorRoleDefinition.id
    principalId: evaluationPrincipalId
    scope: '${cosmos.id}/dbs/${cosmosDatabaseName}/colls/${cosmosEvaluationContainerName}'
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
// The value AZURE_CLAUDE_ENDPOINT takes: the Foundry resource's Anthropic path, which is where
// the judge's adapter sends its requests.
output claudeEndpoint string = 'https://${foundryAccountName}.services.ai.azure.com/anthropic/'
// Empty while the deployment is gated off, so a reader of the outputs sees that the judge model
// is not there to call rather than a name that resolves to nothing.
output claudeDeploymentName string = deployClaudeModel ? claudeDeploymentName : ''
output foundryAccountName string = foundry.name
output cosmosAccountName string = cosmos.name
output cosmosEndpoint string = cosmos.properties.documentEndpoint
output keyVaultName string = vault.name
output authEnabled bool = configureAuth
output appInsightsName string = insights.name
output appInsightsConnectionString string = insights.properties.ConnectionString
