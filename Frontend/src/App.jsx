import { useEffect, useMemo, useState } from 'react'
import { buscarLeituras, buscarSaude } from './services/api'
import './App.css'

function formatarData(data) {
  if (!data) return '--'

  return new Date(data).toLocaleString('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'medium',
  })
}

function formatarRisco(risco) {
  if (risco === null || risco === undefined) return '--'
  return `${Math.round(risco * 100)}%`
}

function classeFaixa(faixa) {
  return faixa || 'indisponivel'
}

function App() {
  const [leituras, setLeituras] = useState([])
  const [saude, setSaude] = useState(null)
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState('')

  const ultimaLeitura = useMemo(
    () => leituras[0] || null,
    [leituras]
  )

  async function atualizarDashboard() {
    try {
      const [statusApi, historico] = await Promise.all([
        buscarSaude(),
        buscarLeituras(20),
      ])

      setSaude(statusApi)
      setLeituras(historico)
      setErro('')
    } catch (error) {
      setErro(error.message)
    } finally {
      setCarregando(false)
    }
  }

  useEffect(() => {
    atualizarDashboard()

    const intervalo = setInterval(
      atualizarDashboard,
      5000
    )

    return () => clearInterval(intervalo)
  }, [])

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <span className="marca">CardioIA</span>
          <p className="subtitulo">
            Monitoramento inteligente de risco cardíaco
          </p>
        </div>

        <div
          className={`status-api ${
            saude?.status === 'ok'
              ? 'online'
              : 'offline'
          }`}
        >
          <span className="status-dot" />
          {saude?.status === 'ok'
            ? 'Sistema online'
            : 'Sistema offline'}
        </div>
      </header>

      <main className="conteudo">
        <section className="cabecalho-dashboard">
          <div>
            <p className="eyebrow">
              PAINEL DE MONITORAMENTO
            </p>

            <h1>Visão geral do paciente</h1>

            <p className="descricao">
              Dados atualizados automaticamente a cada
              5 segundos.
            </p>
          </div>

          <button
            className="botao-atualizar"
            onClick={atualizarDashboard}
          >
            Atualizar agora
          </button>
        </section>

        {erro && (
          <div className="alerta-erro">
            <strong>Backend indisponível.</strong>
            <span>{erro}</span>
          </div>
        )}

        <section className="cards">
          <article className="card card-risco">
            <p className="card-titulo">
              Risco cardíaco
            </p>

            <strong
              className={`risco-valor ${classeFaixa(
                ultimaLeitura?.faixa
              )}`}
            >
              {formatarRisco(
                ultimaLeitura?.risco
              )}
            </strong>

            <span
              className={`badge-risco ${classeFaixa(
                ultimaLeitura?.faixa
              )}`}
            >
              {ultimaLeitura?.faixa
                ? ultimaLeitura.faixa.toUpperCase()
                : 'SEM DADOS'}
            </span>
          </article>

          <article className="card">
            <p className="card-titulo">
              Frequência cardíaca
            </p>

            <div className="metrica">
              <strong>
                {ultimaLeitura?.bpm ?? '--'}
              </strong>
              <span>bpm</span>
            </div>

            <p className="card-legenda">
              Última leitura recebida
            </p>
          </article>

          <article className="card">
            <p className="card-titulo">
              Saturação de oxigênio
            </p>

            <div className="metrica">
              <strong>
                {ultimaLeitura?.spo2 ?? '--'}
              </strong>
              <span>%</span>
            </div>

            <p className="card-legenda">
              SpO₂
            </p>
          </article>

          <article className="card">
            <p className="card-titulo">
              Temperatura
            </p>

            <div className="metrica">
              <strong>
                {ultimaLeitura?.temperatura ??
                  '--'}
              </strong>
              <span>°C</span>
            </div>

            <p className="card-legenda">
              Temperatura corporal
            </p>
          </article>
        </section>

        <section className="grid-secundario">
          <article className="painel">
            <div className="painel-cabecalho">
              <div>
                <p className="eyebrow">
                  RECOMENDAÇÕES
                </p>
                <h2>Protocolos acionados</h2>
              </div>

              <span className="contador">
                {ultimaLeitura
                  ?.protocolos_acionados
                  ?.length ?? 0}
              </span>
            </div>

            {ultimaLeitura?.recomendacoes
              ?.length > 0 ? (
              <ul className="lista-protocolos">
                {ultimaLeitura.recomendacoes.map(
                  (recomendacao, index) => (
                    <li key={index}>
                      <span className="icone-protocolo">
                        !
                      </span>
                      {recomendacao}
                    </li>
                  )
                )}
              </ul>
            ) : (
              <div className="estado-vazio">
                Nenhum protocolo acionado no
                momento.
              </div>
            )}
          </article>

          <article className="painel">
            <p className="eyebrow">
              DISPOSITIVO
            </p>

            <h2>Última atualização</h2>

            <div className="detalhes">
              <div>
                <span>Dispositivo</span>
                <strong>
                  {ultimaLeitura?.device_id ??
                    '--'}
                </strong>
              </div>

              <div>
                <span>Recebido em</span>
                <strong>
                  {formatarData(
                    ultimaLeitura?.recebido_em
                  )}
                </strong>
              </div>

              <div>
                <span>Modelo preditivo</span>
                <strong>
                  {saude?.modelo_carregado
                    ? 'Disponível'
                    : 'Indisponível'}
                </strong>
              </div>

              <div>
                <span>Assistente</span>
                <strong>
                  {saude?.watson_configurado
                    ? 'Disponível'
                    : 'Não configurado'}
                </strong>
              </div>
            </div>
          </article>
        </section>

        <section className="painel historico">
          <div className="painel-cabecalho">
            <div>
              <p className="eyebrow">
                HISTÓRICO
              </p>
              <h2>Leituras recentes</h2>
            </div>

            <span>
              {leituras.length} registro(s)
            </span>
          </div>

          {carregando ? (
            <div className="estado-vazio">
              Carregando dados...
            </div>
          ) : leituras.length === 0 ? (
            <div className="estado-vazio">
              Ainda não há leituras recebidas.
            </div>
          ) : (
            <div className="tabela-container">
              <table>
                <thead>
                  <tr>
                    <th>Horário</th>
                    <th>BPM</th>
                    <th>SpO₂</th>
                    <th>Temperatura</th>
                    <th>Risco</th>
                    <th>Faixa</th>
                  </tr>
                </thead>

                <tbody>
                  {leituras.map((leitura) => (
                    <tr key={leitura.id}>
                      <td>
                        {formatarData(
                          leitura.recebido_em
                        )}
                      </td>
                      <td>{leitura.bpm}</td>
                      <td>
                        {leitura.spo2 ?? '--'}
                      </td>
                      <td>
                        {leitura.temperatura} °C
                      </td>
                      <td>
                        {formatarRisco(
                          leitura.risco
                        )}
                      </td>
                      <td>
                        <span
                          className={`badge-tabela ${classeFaixa(
                            leitura.faixa
                          )}`}
                        >
                          {leitura.faixa}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <footer className="aviso">
          {ultimaLeitura?.aviso ||
            'Protótipo acadêmico com dados sintéticos; não substitui avaliação médica.'}
        </footer>
      </main>
    </div>
  )
}

export default App