// MODEL - autenticação
import { requisitar, setToken, urlBase } from "./cliente.js";

// Faz login na agência selecionada (todas validam o mesmo segredo) e guarda o
// token devolvido. Depois disso, requisitar() reenvia esse token sozinho.
export async function cadastrar(usuario, senha) {
  return requisitar("/auth/cadastro", {
    metodo: "POST",
    corpo: { usuario, senha },
    base: urlBase(),
  });
}

export async function login(usuario, senha) {
  const dados = await requisitar("/auth/login", {
    metodo: "POST",
    corpo: { usuario, senha },
    base: urlBase(),
  });
  setToken(dados.access_token);
  return dados;
}
