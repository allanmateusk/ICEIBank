# ICEIBank móvel

Aplicativo Flutter que consulta as agências, mostra a líder, mantém o último saldo e registra operações em SQLite. Depósitos, saques e transferências são enviados por `/sincronizacao`; o cliente identifica cada operação com UUID persistido. O valor exibido como estimado inclui as pendências e não representa confirmação do servidor. A transferência remota só é confirmada quando o acompanhamento chega a `CONFIRMADA`.

## Funcionalidade adicional: diagnóstico das agências

O painel de diagnóstico consulta as três agências em paralelo a cada cinco segundos e ao atualizar manualmente. Para cada uma, mostra disponibilidade e o tempo de resposta em milissegundos. Se as agências acessíveis informarem líderes diferentes, o painel exibe que a eleição está em andamento. A disponibilidade é uma observação momentânea e não garante que uma próxima operação bancária será concluída.

## Preparação

Instale o Flutter e o Android SDK, valide-os com `flutter doctor` e, dentro desta pasta, execute:

```powershell
flutter pub get
flutter run
```

O manifesto Android permite tráfego HTTP para o ambiente acadêmico local. Em produção, use HTTPS e remova a permissão de tráfego HTTP em texto claro.

O host padrão `10.0.2.2` é o computador visto pelo emulador Android. Em um dispositivo físico, informe o endereço acessível do computador e ajuste a exposição das portas de desenvolvimento 4000–4002. Faça login e crie uma conta no aplicativo ou consulte uma conta existente online para armazenar seu saldo e versão. O JWT fica no armazenamento seguro do dispositivo; a senha não é armazenada. Ao expirar o JWT, faça login novamente para sincronizar a fila persistida. Dados e operações são separados pelo endereço do servidor e nome do usuário.

Se uma operação retornar conflito, ela e as operações seguintes da mesma conta ficam bloqueadas. A tela mostra a resposta do servidor; consulte o saldo, descarte a operação apenas depois de analisá-la e refaça-a se necessário. Problemas de rede e respostas 5xx preservam o mesmo UUID para nova tentativa. Se o servidor reiniciar, seu estado e suas chaves de deduplicação em memória são perdidos; o cliente preserva a operação para reconciliação e não considera a ausência de resposta como confirmação.
