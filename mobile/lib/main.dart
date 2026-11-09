import 'dart:async';
import 'dart:convert';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';
import 'api.dart';
import 'storage.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final storage = Storage();
  await storage.init();
  runApp(MaterialApp(debugShowCheckedModeBanner: false, title: 'ICEIBank', theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true), home: Banking(storage: storage)));
}

class Banking extends StatefulWidget {
  const Banking({super.key, required this.storage});
  final Storage storage;
  @override
  State<Banking> createState() => _BankingState();
}

class _BankingState extends State<Banking> with WidgetsBindingObserver {
  final host = TextEditingController(text: '10.0.2.2');
  final user = TextEditingController();
  final password = TextEditingController();
  final account = TextEditingController();
  final amount = TextEditingController();
  final destination = TextEditingController();
  late Api api;
  final secure = const FlutterSecureStorage();
  String? usuario;
  Map<String, dynamic>? conta;
  List<Map<String, Object?>> fila = [];
  List<Map<String, Object?>> transferencias = [];
  String status = 'Entre para começar.';
  String lider = 'Buscando...';
  List<String> diagnostico = List.filled(3, 'Aguardando consulta');
  bool verificandoLider = false;
  bool sincronizando = false;
  Timer? timer;
  StreamSubscription<List<ConnectivityResult>>? connectivity;
  Storage get store => widget.storage;
  int? get id => int.tryParse(account.text);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    api = Api(host.text);
    restaurarSessao();
    timer = Timer.periodic(const Duration(seconds: 5), (_) { if (usuario != null) { verificarLider(); sincronizar(); acompanharTransferencias(); } });
    connectivity = Connectivity().onConnectivityChanged.listen((_) { if (usuario != null) sincronizar(); });
  }
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) { if (state == AppLifecycleState.resumed && usuario != null) sincronizar(); }
  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    timer?.cancel(); connectivity?.cancel();
    for (final controller in [host, user, password, account, amount, destination]) { controller.dispose(); }
    super.dispose();
  }
  void atualizar(VoidCallback f) { if (mounted) setState(f); }
  String erro(Object e) => e is ApiError ? (e.data is Map ? '${(e.data as Map)['detail'] ?? e.data}' : '${e.data}') : 'Rede indisponível ou tempo esgotado.';

  Future<void> restaurarSessao() async {
    final nome = await secure.read(key: 'usuario');
    final token = await secure.read(key: 'jwt');
    final servidor = await secure.read(key: 'host');
    if (nome == null || token == null || servidor == null || !mounted) return;
    host.text = servidor; user.text = nome; api = Api(servidor); api.token = token;
    atualizar(() { usuario = nome; status = 'Sessão restaurada; dados offline disponíveis.'; });
    await atualizarFila();
    await acompanharTransferencias();
    await sincronizar();
  }

  Future<void> login() async {
    try {
      api = Api(host.text.trim());
      Map<String, dynamic>? result;
      Object? lastError;
      for (var agencia = 0; agencia < 3; agencia++) {
        try {
          result = await api.request(agencia, '/auth/login', body: {'usuario': user.text.trim(), 'senha': password.text});
          break;
        } catch (e) { lastError = e; }
      }
      if (result == null) throw lastError ?? Exception('Nenhuma agência disponível');
      api.token = result['access_token'] as String;
      await secure.write(key: 'usuario', value: user.text.trim());
      await secure.write(key: 'host', value: host.text.trim());
      await secure.write(key: 'jwt', value: api.token);
      atualizar(() { usuario = user.text.trim(); password.clear(); status = 'Sessão iniciada.'; });
      await verificarLider();
      await atualizarFila();
      await sincronizar();
    } catch (e) { atualizar(() => status = erro(e)); }
  }
  Future<void> sair() async {
    await secure.deleteAll();
    atualizar(() { usuario = null; api.token = null; conta = null; fila = []; transferencias = []; status = 'Sessão encerrada.'; });
  }
  Future<void> atualizarFila() async {
    final u = usuario; if (u == null) return;
    final rows = await store.pendentes(u);
    atualizar(() => fila = rows);
  }
  Future<void> acompanharTransferencias() async {
    final u = usuario; if (u == null) return;
    final rows = await store.transferencias(u);
    for (final row in rows) {
      final dados = Map<String, dynamic>.from(jsonDecode(row['dados'] as String));
      if (dados['status'] == 'CONFIRMADA' || dados['status'] == 'FALHOU') continue;
      try {
        final atual = await api.request(row['agencia'] as int, '/transferencias/${row['id']}');
        await store.salvarTransferencia(u, row['agencia'] as int, atual);
      } catch (_) { /* Manter último estado, inclusive quando a agência está indisponível. */ }
    }
    final atualizadas = await store.transferencias(u);
    atualizar(() => transferencias = atualizadas);
  }
  Future<void> verificarLider() async {
    if (verificandoLider) return;
    verificandoLider = true;
    try {
      final respostas = await Future.wait(List.generate(3, (i) async {
        final relogio = Stopwatch()..start();
        try {
          final data = await api.request(i, '/bully/lider');
          relogio.stop();
          return {'descricao': 'Acessível — ${relogio.elapsedMilliseconds} ms', 'lider': data['liderId']};
        } catch (_) {
          return {'descricao': 'Indisponível', 'lider': null};
        }
      }));
      final observados = respostas.map((r) => r['lider']).where((l) => l != null).toSet();
      final descricao = observados.isEmpty ? 'indisponível' : observados.length == 1 ? '${observados.first}' : 'eleição em andamento';
      atualizar(() {
        lider = descricao;
        diagnostico = respostas.map((r) => r['descricao'] as String).toList();
      });
    } finally {
      verificandoLider = false;
    }
  }
  Future<void> consultar() async {
    final numero = id; final u = usuario;
    if (numero == null || numero < 0 || u == null) { atualizar(() => status = 'Informe uma conta válida.'); return; }
    try {
      final atual = await api.request(numero % 3, '/contas/$numero');
      await store.salvarConta(u, atual);
      atualizar(() { conta = atual; status = 'Saldo atualizado.'; });
    } catch (e) {
      final cached = await store.conta(u, numero);
      atualizar(() { conta = cached; status = cached == null ? erro(e) : 'Sem resposta da agência. Exibindo último saldo armazenado.'; });
    }
    await atualizarFila();
  }
  Future<void> movimentar(String tipo) async {
    final u = usuario; final atual = conta; final numero = id;
    final valor = double.tryParse(amount.text.replaceAll(',', '.'));
    final destino = int.tryParse(destination.text);
    if (u == null || atual == null || numero == null || atual['id'] != numero || valor == null || !valor.isFinite || valor <= 0 || (valor * 100 - (valor * 100).round()).abs() > 0.000001 || (tipo == 'TRANSFERENCIA' && (destino == null || destino < 0 || destino == numero))) {
      atualizar(() => status = 'Confira conta, valor e destino. Consulte a conta antes de movimentar.'); return;
    }
    if (atual['vetorVersao'] == null || atual['sessaoServidor'] == null) { atualizar(() => status = 'A agência não informou a versão necessária para sincronizar.'); return; }
    if (tipo != 'DEPOSITO' && saldoEstimado < valor) { atualizar(() => status = 'Saldo estimado insuficiente.'); return; }
    final operacao = <String, dynamic>{'operacaoId': const Uuid().v4(), 'contaId': numero, 'tipo': tipo, 'valor': valor, 'vetorBase': atual['vetorVersao'], 'sessaoServidor': atual['sessaoServidor'], if (tipo == 'TRANSFERENCIA') 'destinoId': destino};
    await store.enfileirar(u, operacao);
    amount.clear();
    await atualizarFila();
    atualizar(() => status = 'Operação registrada no dispositivo; aguardando confirmação.');
    await sincronizar();
  }
  Future<void> descartar(Map<String, Object?> item) async {
    final confirmacao = await showDialog<bool>(context: context, builder: (context) => AlertDialog(title: const Text('Descartar operação?'), content: const Text('A operação será removida da fila. As operações posteriores desta conta precisarão de revisão.'), actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')), FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Descartar'))]));
    if (confirmacao != true || usuario == null) return;
    await store.descartar(usuario!, item);
    await atualizarFila();
    atualizar(() => status = 'Operação descartada. Consulte o saldo antes de refazê-la.');
  }
  Future<void> sincronizar() async {
    final u = usuario;
    if (u == null || sincronizando) return;
    sincronizando = true;
    try {
      final rows = await store.pendentes(u);
      final bloqueadas = <int>{};
      for (final item in rows) {
        final numero = item['conta'] as int;
        if (bloqueadas.contains(numero)) continue;
        if (item['estado'] != 'PENDENTE') { bloqueadas.add(numero); continue; }
        final atualizados = await store.pendentes(u, conta: numero);
        final atuais = atualizados.where((row) => row['ordem'] == item['ordem']);
        if (atuais.isEmpty) continue;
        final operacao = Map<String, dynamic>.from(jsonDecode(atuais.first['dados'] as String));
        try {
          final resposta = await api.request(numero % 3, '/sincronizacao', body: operacao);
          final atual = Map<String, dynamic>.from(resposta['conta'] as Map);
          final transferencia = resposta['transferencia'];
          await store.concluir(u, item, atual, transferencia: transferencia is Map ? Map<String, dynamic>.from(transferencia) : null);
          if (id == numero) atualizar(() => conta = atual);
          atualizar(() => status = transferencia == null ? 'Operação sincronizada.' : 'Transferência: ${transferencia['status']}. Consulte o acompanhamento.');
          if (transferencia != null) await acompanharTransferencias();
        } on ApiError catch (e) {
          if (e.status == 409) {
            await store.falha(item['ordem'] as int, 'CONFLITO', erro(e));
            atualizar(() => status = 'Conflito na conta $numero. Revise a fila antes de continuar.');
          } else if (e.status == 401 || e.status == 403) {
            atualizar(() => status = 'Sessão expirada. Entre novamente para sincronizar.');
            break;
          } else if (e.status >= 400 && e.status < 500) {
            await store.falha(item['ordem'] as int, 'FALHA', erro(e));
          }
          bloqueadas.add(numero);
        } catch (_) { bloqueadas.add(numero); }
      }
    } finally { sincronizando = false; await atualizarFila(); }
  }

  double get saldoEstimado {
    var saldo = (conta?['saldo'] as num?)?.toDouble() ?? 0;
    for (final item in fila.where((e) => e['conta'] == id && e['estado'] == 'PENDENTE')) {
      final op = jsonDecode(item['dados'] as String) as Map;
      saldo += (op['tipo'] == 'DEPOSITO' ? 1 : -1) * (op['valor'] as num).toDouble();
    }
    return saldo;
  }
  Widget input(TextEditingController c, String label, {bool secret = false, bool numeric = false}) => TextField(controller: c, obscureText: secret, keyboardType: numeric ? const TextInputType.numberWithOptions(decimal: true) : TextInputType.text, decoration: InputDecoration(labelText: label));
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('ICEIBank')),
    body: SafeArea(child: ListView(padding: const EdgeInsets.all(16), children: [
      if (usuario == null) ...[
        const Text('O endereço padrão é o acesso ao computador pelo emulador Android.'),
        input(host, 'Host do backend'), input(user, 'Usuário'), input(password, 'Senha', secret: true),
        const SizedBox(height: 12), FilledButton(onPressed: login, child: const Text('Entrar')),
      ] else ...[
        Text('Olá, $usuario', style: Theme.of(context).textTheme.titleLarge),
        Card(child: ListTile(title: const Text('Líder atual'), subtitle: Text('Agência $lider'), trailing: IconButton(onPressed: verificarLider, icon: const Icon(Icons.refresh)))),
        Card(child: ExpansionTile(title: const Text('Diagnóstico das agências'), subtitle: const Text('Disponibilidade e tempo de resposta'), children: [for (var i = 0; i < 3; i++) ListTile(title: Text('Agência $i'), subtitle: Text(diagnostico[i]))])),
        input(account, 'Número da conta', numeric: true),
        OutlinedButton(onPressed: consultar, child: const Text('Consultar saldo')),
        if (conta != null && conta!['id'] == id) Card(child: ListTile(title: Text('Saldo confirmado: R\$ ${(conta!['saldo'] as num).toStringAsFixed(2)}'), subtitle: Text('Saldo estimado: R\$ ${saldoEstimado.toStringAsFixed(2)} (inclui pendências)'))),
        input(amount, 'Valor', numeric: true), input(destination, 'Conta destino (transferência)', numeric: true),
        Wrap(spacing: 8, children: [FilledButton(onPressed: () => movimentar('DEPOSITO'), child: const Text('Depositar')), FilledButton(onPressed: () => movimentar('SAQUE'), child: const Text('Sacar')), FilledButton(onPressed: () => movimentar('TRANSFERENCIA'), child: const Text('Transferir'))]),
        const SizedBox(height: 16), Text('Fila de operações (${fila.length})', style: Theme.of(context).textTheme.titleMedium),
        for (final item in fila) ListTile(title: Text('${(jsonDecode(item['dados'] as String) as Map)['tipo']} — conta ${item['conta']}'), subtitle: Text('${item['estado']}${item['erro'] == null ? '' : ': ${item['erro']}'}'), leading: Icon(item['estado'] == 'CONFLITO' ? Icons.warning_amber : Icons.schedule), trailing: item['estado'] == 'CONFLITO' || item['estado'] == 'FALHA' ? TextButton(onPressed: () => descartar(item), child: const Text('Descartar')) : null),
        OutlinedButton(onPressed: sincronizar, child: const Text('Tentar sincronizar')),
        const SizedBox(height: 12), Text('Acompanhamento de transferências', style: Theme.of(context).textTheme.titleMedium),
        for (final item in transferencias) ListTile(title: Text('Transferência ${item['id']}'), subtitle: Text('Estado: ${(jsonDecode(item['dados'] as String) as Map)['status']}')),
        TextButton(onPressed: sair, child: const Text('Sair')),
      ],
      const SizedBox(height: 16), Text(status, key: const Key('status')),
    ])),
  );
}
