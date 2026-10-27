const API_URL =
  import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function requisicao(endpoint, options = {}) {
  const resposta = await fetch(`${API_URL}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!resposta.ok) {
    let erro

    try {
      erro = await resposta.json()
    } catch {
      erro = null
    }

    throw new Error(
      erro?.detail
        ? typeof erro.detail === 'string'
          ? erro.detail
          : 'Erro de validação dos dados.'
        : `Erro HTTP ${resposta.status}`
    )
  }

  return resposta.json()
}

export function buscarSaude() {
  return requisicao('/health')
}

export function buscarUltimaLeitura() {
  return requisicao('/api/leituras/ultima')
}

export function buscarLeituras(limite = 20) {
  return requisicao(`/api/leituras?limite=${limite}`)
}

export function simularRisco(dados) {
  return requisicao('/api/risco', {
    method: 'POST',
    body: JSON.stringify(dados),
  })
}

export function enviarMensagem(mensagem, sessionId = null) {
  return requisicao('/api/chat', {
    method: 'POST',
    body: JSON.stringify({
      mensagem,
      session_id: sessionId,
    }),
  })
}