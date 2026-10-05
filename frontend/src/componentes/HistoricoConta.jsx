import { useEffect, useState } from "react";
import { AGENCIAS } from "../api/cliente.js";
import { consultarHistorico } from "../api/contas.js";
import { moeda } from "../util/numeros.js";
const nomes = {
  CRIAR_CONTA: "Conta criada",
  DEPOSITO: "Depósito",
  SAQUE: "Saque",
  TRANSFERENCIA_DEBITO: "Transferência enviada",
  TRANSFERENCIA_CREDITO: "Transferência recebida",
  TRANSFERENCIA_CREDITO_REMOTO: "Crédito recebido",
  CONFIRMACAO_RECEBIDA: "Resultado da transferência",
  CREDITO_REMOTO_FALHOU: "Crédito não aplicado",
  TRANSFERENCIA_ENVIADA: "Pedido encaminhado",
};

export default function HistoricoConta({
  conta,
  agencia,
  revisao,
  onErro,
  compacto = false,
}) {
  const [eventos, setEventos] = useState([]),
    [carregando, setCarregando] = useState(true);
  const [falhou, setFalhou] = useState(false);
  useEffect(() => {
    const controle = new AbortController();
    let vivo = true;
    setCarregando(true);
    setFalhou(false);
    setEventos([]);
    consultarHistorico(conta.id, {
      signal: controle.signal,
      base: AGENCIAS.find((a) => a.id === agencia).url,
    })
      .then((r) => {
        if (vivo) setEventos(r.eventos.reverse());
      })
      .catch((e) => {
        if (vivo) {
          setFalhou(true);
          onErro(e);
        }
      })
      .finally(() => {
        if (vivo) setCarregando(false);
      });
    return () => {
      vivo = false;
      controle.abort();
    };
  }, [conta.id, agencia, revisao, onErro]);
  const visiveis = eventos
    .filter((e) => nomes[e.tipo])
    .slice(0, compacto ? 5 : 50);
  return (
    <section className="cartao historico">
      <h2>{compacto ? "Últimas movimentações" : "Movimentações da conta"}</h2>
      {carregando ? (
        <p className="muted">Carregando movimentações…</p>
      ) : falhou ? (
        <p className="muted">Não foi possível carregar o histórico.</p>
      ) : !visiveis.length ? (
        <p className="muted">Nenhuma movimentação registrada.</p>
      ) : (
        visiveis.map((e, i) => {
          const d = e.detalhes,
            debito = ["SAQUE", "TRANSFERENCIA_DEBITO"].includes(e.tipo);
          const alteraSaldo = [
            "DEPOSITO",
            "SAQUE",
            "TRANSFERENCIA_DEBITO",
            "TRANSFERENCIA_CREDITO",
            "TRANSFERENCIA_CREDITO_REMOTO",
          ].includes(e.tipo);
          return (
            <div
              className="movimentacao"
              key={`${e.sessaoProcesso || "legado"}-${e.sequencia || i}`}
            >
              <div>
                <strong>{nomes[e.tipo]}</strong>
                <div className="muted">
                  {new Date(e.horaParede).toLocaleString("pt-BR")}
                </div>
                {d.resultado && (
                  <span
                    className={`badge ${d.resultado === "CREDITO_APLICADO" ? "ok" : "erro"}`}
                  >
                    {d.resultado === "CREDITO_APLICADO"
                      ? "Crédito confirmado"
                      : "Crédito não aplicado"}
                  </span>
                )}
              </div>
              <div className="valor-movimento">
                {alteraSaldo
                  ? `${debito ? "−" : "+"} ${moeda(d.valor)}`
                  : e.tipo === "CRIAR_CONTA"
                    ? moeda(d.saldoInicial || 0)
                    : "—"}
              </div>
            </div>
          );
        })
      )}
    </section>
  );
}
