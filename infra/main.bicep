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

var logAnalyticsName = '${namePrefix}-logs'
var environmentName = '${namePrefix}-env'
var appName = '${namePrefix}-api'
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull built-in role

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
      // No `registries` block here on purpose: the bootstrap image is public, so the
      // app must NOT try to authenticate to ACR at create time (that races the AcrPull
      // role below and times out the revision). CD configures ACR pull-via-identity once
      // the role exists — see .github/workflows/deploy.yml (`az containerapp registry set`).
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

output acrLoginServer string = acr.properties.loginServer
output acrName string = acr.name
output appName string = app.name
output appFqdn string = app.properties.configuration.ingress.fqdn
output environmentName string = env.name
