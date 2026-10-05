import { useCallback, useEffect, useRef, useState } from "react";
import {
  AGENCIAS,
  getAgenciaId,
  setAgenciaId,
  getToken,
  setToken,
  SessaoExpirada,
} from "./api/cliente.js";
import { login } from "./api/auth.js";
import * as contasApi from "./api/contas.js";
import * as transferenciasApi from "./api/transferencias.js";
import Login from "./componentes/Login.jsx";
import Mensagem from "./componentes/Mensagem.jsx";
import ConsultaSaldo from "./componentes/ConsultaSaldo.jsx";
import FormCriarConta from "./componentes/FormCriarConta.jsx";
import FormValor from "./componentes/FormValor.jsx";
import FormTransferencia from "./componentes/FormTransferencia.jsx";
import HistoricoConta from "./componentes/HistoricoConta.jsx";
import StatusTransferencia from "./componentes/StatusTransferencia.jsx";
import { moeda } from "./util/numeros.js";

const observavel = (status) =>
  ["PUBLICANDO", "PENDENTE", "PUBLICACAO_INCERTA"].includes(status);

export default function App() {
  const [autenticado, setAutenticado] = useState(!!getToken());
  const [agencia, setAgencia] = useState(getAgenciaId());
  const [tela, setTela] = useState("resumo");
  const [conta, setConta] = useState(null);
  const [msg, setMsg] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [transferencia, setTransferencia] = useState(null);
  const [revisao, setRevisao] = useState(0);
  const [retomar, setRetomar] = useState(0);
  const [esperaLonga, setEsperaLonga] = useState(false);
  const contexto = useRef(0);

  const tratarErro = useCallback((e) => {
    if (e.name === "AbortError") return;
    if (e instanceof SessaoExpirada) {
      contexto.current++;
      setAutenticado(false);
      setConta(null);
      setTransferencia(null);
      setOcupado(false);
    }
    setMsg({ tipo: "erro", texto: e.message });
  }, []);

  async function executar(fn, sucesso) {
    const atual = contexto.current;
    setOcupado(true);
    setMsg(null);
    try {
      const resultado = await fn();
      if (atual !== contexto.current) return;
      if (sucesso)
        setMsg({
          tipo: "ok",
          texto: typeof sucesso === "function" ? sucesso(resultado) : sucesso,
        });
      setRevisao((r) => r + 1);
      return resultado;
    } catch (e) {
      if (atual !== contexto.current) return;
      if (e.dados?.transferenciaId) {
        setTransferencia(e.dados);
        setConta((c) => (c?.id === e.dados.idOrigem ? null : c));
      }
      tratarErro(e);
      if (e.dados?.transferenciaId)
        setMsg({
          tipo: "erro",
          texto: e.message,
          transferenciaId: e.dados.transferenciaId,
        });
    } finally {
      if (atual === contexto.current) setOcupado(false);
    }
  }

  function limparContexto() {
    contexto.current++;
    setConta(null);
    setTransferencia(null);
    setMsg(null);
    setEsperaLonga(false);
    setOcupado(false);
    setTela("resumo");
  }

  function trocarAgencia(id) {
    limparContexto();
    setAgencia(id);
    setAgenciaId(id);
  }
  function sair() {
    limparContexto();
    setToken(null);
    setAutenticado(false);
  }
  async function aoEntrar(usuario, senha) {
    if (await executar(() => login(usuario, senha))) setAutenticado(true);
  }
  async function aoCriar(id, nome, saldo) {
    const c = await executar(
      () => contasApi.criarConta(id, nome, saldo),
      "Conta criada com sucesso.",
    );
    if (c) {
      setConta(c);
      setTela("resumo");
    }
  }
  async function aoConsultar(id) {
    const c = await executar(() => contasApi.consultarSaldo(id));
    if (c) setConta(c);
  }
  async function movimentar(fn, id, valor) {
    const c = await executar(() => fn(id, valor), "Movimentação concluída.");
    if (c) {
      setConta(c);
      setTela("resumo");
    }
  }
  async function aoTransferir(origem, destino, valor, chave) {
    const agenciaPedido = agencia;
    setTransferencia(null);
    const r = await executar(async () => {
      let operacao;
      try {
        operacao = await transferenciasApi.transferir(
          origem,
          destino,
          valor,
          chave,
        );
      } catch (e) {
        if (e.dados?.transferenciaId || [400, 404, 422, 503].includes(e.status))
          transferenciasApi.limparPedidoPendente(agenciaPedido, chave);
        throw e;
      }
      transferenciasApi.limparPedidoPendente(agenciaPedido, chave);
      try {
        const atual = await contasApi.consultarSaldo(origem);
        return { operacao, atual };
      } catch (erroSaldo) {
        return { operacao, erroSaldo };
      }
    });
    if (r) {
      setTransferencia(r.operacao);
      setEsperaLonga(false);
      setConta((c) => (c?.id === origem ? r.atual || null : c));
      if (r.erroSaldo) tratarErro(r.erroSaldo);
    }
    return r?.operacao;
  }

  useEffect(() => {
    if (!autenticado || !transferencia || !observavel(transferencia.status))
      return;
    const controle = new AbortController();
    const atual = contexto.current;
    const base = AGENCIAS.find((a) => a.id === agencia).url;
    let vivo = true,
      timer,
      tentativas = 0;
    setEsperaLonga(false);
    async function consultar() {
      try {
        const r = await transferenciasApi.consultarTransferencia(
          transferencia.transferenciaId,
          { base, signal: controle.signal },
        );
        if (!vivo || atual !== contexto.current) return;
        setTransferencia(r);
        if (!observavel(r.status)) {
          setMsg((m) => (m?.transferenciaId === r.transferenciaId ? null : m));
          setRevisao((v) => v + 1);
          return;
        }
        if (++tentativas >= 30) {
          setEsperaLonga(true);
          return;
        }
        timer = setTimeout(consultar, 2000);
      } catch (e) {
        if (!vivo || atual !== contexto.current) return;
        tratarErro(e);
        setEsperaLonga(true);
      }
    }
    timer = setTimeout(consultar, 500);
    return () => {
      vivo = false;
      clearTimeout(timer);
      controle.abort();
    };
  }, [
    transferencia?.transferenciaId,
    transferencia?.status,
    agencia,
    autenticado,
    retomar,
    tratarErro,
  ]);

  const titulos = {
    resumo: "Meu dinheiro",
    transferir: "Faça uma transferência",
    historico: "Histórico da conta",
    criar: "Abra uma conta",
    consultar: "Consultar conta",
    depositar: "Depositar",
    sacar: "Sacar",
  };
  return (
    <div className="app">
      <aside className="sidebar">
        <a
          className="marca"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setTela("resumo");
          }}
        >
          ICEI<span>Bank</span>
        </a>
        <div className="marca-sub">Seu banco distribuído.</div>
        {autenticado && (
          <nav aria-label="Navegação principal">
            {[
              ["resumo", "Resumo"],
              ["transferir", "Transferir"],
              ["historico", "Histórico"],
            ].map(([id, texto]) => (
              <button
                key={id}
                type="button"
                className="nav-item"
                aria-current={tela === id ? "page" : undefined}
                onClick={() => setTela(id)}
              >
                {texto}
              </button>
            ))}
            <button
              type="button"
              className="nav-item nav-secundario"
              onClick={() => setTela("criar")}
            >
              Criar conta
            </button>
          </nav>
        )}
        <div className="sidebar-rodape">ICEIBank · Sprint 2</div>
      </aside>
      <div className="conteudo">
        <header className="topbar">
          <span className="muted">
            {conta ? `Olá, ${conta.nomeAluno}` : "Bem-vindo ao ICEIBank"}
          </span>
          <div className="ferramentas">
            <label htmlFor="agencia">Agência atual</label>
            <select
              id="agencia"
              value={agencia}
              disabled={ocupado}
              onChange={(e) => trocarAgencia(Number(e.target.value))}
            >
              {AGENCIAS.map((a) => (
                <option key={a.id} value={a.id}>
                  Agência {a.id}
                </option>
              ))}
            </select>
            {autenticado && (
              <button type="button" className="ghost" onClick={sair}>
                Sair
              </button>
            )}
          </div>
        </header>
        <main>
          <Mensagem msg={msg} />
          {!autenticado ? (
            <div className="login-area">
              <div className="eyebrow">Bem-vindo ao seu banco</div>
              <h1>
                Seu dinheiro.
                <br />
                Do seu jeito.
              </h1>
              <p className="muted">
                Entre para consultar e movimentar suas contas.
              </p>
              <Login aoEntrar={aoEntrar} ocupado={ocupado} />
            </div>
          ) : (
            <>
              <div className="page-header">
                <div className="eyebrow">
                  {conta
                    ? `Conta ${conta.id} · Agência ${agencia}`
                    : `Agência ${agencia}`}
                </div>
                <h1>{titulos[tela]}</h1>
              </div>
              <fieldset
                className="operacoes"
                disabled={ocupado}
                key={`${agencia}-${autenticado}`}
              >
                {tela === "resumo" && (
                  <>
                    {conta ? (
                      <section className="saldo-card">
                        <span>Saldo disponível</span>
                        <div className="saldo-valor">{moeda(conta.saldo)}</div>
                        <p>Saldo da conta consultada</p>
                        <div className="acoes">
                          {[
                            ["transferir", "Transferir ↗"],
                            ["depositar", "Depositar"],
                            ["sacar", "Sacar"],
                          ].map(([id, texto]) => (
                            <button
                              type="button"
                              key={id}
                              onClick={() => setTela(id)}
                            >
                              {texto}
                            </button>
                          ))}
                        </div>
                      </section>
                    ) : (
                      <section className="cartao vazio">
                        <h2>Vamos começar?</h2>
                        <p>
                          Consulte uma conta da Agência {agencia} ou crie sua
                          primeira conta.
                        </p>
                        <div className="acoes">
                          <button
                            type="button"
                            onClick={() => setTela("consultar")}
                          >
                            Consultar conta
                          </button>
                          <button
                            className="ghost"
                            type="button"
                            onClick={() => setTela("criar")}
                          >
                            Criar conta
                          </button>
                        </div>
                      </section>
                    )}
                    {conta && (
                      <HistoricoConta
                        conta={conta}
                        agencia={agencia}
                        revisao={revisao}
                        onErro={tratarErro}
                        compacto
                      />
                    )}
                    <div className="acoes">
                      <button
                        className="ghost"
                        type="button"
                        onClick={() => setTela("consultar")}
                      >
                        Consultar outra conta
                      </button>
                      <button
                        className="ghost"
                        type="button"
                        onClick={() => setTela("criar")}
                      >
                        Criar conta
                      </button>
                    </div>
                  </>
                )}
                {tela === "consultar" && (
                  <ConsultaSaldo
                    aoConsultar={aoConsultar}
                    conta={conta}
                    agenciaAtual={agencia}
                  />
                )}
                {tela === "criar" && (
                  <FormCriarConta aoCriar={aoCriar} agenciaAtual={agencia} />
                )}
                {tela === "depositar" && (
                  <FormValor
                    titulo="Depósito"
                    rotuloBotao="Depositar"
                    contaInicial={conta?.id ?? agencia}
                    aoEnviar={(id, valor) =>
                      movimentar(contasApi.depositar, id, valor)
                    }
                  />
                )}
                {tela === "sacar" && (
                  <FormValor
                    titulo="Saque"
                    rotuloBotao="Sacar"
                    contaInicial={conta?.id ?? agencia}
                    aoEnviar={(id, valor) =>
                      movimentar(contasApi.sacar, id, valor)
                    }
                  />
                )}
                {tela === "transferir" && (
                  <FormTransferencia
                    aoTransferir={aoTransferir}
                    agenciaAtual={agencia}
                    conta={conta}
                  />
                )}
                {tela === "historico" &&
                  (conta ? (
                    <HistoricoConta
                      conta={conta}
                      agencia={agencia}
                      revisao={revisao}
                      onErro={tratarErro}
                    />
                  ) : (
                    <ConsultaSaldo
                      aoConsultar={aoConsultar}
                      agenciaAtual={agencia}
                    />
                  ))}
              </fieldset>
              {tela === "transferir" && transferencia && (
                <StatusTransferencia
                  transferencia={transferencia}
                  esperaLonga={esperaLonga}
                  retomar={() => setRetomar((v) => v + 1)}
                />
              )}
            </>
          )}
        </main>
        <footer>
          Projeto acadêmico · contas em memória · reiniciar a agência perde suas
          contas
        </footer>
      </div>
    </div>
  );
}
