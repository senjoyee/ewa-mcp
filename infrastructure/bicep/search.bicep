param location string
param prefix string
param environment string
param sku string = 'standard'

var searchName = '${prefix}-search-${environment}'

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: searchName
  location: location
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
