param location string = resourceGroup().location
param appName string = 'jiralite'
param containerImage string
param containerCpu string = '0.5'
param containerMemory string = '1.0Gi'

@secure()
param postgresAdminPassword string
param postgresAdminLogin string = 'jiraliteadmin'
param postgresServerName string = 'jiralite-pg'
param postgresDbName string = 'jiralite'

param containerAppEnvName string = 'jiralite-env'
param logAnalyticsName string = 'jiralite-law'

resource law 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource acaEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppEnvName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: law.properties.customerId
        sharedKey: law.listKeys().primarySharedKey
      }
    }
  }
}

resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: postgresServerName
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    version: '16'
    storage: {
      storageSizeGB: 32
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
  }
}

resource pgDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  name: '${pg.name}/${postgresDbName}'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: acaEnv.id
    configuration: {
      ingress: {
        external: false
        targetPort: 8000
        transport: 'auto'
      }
      secrets: []
    }
    template: {
      containers: [
        {
          name: 'jiralite'
          image: containerImage
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          env: [
            {
              name: 'APP_NAME'
              value: 'JiraLite'
            }
            {
              name: 'APP_ENV'
              value: 'production'
            }
            {
              name: 'APP_HOST'
              value: '0.0.0.0'
            }
            {
              name: 'APP_PORT'
              value: '8000'
            }
            {
              name: 'DATABASE_URL'
              value: 'postgresql+psycopg://${postgresAdminLogin}:${postgresAdminPassword}@${pg.name}.postgres.database.azure.com:5432/${postgresDbName}'
            }
            {
              name: 'DEFAULT_PROJECT_KEY'
              value: 'TEST'
            }
            {
              name: 'LOG_LEVEL'
              value: 'INFO'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
      }
    }
  }
  dependsOn: [
    pgDb
  ]
}
