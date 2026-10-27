const API_URL =
  process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000'

async function requisicao(endpoint: string) {
  const resposta = await fetch(`${API_URL}${endpoint}`)

  if (!resposta.ok) {
    throw new Error(`Erro HTTP ${resposta.status}`)
  }

  return resposta.json()
}

export function buscarSaude() {
  return requisicao('/health')
}

export function buscarLeituras(limite = 20) {
  return requisicao(`/api/leituras?limite=${limite}`)
}