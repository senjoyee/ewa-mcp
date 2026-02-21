param location string
param prefix string
param envSuffix string
param tags object = {}

// Function App hostname to wire Event Subscription to (e.g. ewa-processor-prod.azurewebsites.net)
param functionAppHostname string = ''
// Function key used in the webhook URL (?code=<key>)
param functionKey string = ''

var storageName = '${prefix}stg${envSuffix}${uniqueString(resourceGroup().id)}'
var systemTopicName = '${prefix}-blob-events${envSuffix}'
var subscriptionName = 'ewa-blob-trigger'
var functionWebhookUrl = 'https://${functionAppHostname}/api/ProcessEwaBlob?code=${functionKey}'

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: take(storageName, 24)
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

// Blob Services
resource blobServices 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storage
  name: 'default'
}

// Blob container for EWA uploads
resource blobContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobServices
  name: 'ewa-uploads'
  properties: {
    publicAccess: 'None'
  }
}

// ---------------------------------------------------------------------------
// Event Grid System Topic – listens to BlobCreated events on this storage account
// ---------------------------------------------------------------------------
resource systemTopic 'Microsoft.EventGrid/systemTopics@2023-12-15-preview' = {
  name: systemTopicName
  location: location
  tags: tags
  properties: {
    source: storage.id
    topicType: 'Microsoft.Storage.StorageAccounts'
  }
}

// ---------------------------------------------------------------------------
// Event Subscription – routes BlobCreated events to the Azure Function HTTP endpoint
// (Only created when functionAppHostname is provided)
// ---------------------------------------------------------------------------
resource eventSubscription 'Microsoft.EventGrid/systemTopics/eventSubscriptions@2023-12-15-preview' = if (!empty(functionAppHostname)) {
  parent: systemTopic
  name: subscriptionName
  properties: {
    destination: {
      endpointType: 'WebHook'
      properties: {
        endpointUrl: functionWebhookUrl
        maxEventsPerBatch: 1
        preferredBatchSizeInKilobytes: 64
      }
    }
    filter: {
      includedEventTypes: [
        'Microsoft.Storage.BlobCreated'
      ]
      subjectBeginsWith: '/blobServices/default/containers/ewa-uploads/'
      subjectEndsWith: '.pdf'
    }
    eventDeliverySchema: 'EventGridSchema'
    retryPolicy: {
      maxDeliveryAttempts: 5
      eventTimeToLiveInMinutes: 60
    }
  }
}

// Outputs
output connectionString string = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
output storageAccountName string = storage.name
output systemTopicName string = systemTopic.name
