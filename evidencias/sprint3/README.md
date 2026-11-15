# Evidências da Sprint 3

As imagens desta pasta devem ser capturas reais da demonstração, com o comando
`Get-Date -Format o` e o resultado visíveis na tela. Não use imagens simuladas.

Na raiz do projeto, em uma janela PowerShell, execute cada comando e capture a
janela com a data e a saída exibidas:

```powershell
./scripts/evidencias-backend-sprint3.ps1 -Acao eleicao
# Salvar: eleicao-inicial.png
./scripts/evidencias-backend-sprint3.ps1 -Acao failover
# Salvar: failover.png
./scripts/evidencias-backend-sprint3.ps1 -Acao historico
# Salvar: historico-lideranca.png
./scripts/evidencias-backend-sprint3.ps1 -Acao conflito
# Salvar: conflito-sincronizacao.png
```

Os comandos utilizam o projeto Docker isolado `iceibank-evidencias`. O primeiro
inicia as dependências; os seguintes pressupõem que a primeira ação já ocorreu.
As senhas e os tokens das contas de teste não são mostrados.

Para as imagens do app, mantenha o celular espelhado e uma janela PowerShell
com `Get-Date -Format o` e seu resultado visíveis na mesma captura:

- `app-lider-atual.png`: painel com a líder atual.
- `app-failover.png`: painel com a nova líder após desligar a anterior.
- `app-offline.png`: operação pendente e aviso de indisponibilidade. Uma
  captura complementar `app-offline-saldo.png` deve mostrar o saldo estimado,
  que não ficou visível na imagem da fila.
- `app-sincronizacao.png`: fila e resultado após a reconexão.
- `funcionalidade-adicional.png`: diagnóstico das agências.

Consulte [docs/sprint3.md](../../docs/sprint3.md) para contexto e limitações.
