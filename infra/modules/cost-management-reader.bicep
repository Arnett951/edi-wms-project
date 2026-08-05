// Subscription-scoped role assignment, split into its own module because
// ARM requires a resource's scope to match its deployment's targetScope --
// the parent template deploys at resource-group scope, so this one piece
// (Cost Management is subscription-level) needs its own subscription-scoped
// deployment. See main.bicep's costManagementReaderAssignment module call.
targetScope = 'subscription'

@description('Principal ID of the identity to grant Cost Management Reader to')
param principalId string

resource costManagementReaderAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, principalId, 'CostManagementReader')
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '72fafb9e-0641-4937-9268-a91bfd8191a3')
  }
}
