import { moeda } from "../util/numeros.js";
const labels = {
  PUBLICANDO: "Publicação em andamento",
  PENDENTE: "Aguardando crédito",
  CONFIRMADA: "Crédito confirmado",
  FALHOU: "Crédito não aplicado",
  FALHA_PUBLICACAO: "Envio recusado",
  PUBLICACAO_INCERTA: "Envio sem confirmação",
};

export default function StatusTransferencia({
  transferencia: t,
  esperaLonga,
  retomar,
}) {
  const confirmado = t.status === "CONFIRMADA",
    falhou = ["FALHOU", "FALHA_PUBLICACAO"].includes(t.status);
  return (
    <section className="cartao acompanhamento" aria-live="polite">
      <div className="linha-titulo">
        <h2>Acompanhamento</h2>
        <span
          className={`badge ${confirmado ? "ok" : falhou ? "erro" : "pendente"}`}
        >
          {labels[t.status] || t.status}
        </span>
      </div>
      <p>
        {moeda(t.valor)} · conta {t.idOrigem} → conta {t.idDestino}
      </p>
      <ol className="etapas">
        <li className="concluida">
          <strong>Débito aplicado</strong>
          <span>Valor debitado da conta de origem.</span>
        </li>
        <li
          className={
            ["PENDENTE", "CONFIRMADA", "FALHOU"].includes(t.status)
              ? "concluida"
              : ""
          }
        >
          <strong>
            {t.destinoAgencia === t.idOrigem % 3
              ? "Processamento local"
              : "Envio para a agência de destino"}
          </strong>
          <span>
            {t.status === "PUBLICACAO_INCERTA"
              ? "Não foi possível confirmar se o envio foi aceito."
              : t.status === "FALHA_PUBLICACAO"
                ? "A mensagem não foi aceita para entrega."
                : "Pedido encaminhado para processamento."}
          </span>
        </li>
        <li className={confirmado ? "concluida" : ""}>
          <strong>
            {confirmado
              ? "Crédito confirmado"
              : falhou
                ? "Crédito não aplicado"
                : "Aguardando confirmação do crédito"}
          </strong>
          <span>
            {confirmado
              ? "O crédito foi aplicado e confirmado."
              : t.motivo || "O destino ainda não confirmou o processamento."}
          </span>
        </li>
      </ol>
      {falhou && (
        <p className="alerta">
          O débito permanece aplicado. Este sprint não realiza estorno
          distribuído automático.
        </p>
      )}
      {esperaLonga && (
        <div className="revisao">
          <p>
            A confirmação ainda não foi obtida. Isso não significa que o crédito
            falhou.
          </p>
          <button className="ghost" type="button" onClick={retomar}>
            Consultar novamente
          </button>
        </div>
      )}
      <details>
        <summary>Referência da transferência</summary>
        <code>{t.transferenciaId}</code>
      </details>
    </section>
  );
}
