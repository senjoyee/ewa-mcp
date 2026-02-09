param location string
param prefix string
param environment string
param tags object = {}

var openaiName = '${prefix}-openai-${environment}'

resource openai 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' = {
  name: openaiName
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: openaiName
    publicNetworkAccess: 'Enabled'
  }
}

// GPT-5.2 Vision deployment
resource gpt52Deployment 'Microsoft.CognitiveServices/accounts/deployments@2023-10-01-preview' = {
  parent: openai
  name: 'gpt-5.2'
  sku: {
    name: 'Standard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.2'
      version: '2024-08-06'
    }
  }
}

// Text Embedding deployment
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-10-01-preview' = {
  parent: openai
  name: 'text-embedding-3-small'
  sku: {
    name: 'Standard'
    capacity: 50
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-small'
      version: '1'
    }
  }
  dependsOn: [
    gpt52Deployment
  ]
}

// Outputs
output endpoint string = openai.properties.endpoint
output name string = openaiName
output apiKey string = openai.listKeys().key1
