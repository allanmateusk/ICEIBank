# ICEIBank

Projeto individual de Allan Mateus: banco acadêmico dividido em três agências.
A sprint1 está preservada no commit `sprint1`. Esta sprint2 evolui essa base com
RabbitMQ, relógio vetorial, confirmação de crédito e frontend próprio.

## Stack e funcionamento

- Python 3.12+, FastAPI, Pydantic, PyJWT e aio-pika.
- React 18, Vite 8, interface escura com verde e navegação lateral.
- RabbitMQ: exchange topic `iceibank.eventos`, três filas duráveis,
  mensagens persistentes, publisher confirms e ack manual.
- Uma conta pertence à agência `numero % 3`. Um processo/worker por agência.
- As contas e a deduplicação ficam em memória: reiniciar perde esse estado.

Transferência remota: débito → publicação → consumo/crédito → evento de
confirmação → acompanhamento na agência de origem. HTTP 200 de publicação
não garante que o destino creditou. A interface só apresenta confirmação após
processamento local ou recebimento do resultado do destino.

## Rodar no Windows / PowerShell

Pré-requisitos: Python 3.12+, [uv](https://docs.astral.sh/uv/),
Node **20.19+ ou 22.12+**, npm e Docker Desktop para o broker local.

Na raiz, para subir RabbitMQ, Postgres, as três agências e o frontend:

```powershell
docker compose up -d --build --wait
```

Abra [o frontend](http://localhost:5173). Na tela inicial, **Criar usuário**
grava o login no Postgres. Depois de entrar, **Criar conta** cria a conta
bancária somente na memória da agência. Usuários de desenvolvimento `allan` e `lara` (senha
`iceibank`) são criados na primeira subida, se ainda não existirem.

Postgres local: `127.0.0.1:5434`, banco `iceibank`, usuário `iceibank`, senha
`iceibank-dev`. O volume `postgres-data` guarda somente usuários entre
reinícios. Contas, saldos, deduplicação e acompanhamento das transferências
continuam em memória, mesmo com Postgres ativo.

Para rodar as agências no host, com o banco e o broker no Docker:

```powershell
docker compose up -d --wait postgres rabbitmq
cd agencia
uv sync
cd ../frontend
npm ci
cd ..
```

Abra três terminais na raiz, executando um comando em cada:

```powershell
./scripts/iniciar-agencia.ps1 -Agencia 0
./scripts/iniciar-agencia.ps1 -Agencia 1
./scripts/iniciar-agencia.ps1 -Agencia 2
```

Em um quarto terminal:

```powershell
cd frontend
npm run dev
```

Crie ou consulte uma conta da agência selecionada. Exemplo: contas 300/303 → Agência 0; 301 → Agência 1;
302 → Agência 2. No início não existem contas.

O script usa AMQP local em `127.0.0.1:5678` se `RABBITMQ_URL` não estiver definida.
[RabbitMQ Manager local](http://localhost:15678): usuário `iceibank`, senha
`iceibank-dev`, somente para desenvolvimento. O compose liga as portas apenas
ao loopback e usa um volume próprio; não é configuração de produção.

### CloudAMQP

O broker local pode ser substituído pela sua instância pessoal. Em **cada**
terminal de agência, defina `RABBITMQ_URL` com a URL AMQPS da instância antes
de executar o script. Não cole a URL com senha em commits, prints ou logs.
Não é necessário alterar o código. `.env.example` contém apenas exemplos;
os scripts leem variáveis do processo, não carregam esse arquivo automaticamente.

### OFFSET

Use o mesmo offset nas três agências:

```powershell
./scripts/iniciar-agencia.ps1 -Agencia 0 -Offset 42
```

No frontend, antes de `npm run dev`: `$env:VITE_OFFSET='42'`.
As portas HTTP ficam em `4000 + OFFSET + agencia`.

## APIs

JWT em `Authorization: Bearer <token>` para contas, histórico e transferências.
`POST /auth/login` e `POST /auth/cadastro` são abertos. O escopo do projeto é autenticação, sem
uma regra de propriedade por titular/usuário.

| Endpoint | Finalidade |
|---|---|
| `POST /contas` | Criar com `id`, `nomeAluno`, `saldoInicial` |
| `GET /contas/{id}` | Consultar saldo |
| `POST /contas/{id}/depositar` ou `/sacar` | Movimentar com `valor` |
| `GET /contas/{id}/historico?limite=50` | Eventos da conta |
| `POST /transferencias` | `idOrigem`, `idDestino`, `valor` |
| `GET /transferencias/{transferenciaId}` | Status na agência da origem |

O frontend envia um `Idempotency-Key` UUID e mantém a chave ao repetir o mesmo
pedido. Pedidos sem resposta ficam guardados na mesma aba, inclusive após
navegação e recarga. A edição fica bloqueada até recuperar o resultado. Depois
da resposta, o frontend consulta o saldo atual. Reutilizar uma chave com outro
payload retorna 409. Valores financeiros devem
ser finitos, positivos nas movimentações e ter no máximo duas casas decimais.
A rota REST `creditar-remoto` foi removida: créditos remotos chegam pelo broker.

Estados: `PUBLICANDO`, `PENDENTE`, `CONFIRMADA`, `FALHOU`,
`FALHA_PUBLICACAO`, `PUBLICACAO_INCERTA`. A confirmação rápida não é sobrescrita
pela resposta de publicação. O polling tem limite; espera longa ou erro de
consulta não transforma a transferência em falha. Após reinício, status pode
retornar 404 porque o acompanhamento também está em memória.

## Testes e evidências

Com compose ativo:

```powershell
cd agencia
uv run python verificar_vetorial.py
uv run python -m unittest discover -s tests -v
cd ../frontend
npm run build
npm audit
npm run test:e2e
```

O E2E usa o Edge instalado no Windows (sem abrir janela). Em Linux, instale o
Chromium do Playwright com `npx playwright install chromium`. Os testes usam
vhosts exclusivos no broker local e processos temporários; limpam apenas esses
vhosts e o esquema exclusivo de usuários criado pelos testes de integração.
Esses testes usam o Postgres local em 5434 e verificam login persistente e
perda das contas após reinício. O E2E mantém também a cobertura sem banco.
Backend: 14500–14502; E2E: 14600–14602 e 15173. Deixe essas portas livres.
O teste não usa sua instância CloudAMQP nem altera contas da sessão manual.

`evidencias/sprint2/` contém capturas reais da interface e relatórios visuais
gerados com saídas reais de API/logs/linha do tempo. Os relatórios incluem
`Get-Date -Format o` executado pelo PowerShell. Não são screenshots de terminal
nativo; veja o README das evidências para reproduzir e capturar os terminais.

## Causalidade

```powershell
cd agencia
uv run python mesclar_logs.py --pasta data --limite-pares 50
```

Hora de parede organiza a exibição, não define causalidade. Vetores são
comparados componente a componente. Logs antigos de Lamport continuam legíveis,
mas são excluídos da comparação vetorial. Reinícios na mesma agência invalidam
inferências entre sessões: o script detecta isso e pede um experimento contínuo
em outra pasta. Use `PASTA_DADOS` para separar experimentos e preservar logs.

## Limites e documentação

Fila durável preserva mensagens, não contas. Se uma agência reiniciar, o crédito
pode chegar e falhar por conta ausente. O resultado volta à origem e o frontend
informa que o débito permanece aplicado. Não há estorno automático, outbox,
persistência financeira ou promessa de exactly-once; esses temas ficam para as
próximas etapas. Deduplicação vale durante a vida do processo.

[RESPOSTAS.md](RESPOSTAS.md) preserva o material da sprint1 e aponta as respostas
e observações da sprint2 em [docs/sprint2.md](docs/sprint2.md).
Configurações JWT/senhas de desenvolvimento da base
continuam disponíveis por variáveis de ambiente; definir segredos pessoais fora
do Git ao usar outro ambiente.
