// Alerta de orçamento da assinatura, criado ANTES de qualquer recurso (exigência do projeto).
// US$ 1 por mês: o objetivo é custo zero, então qualquer consumo real já é motivo para olhar.
// O Azure for Students tem limite de gasto: quando o crédito acaba, a assinatura é desativada, sem
// cobrança. O alerta avisa bem antes disso.
targetScope = 'subscription'

@description('E-mail que recebe os alertas')
param email string

@description('Início do orçamento: primeiro dia do mês corrente')
param inicio string = '${utcNow('yyyy-MM')}-01'

resource orcamento 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'orcamento-mensal-1usd'
  properties: {
    category: 'Cost'
    amount: 1
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: inicio
    }
    notifications: {
      real50: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: [email]
      }
      real100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: [email]
      }
      previsto100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: [email]
      }
    }
  }
}
