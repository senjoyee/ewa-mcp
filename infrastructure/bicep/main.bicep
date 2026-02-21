param location string = resourceGroup().location
param prefix string = 'ewa'
param environment string = ''
param personResponsible string

// Common tags for all resources
var commonTags = {
  PersonResponsible: personResponsible
  Project: 'ewa-mcp'
}
var envSuffix = environment == '' ? '' : '-${environment}'

// Azure AI Search
module search 'search.bicep' = {
  name: 'searchDeploy'
  params: {
    location: location
    prefix: prefix
    envSuffix: envSuffix
    tags: commonTags
  }
}

// Storage Account
module storage 'storage.bicep' = {
  name: 'storageDeploy'
  params: {
    location: location
    prefix: prefix
    envSuffix: envSuffix
    tags: commonTags
  }
}

// Event Grid
module eventgrid 'eventgrid.bicep' = {
  name: 'eventgridDeploy'
  params: {
    location: location
    prefix: prefix
    envSuffix: envSuffix
    tags: commonTags
  }
}

// Container Apps Environment for MCP Server
module containerapp 'containerapp.bicep' = {
  name: 'containerappDeploy'
  params: {
    location: location
    prefix: prefix
    envSuffix: envSuffix
    tags: commonTags
  }
}

// Outputs
output searchEndpoint string = search.outputs.endpoint
output searchName string = search.outputs.name
output storageConnectionString string = storage.outputs.connectionString
output eventgridEndpoint string = eventgrid.outputs.endpoint
output containerAppEnvironmentId string = containerapp.outputs.environmentId
