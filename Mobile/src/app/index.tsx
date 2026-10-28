import { useCallback, useEffect, useState } from 'react'
import {
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native'

import {
  buscarLeituras,
  buscarSaude,
} from '../services/api'

type Leitura = {
  id: number
  risco: number
  faixa: 'baixo' | 'moderado' | 'alto'
  bpm: number
  temperatura: number
  spo2: number | null
  device_id: string
  recebido_em: string
  recomendacoes: string[]
  aviso: string
}

type Saude = {
  status: string
  modelo_carregado: boolean
  watson_configurado: boolean
}

export default function HomeScreen() {
  const [leituras, setLeituras] = useState<Leitura[]>([])
  const [saude, setSaude] = useState<Saude | null>(null)
  const [erro, setErro] = useState('')
  const [atualizando, setAtualizando] = useState(false)

  const ultima = leituras[0]

  const atualizar = useCallback(async () => {
    try {
      const [status, historico] = await Promise.all([
        buscarSaude(),
        buscarLeituras(20),
      ])

      setSaude(status)
      setLeituras(historico)
      setErro('')
    } catch {
      setErro('Não foi possível conectar ao backend.')
    } finally {
      setAtualizando(false)
    }
  }, [])

  useEffect(() => {
    const inicio = setTimeout(() => {
      atualizar()
    }, 0)

    const intervalo = setInterval(() => {
      atualizar()
    }, 5000)

    return () => {
      clearTimeout(inicio)
      clearInterval(intervalo)
    }
  }, [atualizar])

  function porcentagemRisco() {
    if (ultima?.risco === undefined) return '--'
    return `${Math.round(ultima.risco * 100)}%`
  }

  function corRisco() {
    if (ultima?.faixa === 'alto') return '#dc2626'
    if (ultima?.faixa === 'moderado') return '#d97706'
    if (ultima?.faixa === 'baixo') return '#15803d'

    return '#64748b'
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={atualizando}
          onRefresh={() => {
            setAtualizando(true)
            atualizar()
          }}
        />
      }
    >
      <View style={styles.header}>
        <Text style={styles.logo}>CardioIA</Text>

        <Text style={styles.subtitulo}>
          Monitoramento inteligente
        </Text>

        <View style={styles.status}>
          <View
            style={[
              styles.statusDot,
              {
                backgroundColor:
                  saude?.status === 'ok'
                    ? '#4ade80'
                    : '#fca5a5',
              },
            ]}
          />

          <Text style={styles.statusTexto}>
            {saude?.status === 'ok'
              ? 'Sistema online'
              : 'Sistema offline'}
          </Text>
        </View>
      </View>

      <View style={styles.area}>
        <Text style={styles.eyebrow}>
          PAINEL DE MONITORAMENTO
        </Text>

        <Text style={styles.titulo}>
          Visão geral do paciente
        </Text>

        <Text style={styles.descricao}>
          Atualização automática a cada 5 segundos.
        </Text>

        {erro ? (
          <View style={styles.erro}>
            <Text style={styles.erroTitulo}>
              Backend indisponível
            </Text>

            <Text style={styles.erroTexto}>
              {erro}
            </Text>
          </View>
        ) : null}

        <View style={styles.cardRisco}>
          <Text style={styles.cardTitulo}>
            Risco cardíaco
          </Text>

          <Text
            style={[
              styles.risco,
              { color: corRisco() },
            ]}
          >
            {porcentagemRisco()}
          </Text>

          <Text
            style={[
              styles.faixa,
              { color: corRisco() },
            ]}
          >
            {ultima?.faixa?.toUpperCase() || 'SEM DADOS'}
          </Text>
        </View>

        <View style={styles.metricas}>
          <View style={styles.cardMetrica}>
            <Text style={styles.cardTitulo}>
              Frequência cardíaca
            </Text>

            <Text style={styles.valor}>
              {ultima?.bpm ?? '--'}
              <Text style={styles.unidade}>
                {' '}bpm
              </Text>
            </Text>
          </View>

          <View style={styles.cardMetrica}>
            <Text style={styles.cardTitulo}>
              SpO₂
            </Text>

            <Text style={styles.valor}>
              {ultima?.spo2 ?? '--'}
              <Text style={styles.unidade}>
                {' '}%
              </Text>
            </Text>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitulo}>
            Temperatura
          </Text>

          <Text style={styles.valor}>
            {ultima?.temperatura ?? '--'}
            <Text style={styles.unidade}>
              {' '}°C
            </Text>
          </Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.secaoTitulo}>
            Protocolos acionados
          </Text>

          {ultima?.recomendacoes?.length ? (
            ultima.recomendacoes.map((item, index) => (
              <View
                key={`${item}-${index}`}
                style={styles.protocolo}
              >
                <View style={styles.alerta}>
                  <Text style={styles.alertaTexto}>
                    !
                  </Text>
                </View>

                <Text style={styles.protocoloTexto}>
                  {item}
                </Text>
              </View>
            ))
          ) : (
            <Text style={styles.vazio}>
              Nenhum protocolo acionado.
            </Text>
          )}
        </View>

        <View style={styles.card}>
          <Text style={styles.secaoTitulo}>
            Dispositivo
          </Text>

          <Text style={styles.label}>
            Identificação
          </Text>

          <Text style={styles.info}>
            {ultima?.device_id ?? '--'}
          </Text>

          <Text style={styles.label}>
            Modelo preditivo
          </Text>

          <Text style={styles.info}>
            {saude?.modelo_carregado
              ? 'Disponível'
              : 'Indisponível'}
          </Text>
        </View>

        <View style={styles.aviso}>
          <Text style={styles.avisoTexto}>
            {ultima?.aviso ||
              'Protótipo acadêmico com dados sintéticos; não substitui avaliação médica.'}
          </Text>
        </View>
      </View>
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f4f7fb',
  },

  content: {
    paddingBottom: 40,
  },

  header: {
    backgroundColor: '#b91c1c',
    paddingHorizontal: 22,
    paddingTop: 56,
    paddingBottom: 24,
  },

  logo: {
    color: '#ffffff',
    fontSize: 28,
    fontWeight: '800',
  },

  subtitulo: {
    color: '#fecaca',
    marginTop: 4,
  },

  status: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 18,
    gap: 8,
  },

  statusDot: {
    width: 9,
    height: 9,
    borderRadius: 5,
  },

  statusTexto: {
    color: '#ffffff',
    fontWeight: '600',
  },

  area: {
    padding: 18,
  },

  eyebrow: {
    color: '#b91c1c',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 1.4,
    marginTop: 8,
  },

  titulo: {
    color: '#172033',
    fontSize: 30,
    fontWeight: '800',
    marginTop: 6,
  },

  descricao: {
    color: '#667085',
    marginTop: 5,
    marginBottom: 20,
  },

  erro: {
    backgroundColor: '#fff1f2',
    borderColor: '#fecaca',
    borderWidth: 1,
    borderRadius: 14,
    padding: 15,
    marginBottom: 16,
  },

  erroTitulo: {
    color: '#991b1b',
    fontWeight: '800',
  },

  erroTexto: {
    color: '#b91c1c',
    marginTop: 3,
  },

  cardRisco: {
    backgroundColor: '#ffffff',
    borderRadius: 18,
    padding: 20,
    marginBottom: 14,
  },

  card: {
    backgroundColor: '#ffffff',
    borderRadius: 18,
    padding: 20,
    marginBottom: 14,
  },

  metricas: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 14,
  },

  cardMetrica: {
    flex: 1,
    backgroundColor: '#ffffff',
    borderRadius: 18,
    padding: 18,
  },

  cardTitulo: {
    color: '#667085',
    fontWeight: '600',
    marginBottom: 14,
  },

  risco: {
    fontSize: 48,
    fontWeight: '800',
  },

  faixa: {
    fontWeight: '800',
    marginTop: 4,
  },

  valor: {
    color: '#172033',
    fontSize: 30,
    fontWeight: '800',
  },

  unidade: {
    color: '#667085',
    fontSize: 14,
    fontWeight: '600',
  },

  secaoTitulo: {
    color: '#172033',
    fontSize: 18,
    fontWeight: '800',
    marginBottom: 15,
  },

  protocolo: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff7f7',
    padding: 12,
    borderRadius: 12,
    marginBottom: 9,
    gap: 10,
  },

  alerta: {
    backgroundColor: '#dc2626',
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
  },

  alertaTexto: {
    color: '#ffffff',
    fontWeight: '800',
  },

  protocoloTexto: {
    flex: 1,
    color: '#475467',
  },

  vazio: {
    color: '#94a3b8',
  },

  label: {
    color: '#98a2b3',
    fontSize: 12,
    marginTop: 10,
  },

  info: {
    color: '#172033',
    fontWeight: '700',
    marginTop: 3,
  },

  aviso: {
    backgroundColor: '#fff7ed',
    borderRadius: 14,
    padding: 14,
  },

  avisoTexto: {
    color: '#9a3412',
    textAlign: 'center',
    fontSize: 12,
  },
})