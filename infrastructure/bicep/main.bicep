param location string = resourceGroup().location
param prefix string = 'ewa'
param environment string = ''
param personResponsible string

// ---------------------------------------------------------------------------
// Event Grid → Function trigger wiring
// Set these after the Function App is deployed so the Event Subscription
// can be created pointing at the live function endpoint.
// ---------------------------------------------------------------------------
@description('Hostname of the Azure Function App (e.g. ewa-processor-prod.azurewebsites.net)')
param functionAppHostname string = ''

@description('Function-level auth key for the ProcessEwaBlob endpoint')
@secure()
param functionKey string = ''

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

// Storage Account + Event Grid System Topic + Event Subscription
module storage 'storage.bicep' = {
  name: 'storageDeploy'
  params: {
    location: location
    prefix: prefix
    envSuffix: envSuffix
    tags: commonTags
    functionAppHostname: functionAppHostname
    functionKey: functionKey
  }
}

// Event Grid Custom Topic (used for processing status events published BY the function)
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
output storageSystemTopicName string = storage.outputs.systemTopicName
output eventgridEndpoint string = eventgrid.outputs.endpoint
output containerAppEnvironmentId string = containerapp.outputs.environmentId
