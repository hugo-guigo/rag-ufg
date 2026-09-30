// API do assistente no Azure Container Apps (plano de consumo, escala até zero).
// Criado por scripts/deploy_azure.py; depois disso o GitHub Actions só troca a imagem.
//
// Decisões:
// - Container Apps e não Functions: a API já é um container (Dockerfile da etapa 6), e o plano de
//   consumo tem cota grátis mensal (180 mil vCPU-s, 360 mil GiB-s, 2 milhões de requisições) e não
//   cobra nada com zero réplicas.
// - Imagem no GitHub Container Registry (público, grátis). O Azure Container Registry Basic custa por mês.
// - No máximo 1 réplica: a demo não precisa de mais, e o custo fica previsível.
// - Segredos como secrets do Container App, passados no deploy e nunca gravados no repositório.
// - O GitHub Actions entra por OIDC com uma identidade gerenciada que só pode alterar este app.

@description('Região: a assinatura de estudante aceita só algumas; North Central US é a mais perto do Neon (us-east-1)')
param location string = resourceGroup().location
param nome string = 'rag-ufg'

@description('Imagem completa, ex.: ghcr.io/hugo-guigo/rag-ufg:<sha>')
param imagem string

@secure()
param databaseUrl string
@secure()
param groqApiKey string
@secure()
param salCliente string

@description('Claim sub do token OIDC do GitHub: branch main deste repositório (dono e repositório com ids imutáveis)')
param sujeitoOidc string = 'repo:hugo-guigo@169164791/rag-ufg@1396870437:ref:refs/heads/main'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${nome}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    workspaceCapping: { dailyQuotaGb: json('0.1') } // teto diário de ingestão: logs nunca viram custo relevante
  }
}

resource ambiente 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${nome}'
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
  name: 'ca-${nome}'
  location: location
  properties: {
    managedEnvironmentId: ambiente.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
      }
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'groq-api-key', value: groqApiKey }
        { name: 'sal-cliente', value: salCliente }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: imagem
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'GROQ_API_KEY', secretRef: 'groq-api-key' }
            { name: 'SAL_CLIENTE', secretRef: 'sal-cliente' }
            { name: 'CONFIAR_PROXY', value: '1' } // o ingress do Container Apps informa o IP em X-Forwarded-For
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: [
          { name: 'http', http: { metadata: { concurrentRequests: '10' } } }
        ]
      }
    }
  }
}

resource identidadeDeploy 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${nome}-deploy'
  location: location
}

resource credencialGithub 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: identidadeDeploy
  name: 'github-main'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: sujeitoOidc
    audiences: ['api://AzureADTokenExchange']
  }
}

// Contributor só no Container App (não no grupo nem na assinatura): o deploy troca a imagem e mais nada.
var contributor = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b24988ac-6180-42a0-ab88-20f7382dd24c')
resource permissaoDeploy 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(app.id, identidadeDeploy.id, contributor)
  scope: app
  properties: {
    roleDefinitionId: contributor
    principalId: identidadeDeploy.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

output url string = 'https://${app.properties.configuration.ingress.fqdn}'
output clientIdDeploy string = identidadeDeploy.properties.clientId
