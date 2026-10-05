// VIEW - tela de login e cadastro de usuário
import { useState } from "react";

export default function Login({ aoEntrar, aoCadastrar, ocupado }) {
  const [modo, setModo] = useState("entrar");
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [confirma, setConfirma] = useState("");
  const [erroLocal, setErroLocal] = useState("");

  function enviar(e) {
    e.preventDefault();
    setErroLocal("");
    if (modo === "criar") {
      if (senha !== confirma) {
        setErroLocal("As senhas não conferem.");
        return;
      }
      aoCadastrar(usuario.trim(), senha);
      return;
    }
    aoEntrar(usuario.trim(), senha);
  }

  function alternar() {
    setModo((atual) => (atual === "entrar" ? "criar" : "entrar"));
    setErroLocal("");
    setSenha("");
    setConfirma("");
  }

  const criando = modo === "criar";

  return (
    <form className="cartao login" onSubmit={enviar}>
      <h2>{criando ? "Criar usuário" : "Entrar"}</h2>
      <label>
        Usuário
        <input
          value={usuario}
          onChange={(e) => setUsuario(e.target.value)}
          autoFocus
          required
          minLength={criando ? 3 : 1}
          maxLength={40}
          pattern={criando ? "[A-Za-z0-9._-]+" : undefined}
          autoComplete="username"
        />
      </label>
      <label>
        Senha
        <input
          type="password"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          required
          minLength={criando ? 6 : 1}
          autoComplete={criando ? "new-password" : "current-password"}
        />
      </label>
      {criando && (
        <label>
          Confirmar senha
          <input
            type="password"
            value={confirma}
            onChange={(e) => setConfirma(e.target.value)}
            required
            minLength={6}
            autoComplete="new-password"
          />
        </label>
      )}
      {erroLocal && <p className="dica alerta">{erroLocal}</p>}
      <button disabled={ocupado}>
        {ocupado ? "Aguarde…" : criando ? "Criar usuário" : "Entrar"}
      </button>
      <button className="ghost" type="button" onClick={alternar} disabled={ocupado}>
        {criando ? "Já tenho usuário" : "Criar usuário"}
      </button>
    </form>
  );
}
