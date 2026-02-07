param location string
param prefix string
param environment string

var topicName = '${prefix}-events-${environment}'

resource eventGridTopic 'Microsoft.EventGrid/topics@2023-12-15-preview' = {
  name: topicName
  location: location
  properties: {
    inputSchema: 'EventGridSchema'
    publicNetworkAccess: 'Enabled'
  }
}

// Outputs
output endpoint string = eventGridTopic.properties.endpoint
output name string = topicName
output key string = eventGridTopic.listKeys().key1
