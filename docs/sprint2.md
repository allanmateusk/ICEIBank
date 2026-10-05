# Sprint2 — respostas, desenho e observações

## Parte B — relógio vetorial (6.4)

**1. Três para dez agências.** Cada mensagem passaria de 3 para 10 contadores.
O espaço do timestamp e o custo de merge/comparação crescem linearmente com o
número de processos. Para dez agências isso é pequeno; em sistemas com muitos
participantes, tráfego e metadados podem exigir outra estratégia de representação.

**2.** `[3,1,0]` **e** `[3,2,0]`**.** O primeiro acontece antes: cada posição do primeiro
é menor ou igual à correspondente do segundo e ao menos uma é menor.

**3.** `[3,1,0]` **e** `[1,3,0]`**.** São concorrentes: o primeiro é maior na posição 0,
mas menor na 1; nenhum vetor domina o outro.

A implementação retorna snapshots por cópia e protege o relógio com lock.
Receber faz máximo posição a posição e depois incrementa a posição local.

## Parte C — publicação/consumo (7.5)

**1. O que acontece quando o destino volta?** No teste automatizado real, foi
criada uma conta 304 na Agência 1, essa agência foi encerrada e uma transferência
foi publicada com ela fora do ar. A API retornou `PENDENTE`; o RabbitMQ Manager
mostrou fila durável, zero consumidores e pelo menos uma mensagem pronta.
Após reiniciar a Agência 1, a mensagem foi entregue, mas a conta não existia mais.
O log registrou `CREDITO_REMOTO_FALHOU`; o resultado de falha voltou à origem e
o status ficou `FALHOU`. A conta não foi recriada para ocultar esse cenário.

**2. O que melhorou e o que ficou aberto?** O broker permite publicar enquanto
o destino está offline e preserva a mensagem. Isso melhora a entrega em relação
ao HTTP síncrono da sprint1, mas não persiste contas nem torna débito/publicação/
crédito uma transação atômica. O débito fica aplicado quando o crédito falha.
No teste backend: origem com 100, transferência normal de 25 → 75; transferência
de 10 para a agência offline → 65, mesmo após resultado de conta ausente.

**3. Consumidor sem JWT HTTP.** O consumidor não é uma rota HTTP e recebe dados
de uma conexão autenticada ao broker. JWT continua protegendo as APIs públicas.
Quem tem permissão de publicar no broker pode provocar créditos; portanto é
importante proteger URL/credenciais, usar AMQPS em nuvem e limitar permissões do
broker. O payload também é validado, mas validação não substitui autenticação e
autorização do publisher. As credenciais do compose são apenas de desenvolvimento
local e as portas ficam em loopback.

## Parte D — linha do tempo causal (8.3)

**1. Por que a comparação funciona?** Cada componente resume o conhecimento
causal do processo correspondente. No envio esse conhecimento vai anexado; no
recebimento o destino incorpora o máximo e registra seu próprio avanço. Em um
experimento contínuo, dominação componente a componente distingue precedência;
incomparabilidade prova concorrência. Lamport fornece um escalar e perde essa
distinção. Hora física e ordenação lexicográfica do vetor não substituem a regra.

**2. Par do próprio teste.** As criações de conta 300 na Agência 0 e 301 na
Agência 1 produziram `[1,0,0]` e `[0,1,0]`. Elas ocorreram antes de qualquer
transferência entre essas contas. Nenhuma recebeu conhecimento causal da outra;
o script as classificou como concorrentes. O débito e o crédito da transferência
remota têm precedência e não entram como par concorrente. O teste de causalidade
também verifica explicitamente essa exclusão.

**3. Escala O(n²).** Comparar todos os pares torna-se inviável com milhões de
eventos. É possível restringir análise por janelas/fluxos correlacionados, usar
índices e DAG de relações já conhecidas ou consultar apenas pares relevantes.
A amostra acadêmica é pequena; o script limita a quantidade exibida, mas esse
limite não reduz o custo da análise completa. Reinícios são detectados porque
contadores zerados não podem ser misturados como uma execução contínua.

## Funcionalidade adicional — confirmação de crédito

O destino publica `CONFIRMAR` em `agencia.<origem>.confirmar` com UUID da
transferência, resultado e vetor de envio. A origem consome e atualiza seu
acompanhamento. `GET /transferencias/{id}` exige JWT. O frontend apresenta o
resultado por polling; não usa timer para inventar sucesso.

Uma confirmação do broker prova aceite de publicação; não prova crédito.
Se a confirmação de negócio falha ao publicar depois de aplicar o crédito,
o cache do destino permite reenviar o resultado sem aplicar saldo novamente.
Ack ocorre após publicar o resultado. O cache é em memória e não sobrevive a
reinícios; não equivale a exactly-once ou persistência financeira.

## Concorrência e compatibilidade

Lock da agência cobre checagem/mutação do saldo e dos mapas. Nenhum lock de
thread permanece adquirido durante await de rede. Uma requisição repetida com
o mesmo UUID/payload reaproveita o resultado; outro payload com o UUID retorna
409. Rejeição definitiva de publicação e confirmação perdida têm estados
diferentes, sem estorno cego. Receber uma confirmação rápida não é sobrescrito
quando o await da publicação termina.

Particionamento, JWT, criação, consulta, depósito, saque e histórico continuam.
O histórico lê arquivos antigos e novos na ordem local de registro. A rota de
crédito remoto HTTP foi retirada. O cenário em memória continua explícito.

## Evidências e reprodução

Os testes Python incluem vetor, comparações, locks, transferências locais e
remotas, duplicatas, timeout versus rejeição, confirmação rápida, retentativa
de confirmação, JWT ausente/inválido/expirado e cenário offline/reinício real.
O teste do navegador usa três processos e RabbitMQ reais; suas capturas e os
relatórios da execução estão em `evidencias/sprint2/`.

Validação em 05/10/2026: 23 testes Python aprovados, E2E com os 15 cenários
registrados em `resultado-testes.json` aprovado, build Vite aprovado e
`npm audit` sem vulnerabilidades. Inclui reentrega com merge vetorial e resultado
confirmado preservado mesmo quando a confirmação de publicação se perde.

`transferencia-assincrona.png`, `resiliencia-fila.png` e
`linha-do-tempo-causal.png` são relatórios visuais de saídas reais capturadas,
incluindo data executada pelo PowerShell. Os demais PNGs são capturas da aplicação.
Para atender a uma exigência de screenshot de terminal nativo, reproduza o
procedimento do README das evidências e capture os terminais com `Get-Date`.

## Correções após a revisão

- O pedido cujo resultado HTTP não chegou é conservado em `sessionStorage`,
  por agência, com a mesma chave UUID. Navegação e recarga da aba preservam o
  pedido. Enquanto estiver sem resposta, a interface bloqueia alterações e
  permite recuperar o resultado reutilizando a chave.
- Após receber o resultado, a interface consulta o saldo atual. O saldo da
  resposta original da transferência é um registro daquele momento, não a
  posição atual da conta. Se a consulta falhar, o saldo anterior é retirado.
- No histórico, o débito de transferência pertence somente à origem e o crédito
  somente ao destino, inclusive para contas da mesma agência.

A deduplicação do backend continua em memória. Recuperar a chave na mesma aba
não garante deduplicação após reiniciar o processo da agência. Persistência e
transações distribuídas continuam fora do escopo desta sprint.

## Uso de IA na sprint2

Codex/OpenAI foi utilizado como apoio ao planejamento, protótipos, implementação,
revisão, correções e testes automatizados da sprint2. A declaração sobre Claude
em `RESPOSTAS.md` pertence à base da sprint1. O aluno deve estudar e explicar o
código entregue; esta declaração não afirma que a defesa oral já ocorreu.

## Pendências formais da entrega

Os relatórios gerados não substituem as capturas de terminal solicitadas na
seção 4.3. O procedimento para produzir essas capturas está em
`evidencias/sprint2/README.md`. O histórico tem commits separados por mudança,
concentrados em 05/10/2026; ele não demonstra desenvolvimento distribuído pelas
três semanas sugeridas no roteiro. As datas reais dos commits são preservadas.
