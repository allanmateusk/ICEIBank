// VIEW - consulta de saldo
import { useState } from "react";
import { agenciaDaConta } from "../api/contas.js";
import { paraInteiroConta } from "../util/numeros.js";

export default function ConsultaSaldo({ aoConsultar, conta, agenciaAtual }) {
  const [id, setId] = useState(String(agenciaAtual));
  const [erro, setErro] = useState("");
  const dono = id === "" ? null : agenciaDaConta(id);

  return (
    <section className="cartao">
      <h3>Consultar saldo</h3>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const numero = paraInteiroConta(id);
          if (Number.isNaN(numero)) {
            setErro("Informe um número de conta válido.");
            return;
          }
          setErro("");
          aoConsultar(numero);
        }}
      >
        <label>
          Número da conta
          <input
            value={id}
            onChange={(e) => setId(e.target.value)}
            inputMode="numeric"
          />
        </label>
        <button>Consultar</button>
      </form>
      {erro && (
        <p className="alerta" role="alert">
          {erro}
        </p>
      )}

      {dono !== null && dono !== agenciaAtual && (
        <p className="dica alerta">
          A conta {id} pertence à Agência {dono}. Selecione a Agência {dono} lá
          em cima para operá-la.
        </p>
      )}

      {conta && (
        <p className="saldo">
          Conta {conta.id} ({conta.nomeAluno}):{" "}
          <strong>R$ {Number(conta.saldo).toFixed(2)}</strong>
        </p>
      )}
    </section>
  );
}
