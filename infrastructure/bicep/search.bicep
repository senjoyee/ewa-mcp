param location string
param prefix string
param envSuffix string
param tags object = {}
param sku string = 'basic'

var searchName = '${prefix}-search${envSuffix}'

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: searchName
  location: location
  tags: tags
  sku: {
    name: sku
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    semanticSearch: 'free'
  }
}

// Outputs
output endpoint string = 'https://${searchName}.search.windows.net'
output name string = searchName
output apiKey string = search.listQueryKeys().value[0].key
