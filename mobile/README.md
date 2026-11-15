# ICEIBank móvel

Aplicativo Flutter que consulta as agências, mostra a líder, mantém o último saldo e registra operações em SQLite. Depósitos, saques e transferências são enviados por `/sincronizacao`; o cliente identifica cada operação com UUID persistido. O valor exibido como estimado inclui as pendências e não representa confirmação do servidor. A transferência remota só é confirmada quando o acompanhamento chega a `CONFIRMADA`.

## Funcionalidade adicional: diagnóstico das agências

Antes de enviar uma operação, o app grava o estado `INCERTA`. Se perder a
resposta, repete exatamente o mesmo pedido e UUID. Enquanto houver resultado
incerto para a conta, a tela suspende o saldo estimado para não contar uma
movimentação duas vezes. Na atualização do banco local da versão 1 para a 2,
pendências antigas também passam por essa reconciliação conservadora.

O painel de diagnóstico consulta as três agências em paralelo a cada cinco segundos e ao atualizar manualmente. Para cada uma, mostra disponibilidade e o tempo de resposta em milissegundos. Se as agências acessíveis informarem líderes diferentes, o painel exibe que a eleição está em andamento. A disponibilidade é uma observação momentânea e não garante que uma próxima operação bancária será concluída.

## Preparação

Instale o Flutter e o Android SDK, valide-os com `flutter doctor` e, dentro desta pasta, execute:

```powershell
flutter pub get
flutter run
```

O manifesto Android permite tráfego HTTP para o ambiente acadêmico local. Em produção, use HTTPS e remova a permissão de tráfego HTTP em texto claro.

Quando o dispositivo informa ausência de rede, novas operações permanecem
pendentes localmente e o saldo estimado reflete a fila. A existência de rede
não garante acesso à agência: depois que um envio é iniciado, uma resposta
perdida continua sendo tratada como incerta, com o mesmo UUID no reenvio e sem
projetar saldo até a reconciliação. Operações posteriores permanecem na fila e
só são enviadas depois da anterior.

O host padrão `10.0.2.2` é o computador visto pelo emulador Android. Em um dispositivo físico, informe o endereço acessível do computador e ajuste a exposição das portas de desenvolvimento 4000–4002. Na tela inicial, selecione **Criar usuário**, informe usuário e senha e confirme a senha; o Postgres precisa estar ativo. Depois entre com as credenciais criadas, crie uma conta bancária no aplicativo ou consulte uma conta existente online para armazenar seu saldo e versão. O JWT fica no armazenamento seguro do dispositivo; a senha não é armazenada. Ao expirar o JWT, faça login novamente para sincronizar a fila persistida. Dados e operações são separados pelo endereço do servidor e nome do usuário.

Se uma operação retornar conflito, ela e as operações seguintes da mesma conta ficam bloqueadas. A tela mostra a resposta do servidor; consulte o saldo, descarte a operação apenas depois de analisá-la e refaça-a se necessário. Problemas de rede e respostas 5xx preservam o mesmo UUID para nova tentativa. Com Postgres ativo, o estado e as chaves de deduplicação persistem após reinício. A mudança de sessão pode exigir revisão da fila; ausência de resposta não é confirmação.

## Teste de integração no Android

Com o backend isolado nas portas 4200–4202 e o telefone autorizado pelo ADB,
execute na raiz do repositório:

```powershell
./mobile/integration_test/executar-isolado.ps1 -DeviceId 'ID_DO_DISPOSITIVO'
```

Use `adb devices` para consultar o identificador. O script cria uma cópia local
com identificador e namespace separados e usa `--no-uninstall`. Essa versão do
script ainda precisa de validação em dispositivo separado; não executá-la no
aparelho principal até essa validação. O ensaio usa SQLite e backend reais,
mas simula a indisponibilidade de rede e reconstrói a interface no mesmo
processo. Detalhes e limitações estão em
[integration_test/README.md](integration_test/README.md).
