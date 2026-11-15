import 'dart:async';
import 'dart:convert';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';
import 'api.dart';
import 'storage.dart';

const _fundo = Color(0xFF0B100E);
const _painel = Color(0xFF141D18);
const _borda = Color(0xFF2A382F);
const _verde = Color(0xFFA4F077);
const _texto = Color(0xFFEDF4EF);
const _suave = Color(0xFFA8B8AD);

ThemeData temaIceiBank() {
  final cores = ColorScheme.fromSeed(seedColor: _verde, brightness: Brightness.dark,
      surface: _painel, primary: _verde);
  final borda = OutlineInputBorder(borderRadius: BorderRadius.circular(12),
      borderSide: const BorderSide(color: _borda));
  return ThemeData(
    brightness: Brightness.dark, useMaterial3: true, colorScheme: cores,
    scaffoldBackgroundColor: _fundo,
    textTheme: ThemeData.dark().textTheme.apply(bodyColor: _texto, displayColor: _texto),
    inputDecorationTheme: InputDecorationTheme(
      filled: true, fillColor: const Color(0xFF0C130F),
      labelStyle: const TextStyle(color: _suave),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      border: borda, enabledBorder: borda,
      focusedBorder: borda.copyWith(borderSide: const BorderSide(color: _verde, width: 2)),
    ),
    filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(
      backgroundColor: _verde, foregroundColor: const Color(0xFF14240E),
      minimumSize: const Size(0, 48),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      textStyle: const TextStyle(fontWeight: FontWeight.w700),
    )),
    outlinedButtonTheme: OutlinedButtonThemeData(style: OutlinedButton.styleFrom(
      foregroundColor: _texto, minimumSize: const Size(0, 48),
      side: const BorderSide(color: _borda),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    )),
    textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(foregroundColor: _verde,
        minimumSize: const Size(0, 48))),
    dividerColor: _borda,
  );
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final storage = Storage();
  await storage.init();
  runApp(MaterialApp(debugShowCheckedModeBanner: false, title: 'ICEIBank', theme: temaIceiBank(), home: Banking(storage: storage)));
}

class Banking extends StatefulWidget {
  const Banking({super.key, required this.storage, this.consultarConectividade, this.criarApi, this.armazenamentoSeguro});
  final Storage storage;
  final Future<List<ConnectivityResult>> Function()? consultarConectividade;
  final Api Function(String)? criarApi;
  final FlutterSecureStorage? armazenamentoSeguro;
  @override
  State<Banking> createState() => _BankingState();
}

class _BankingState extends State<Banking> with WidgetsBindingObserver {
  final host = TextEditingController(text: '10.0.2.2');
  final user = TextEditingController();
  final password = TextEditingController();
  final confirmPassword = TextEditingController();
  final account = TextEditingController();
  final accountName = TextEditingController();
  final initialBalance = TextEditingController(text: '0');
  final amount = TextEditingController();
  final destination = TextEditingController();
  late Api api;
  late final FlutterSecureStorage secure;
  String? usuario;
  Map<String, dynamic>? conta;
  List<Map<String, Object?>> fila = [];
  List<Map<String, Object?>> transferencias = [];
  String status = 'Entre para começar.';
  String lider = 'Buscando...';
  List<String> diagnostico = List.filled(3, 'Aguardando consulta');
  bool verificandoLider = false;
  bool sincronizando = false;
  bool registrandoOperacao = false;
  bool cadastrando = false;
  bool criandoUsuario = false;
  int geracaoSessao = 0;
  Future<void> _persistenciaSessao = Future.value();
  Timer? timer;
  StreamSubscription<List<ConnectivityResult>>? connectivity;
  Storage get store => widget.storage;
  Api novaApi(String servidor) => widget.criarApi?.call(servidor) ?? Api(servidor);
  int? get id => int.tryParse(account.text);
  // O mesmo usuário pode existir em servidores independentes. Não misture
  // cache ou operações entre hosts, mesmo se os nomes forem iguais.
  String? get perfil => usuario == null ? null : '${api.host}|$usuario';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    secure = widget.armazenamentoSeguro ?? const FlutterSecureStorage();
    api = novaApi(host.text);
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
    for (final controller in [host, user, password, confirmPassword, account, accountName, initialBalance, amount, destination]) { controller.dispose(); }
    super.dispose();
  }
  void atualizar(VoidCallback f) { if (mounted) setState(f); }
  String erro(Object e) => e is ApiError ? (e.data is Map ? '${(e.data as Map)['detail'] ?? e.data}' : '${e.data}') : 'Rede indisponível ou tempo esgotado.';

  // Login e logout podem terminar fora de ordem. Serializar as escritas impede
  // que um login antigo volte a gravar credenciais depois do logout.
  Future<void> _alterarCredenciais(Future<void> Function() acao) {
    final tarefa = _persistenciaSessao.then((_) => acao());
    _persistenciaSessao = tarefa.then<void>((_) {}, onError: (Object _, StackTrace __) {});
    return tarefa;
  }

  Future<void> restaurarSessao() async {
    final geracao = geracaoSessao;
    final nome = await secure.read(key: 'usuario');
    final token = await secure.read(key: 'jwt');
    final servidor = await secure.read(key: 'host');
    if (nome == null || token == null || servidor == null || !mounted || geracao != geracaoSessao) return;
    host.text = servidor; user.text = nome; api = novaApi(servidor); api.token = token;
    atualizar(() { usuario = nome; status = 'Sessão restaurada; dados offline disponíveis.'; });
    await atualizarFila();
    await acompanharTransferencias();
    await sincronizar();
  }

  Future<void> login() async {
    final geracao = ++geracaoSessao;
    final servidor = host.text.trim();
    final nome = user.text.trim();
    final senha = password.text;
    final cliente = novaApi(servidor);
    bool sessaoAtual() => mounted && geracao == geracaoSessao;
    try {
      Map<String, dynamic>? result;
      Object? lastError;
      for (var agencia = 0; agencia < 3; agencia++) {
        if (!sessaoAtual()) return;
        try {
          result = await cliente.request(agencia, '/auth/login', body: {'usuario': nome, 'senha': senha});
          break;
        } catch (e) { lastError = e; }
      }
      if (!sessaoAtual()) return;
      if (result == null) throw lastError ?? Exception('Nenhuma agência disponível');
      cliente.token = result['access_token'] as String;
      await _alterarCredenciais(() async {
        if (!sessaoAtual()) return;
        await secure.write(key: 'usuario', value: nome);
        await secure.write(key: 'host', value: servidor);
        await secure.write(key: 'jwt', value: cliente.token);
        if (!sessaoAtual()) await secure.deleteAll();
      });
      if (!sessaoAtual()) return;
      api = cliente;
      atualizar(() { usuario = nome; password.clear(); status = 'Sessão iniciada.'; });
      await verificarLider();
      if (!sessaoAtual()) return;
      await atualizarFila();
      if (!sessaoAtual()) return;
      await sincronizar();
    } catch (e) { if (sessaoAtual()) atualizar(() => status = erro(e)); }
  }
  Future<void> cadastrarUsuario() async {
    if (cadastrando) return;
    final nome = user.text.trim();
    final senha = password.text;
    if (!RegExp(r'^[A-Za-z0-9._-]{3,40}$').hasMatch(nome)) {
      atualizar(() => status = 'Usuário deve ter de 3 a 40 letras, números ou . _ -');
      return;
    }
    if (senha.length < 6 || senha != confirmPassword.text) {
      atualizar(() => status = senha.length < 6 ? 'A senha deve ter pelo menos 6 caracteres.' : 'As senhas não conferem.');
      return;
    }
    atualizar(() => cadastrando = true);
    final cliente = novaApi(host.text.trim());
    try {
      int? agencia;
      for (var i = 0; i < 3; i++) {
        try { await cliente.request(i, '/'); agencia = i; break; } catch (_) { /* Verificação sem efeito. */ }
      }
      if (agencia == null) throw Exception('Nenhuma agência disponível');
      // Um timeout pode ocorrer após o cadastro; não repetir o POST cegamente.
      await cliente.request(agencia, '/auth/cadastro', body: {'usuario': nome, 'senha': senha});
      atualizar(() { criandoUsuario = false; status = 'Usuário criado. Entre com suas credenciais.'; password.clear(); confirmPassword.clear(); });
    } catch (e) {
      atualizar(() => status = e is ApiError ? erro(e) : 'Não foi possível confirmar o cadastro. Verifique a rede e tente entrar antes de repetir.');
    } finally { atualizar(() => cadastrando = false); }
  }
  Future<void> sair() async {
    geracaoSessao++;
    atualizar(() { usuario = null; api.token = null; conta = null; fila = []; transferencias = []; status = 'Sessão encerrada.'; });
    await _alterarCredenciais(() => secure.deleteAll());
  }
  Future<void> atualizarFila() async {
    final geracao = geracaoSessao;
    final u = perfil; if (u == null) return;
    final rows = await store.pendentes(u);
    if (geracao != geracaoSessao || perfil != u) return;
    atualizar(() => fila = rows);
  }
  Future<void> acompanharTransferencias() async {
    final geracao = geracaoSessao;
    final cliente = api;
    final u = perfil; if (u == null) return;
    final rows = await store.transferencias(u);
    for (final row in rows) {
      if (geracao != geracaoSessao || perfil != u) return;
      final dados = Map<String, dynamic>.from(jsonDecode(row['dados'] as String));
      if (dados['status'] == 'CONFIRMADA' || dados['status'] == 'FALHOU') continue;
      try {
        final atual = await cliente.request(row['agencia'] as int, '/transferencias/${row['id']}');
        await store.salvarTransferencia(u, row['agencia'] as int, atual);
      } catch (_) { /* Manter último estado, inclusive quando a agência está indisponível. */ }
    }
    final atualizadas = await store.transferencias(u);
    if (geracao != geracaoSessao || perfil != u) return;
    atualizar(() => transferencias = atualizadas);
  }
  Future<void> verificarLider() async {
    if (verificandoLider) return;
    final geracao = geracaoSessao;
    final cliente = api;
    verificandoLider = true;
    try {
      final respostas = await Future.wait(List.generate(3, (i) async {
        final relogio = Stopwatch()..start();
        try {
          final data = await cliente.request(i, '/bully/lider');
          relogio.stop();
          return {'descricao': 'Acessível — ${relogio.elapsedMilliseconds} ms', 'lider': data['liderId'], 'emEleicao': data['emEleicao'] == true};
        } catch (_) {
          return {'descricao': 'Indisponível', 'lider': null, 'emEleicao': false};
        }
      }));
      if (geracao != geracaoSessao) return;
      final observados = respostas.map((r) => r['lider']).where((l) => l != null).toSet();
      final emEleicao = respostas.any((r) => r['emEleicao'] == true);
      final descricao = emEleicao || observados.length > 1 ? 'eleição em andamento' : observados.isEmpty ? 'indisponível' : '${observados.first}';
      atualizar(() {
        lider = descricao;
        diagnostico = respostas.map((r) => r['descricao'] as String).toList();
      });
    } finally {
      verificandoLider = false;
    }
  }
  Future<void> consultar() async {
    final geracao = geracaoSessao;
    final numero = id; final u = perfil;
    if (numero == null || numero < 0 || u == null) { atualizar(() => status = 'Informe uma conta válida.'); return; }
    try {
      final atual = await api.request(numero % 3, '/contas/$numero');
      await store.salvarConta(u, atual);
      if (geracao != geracaoSessao || perfil != u || id != numero) return;
      atualizar(() { conta = atual; status = 'Saldo atualizado.'; });
    } catch (e) {
      final cached = await store.conta(u, numero);
      if (geracao != geracaoSessao || perfil != u || id != numero) return;
      atualizar(() {
        conta = cached;
        status = e is ApiError
            ? '${erro(e)}${cached == null ? '' : ' Exibindo último saldo armazenado.'}'
            : cached == null ? erro(e) : 'Sem resposta da agência. Exibindo último saldo armazenado.';
      });
    }
    await atualizarFila();
  }
  Future<void> criarConta() async {
    final geracao = geracaoSessao;
    final numero = id;
    final u = perfil;
    final nome = accountName.text.trim();
    final saldo = double.tryParse(initialBalance.text.replaceAll(',', '.'));
    if (u == null || numero == null || numero < 0 || nome.isEmpty || saldo == null ||
        !saldo.isFinite || saldo < 0 || (saldo * 100 - (saldo * 100).round()).abs() > 0.000001) {
      atualizar(() => status = 'Informe número, nome e saldo inicial válidos.');
      return;
    }
    try {
      final criada = await api.request(numero % 3, '/contas', body: {
        'id': numero, 'nomeAluno': nome, 'saldoInicial': saldo,
      });
      await store.salvarConta(u, criada);
      if (geracao != geracaoSessao || perfil != u || id != numero) return;
      atualizar(() { conta = criada; status = 'Conta criada.'; });
      await atualizarFila();
    } catch (e) {
      if (geracao != geracaoSessao || perfil != u) return;
      atualizar(() => status = erro(e));
    }
  }
  Future<void> movimentar(String tipo) async {
    if (registrandoOperacao) return;
    final u = perfil; final atual = conta; final numero = id;
    final valor = double.tryParse(amount.text.replaceAll(',', '.'));
    final destino = int.tryParse(destination.text);
    if (u == null || atual == null || numero == null || atual['id'] != numero || valor == null || !valor.isFinite || valor <= 0 || (valor * 100 - (valor * 100).round()).abs() > 0.000001 || (tipo == 'TRANSFERENCIA' && (destino == null || destino < 0 || destino == numero))) {
      atualizar(() => status = 'Confira conta, valor e destino. Consulte a conta antes de movimentar.'); return;
    }
    if (atual['vetorVersao'] == null || atual['sessaoServidor'] == null) { atualizar(() => status = 'A agência não informou a versão necessária para sincronizar.'); return; }
    if (fila.any((item) => item['conta'] == numero && (item['estado'] == 'CONFLITO' || item['estado'] == 'FALHA'))) {
      atualizar(() => status = 'Resolva a operação bloqueada desta conta antes de adicionar outra.'); return;
    }
    final estimado = saldoEstimado;
    if (tipo != 'DEPOSITO' && estimado != null && estimado < valor) { atualizar(() => status = 'Saldo estimado insuficiente.'); return; }
    final operacao = <String, dynamic>{'operacaoId': const Uuid().v4(), 'contaId': numero, 'tipo': tipo, 'valor': valor, 'vetorBase': atual['vetorVersao'], 'sessaoServidor': atual['sessaoServidor'], if (tipo == 'TRANSFERENCIA') 'destinoId': destino};
    registrandoOperacao = true;
    try {
      await store.enfileirar(u, operacao);
      amount.clear();
      await atualizarFila();
      atualizar(() => status = 'Operação registrada no dispositivo; aguardando confirmação.');
      await sincronizar();
    } finally {
      registrandoOperacao = false;
    }
  }
  Future<void> descartar(Map<String, Object?> item) async {
    final confirmacao = await showDialog<bool>(context: context, builder: (context) => AlertDialog(title: const Text('Descartar operação?'), content: const Text('A operação será removida da fila. As operações posteriores desta conta precisarão de revisão.'), actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')), FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Descartar'))]));
    final u = perfil;
    if (confirmacao != true || u == null) return;
    await store.descartar(u, item);
    await atualizarFila();
    atualizar(() => status = 'Operação descartada. Consulte o saldo antes de refazê-la.');
  }
  Future<void> sincronizar() async {
    final u = perfil;
    if (u == null || sincronizando) return;
    final cliente = api;
    final geracao = geracaoSessao;
    bool sessaoAtual() => geracao == geracaoSessao && perfil == u;
    sincronizando = true;
    try {
      // A conectividade só evita iniciar envios quando não há nenhuma rede.
      // Com rede presente, uma falha de HTTP continua sendo ambígua e deve
      // preservar o UUID e o estado INCERTA para reconciliação.
      try {
        final redes = await (widget.consultarConectividade?.call() ?? Connectivity().checkConnectivity());
        if (redes.isEmpty || redes.every((r) => r == ConnectivityResult.none)) {
          if (sessaoAtual()) atualizar(() => status = 'Sem rede. Operações aguardam sincronização.');
          return;
        }
      } catch (_) {
        // Se o plugin não souber informar, tente HTTP de forma conservadora.
      }
      if (!sessaoAtual()) return;
      final rows = await store.pendentes(u);
      final bloqueadas = <int>{};
      // Wi-Fi não garante acesso à agência. Consultar sem efeitos antes
      // de enviar preserva operações ainda locais quando ela está fora.
      final agenciasAcessiveis = <int, bool>{};
      for (final item in rows) {
        if (!sessaoAtual()) break;
        final numero = item['conta'] as int;
        if (bloqueadas.contains(numero)) continue;
        if (item['estado'] != 'PENDENTE' && item['estado'] != 'INCERTA') { bloqueadas.add(numero); continue; }
        final atualizados = await store.pendentes(u, conta: numero);
        final atuais = atualizados.where((row) => row['ordem'] == item['ordem']);
        if (atuais.isEmpty) continue;
        final operacao = Map<String, dynamic>.from(jsonDecode(atuais.first['dados'] as String));
        final agencia = numero % 3;
        if (atuais.first['estado'] == 'PENDENTE') {
          if (!agenciasAcessiveis.containsKey(agencia)) {
            try {
              await cliente.request(agencia, '/');
              agenciasAcessiveis[agencia] = true;
            } catch (_) {
              agenciasAcessiveis[agencia] = false;
            }
          }
          if (!sessaoAtual()) break;
          if (!agenciasAcessiveis[agencia]!) {
            bloqueadas.add(numero);
            atualizar(() => status = 'Agência $agencia indisponível. Operações aguardam sincronização.');
            continue;
          }
        }
        try {
          // Persistir antes do HTTP: se o app fechar ou perder a resposta,
          // o próximo envio mantém exatamente o mesmo UUID e payload.
          await store.falha(item['ordem'] as int, 'INCERTA', 'Aguardando confirmação do servidor.');
          if (!sessaoAtual()) break;
          await atualizarFila();
          if (!sessaoAtual()) break;
          final resposta = await cliente.request(numero % 3, '/sincronizacao', body: operacao);
          final atual = Map<String, dynamic>.from(resposta['conta'] as Map);
          final transferencia = resposta['transferencia'];
          await store.concluir(u, item, atual, transferencia: transferencia is Map ? Map<String, dynamic>.from(transferencia) : null);
          if (!sessaoAtual()) break;
          if (id == numero) atualizar(() => conta = atual);
          atualizar(() => status = transferencia == null ? 'Operação sincronizada.' : 'Transferência: ${transferencia['status']}. Consulte o acompanhamento.');
          if (transferencia != null) await acompanharTransferencias();
        } on ApiError catch (e) {
          if (e.status == 409) {
            final detail = e.data is Map ? (e.data as Map)['detail'] : null;
            final dados = detail is Map ? detail : e.data is Map ? e.data as Map : null;
            final contaServidor = dados?['conta'] ?? dados?['contaAtual'];
            String descricao = erro(e);
            if (contaServidor is Map && contaServidor['id'] == numero && contaServidor['saldo'] is num) {
              final atual = Map<String, dynamic>.from(contaServidor);
              await store.salvarConta(u, atual);
              descricao = '${dados?['codigo'] ?? 'VERSAO_CONFLITANTE'} — saldo atual no servidor: R\$ ${(atual['saldo'] as num).toStringAsFixed(2)}. Revise a operação.';
              if (sessaoAtual() && id == numero) atualizar(() => conta = atual);
            }
            await store.falha(item['ordem'] as int, 'CONFLITO', descricao);
            if (sessaoAtual()) atualizar(() => status = 'Conflito na conta $numero. Revise a fila antes de continuar.');
          } else if (e.status == 401 || e.status == 403) {
            if (sessaoAtual()) atualizar(() => status = 'Sessão expirada. Entre novamente para sincronizar.');
            break;
          } else if (e.status >= 400 && e.status < 500) {
            await store.falha(item['ordem'] as int, 'FALHA', erro(e));
          }
          bloqueadas.add(numero);
        } catch (_) { bloqueadas.add(numero); }
      }
    } finally { sincronizando = false; if (sessaoAtual()) await atualizarFila(); }
  }

  double? get saldoEstimado => projetarSaldo(conta, fila);
  Widget input(TextEditingController c, String label, {bool secret = false, bool numeric = false}) =>
      TextField(controller: c, obscureText: secret,
          onChanged: identical(c, account) ? (_) => atualizar(() {}) : null,
          keyboardType: numeric ? const TextInputType.numberWithOptions(decimal: true) : TextInputType.text,
          decoration: InputDecoration(labelText: label));

  Widget painel({required Widget child, Color color = _painel}) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _borda)),
    child: Material(type: MaterialType.transparency, child: child),
  );

  Widget titulo(String texto, {String? descricao}) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [Text(texto, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700)),
      if (descricao != null) ...[const SizedBox(height: 4), Text(descricao, style: const TextStyle(color: _suave, height: 1.4))]],
  );

  Widget aviso() => Semantics(liveRegion: true, child: Container(
    key: const Key('status'), width: double.infinity,
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
    decoration: BoxDecoration(color: const Color(0xFF1A2920), borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF395342))),
    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Icon(Icons.info_outline, size: 18, color: _verde), const SizedBox(width: 10),
      Expanded(child: Text(status, style: const TextStyle(color: _texto, height: 1.35))),
    ]),
  ));

  Widget marca() => const Row(mainAxisSize: MainAxisSize.min, children: [
    Icon(Icons.account_balance_wallet_outlined, color: _verde, size: 23), SizedBox(width: 9),
    Text.rich(TextSpan(children: [TextSpan(text: 'ICEI', style: TextStyle(color: _texto)),
      TextSpan(text: 'Bank', style: TextStyle(color: _verde))]),
      style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, letterSpacing: -.6)),
  ]);

  Widget acesso() => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    const Text('BEM-VINDO AO SEU BANCO', style: TextStyle(color: _verde, fontSize: 11,
        fontWeight: FontWeight.w700, letterSpacing: 1.4)),
    const SizedBox(height: 10),
    const Text('Seu dinheiro.\nDo seu jeito.', style: TextStyle(fontSize: 30, height: 1.12,
        fontWeight: FontWeight.w800, letterSpacing: -1)),
    const SizedBox(height: 8),
    const Text('Sua conta, suas movimentações e o controle na palma da mão.',
        style: TextStyle(color: _suave, height: 1.4)),
    const SizedBox(height: 18),
    painel(child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      titulo(criandoUsuario ? 'Crie seu acesso' : 'Acesse sua conta',
          descricao: criandoUsuario ? 'Escolha seus dados para começar.' : 'Entre com seu usuário e senha.'),
      const SizedBox(height: 16), input(user, 'Usuário'), const SizedBox(height: 12),
      input(password, 'Senha', secret: true),
      if (criandoUsuario) ...[const SizedBox(height: 12), input(confirmPassword, 'Confirmar senha', secret: true)],
      const SizedBox(height: 12), aviso(), const SizedBox(height: 12),
      FilledButton(onPressed: cadastrando ? null : (criandoUsuario ? cadastrarUsuario : login),
          child: Text(criandoUsuario ? 'Cadastrar' : 'Entrar')),
      TextButton(onPressed: cadastrando ? null : () => atualizar(() {
        criandoUsuario = !criandoUsuario; password.clear(); confirmPassword.clear();
        status = criandoUsuario ? 'Crie um usuário para acessar.' : 'Entre para começar.';
      }), child: Text(criandoUsuario ? 'Já tenho usuário' : 'Criar usuário')),
      const SizedBox(height: 4),
      input(host, 'Host do backend'),
      const SizedBox(height: 8),
      const Text('No emulador Android, use 10.0.2.2. Em outro dispositivo, informe o endereço do servidor.',
          style: TextStyle(color: _suave, fontSize: 12, height: 1.35)),
    ])),
  ]);

  Widget lideranca() => painel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Row(children: [
      Container(width: 42, height: 42, decoration: BoxDecoration(color: const Color(0xFF243A28),
          borderRadius: BorderRadius.circular(12)), child: const Icon(Icons.hub_outlined, color: _verde)),
      const SizedBox(width: 12),
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Líder atual', style: TextStyle(color: _suave, fontSize: 12)),
        const SizedBox(height: 3), Text(int.tryParse(lider) == null ? lider : 'Agência $lider',
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
      ])),
      IconButton(onPressed: verificarLider, tooltip: 'Atualizar liderança', icon: const Icon(Icons.refresh, color: _verde)),
    ]),
    const SizedBox(height: 6),
    ExpansionTile(tilePadding: EdgeInsets.zero, childrenPadding: EdgeInsets.zero,
      title: const Text('Diagnóstico das agências', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
      subtitle: const Text('Disponibilidade e tempo de resposta', style: TextStyle(color: _suave, fontSize: 12)),
      children: [for (var i = 0; i < 3; i++) ListTile(contentPadding: EdgeInsets.zero,
        dense: true, title: Text('Agência $i'), subtitle: Text(diagnostico[i]))]),
  ]));

  Widget saldo() {
    if (conta == null || conta!['id'] != id) {
      return painel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        titulo('Sua conta', descricao: 'Consulte sua conta para ver o saldo e movimentar.'),
        const SizedBox(height: 16), input(account, 'Número da conta', numeric: true),
        const SizedBox(height: 12), SizedBox(width: double.infinity,
            child: OutlinedButton(onPressed: consultar, child: const Text('Consultar saldo'))),
      ]));
    }
    return painel(color: const Color(0xFF263C29), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('CONTA ${conta!['id']}', style: const TextStyle(color: _verde, fontWeight: FontWeight.w700, fontSize: 11, letterSpacing: 1.2)),
      const SizedBox(height: 8), const Text('Saldo confirmado', style: TextStyle(color: _suave)),
      const SizedBox(height: 4), Text('R\$ ${(conta!['saldo'] as num).toStringAsFixed(2)}',
          style: const TextStyle(fontSize: 32, fontWeight: FontWeight.w800, letterSpacing: -1)),
      const SizedBox(height: 6),
      Text(saldoEstimado == null ? 'Saldo estimado indisponível: revise a fila ou aguarde confirmação.'
          : 'Saldo estimado: R\$ ${saldoEstimado!.toStringAsFixed(2)} (inclui pendências)',
          style: const TextStyle(color: _texto, fontSize: 12, height: 1.4)),
      const SizedBox(height: 16), input(account, 'Número da conta', numeric: true),
      const SizedBox(height: 12), SizedBox(width: double.infinity,
          child: OutlinedButton(onPressed: consultar, child: const Text('Consultar saldo'))),
    ]));
  }

  Widget movimentacoes() => painel(child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
    titulo('Movimentar', descricao: 'Selecione a conta, informe o valor e escolha uma operação.'),
    const SizedBox(height: 16), input(amount, 'Valor', numeric: true), const SizedBox(height: 12),
    input(destination, 'Conta destino (transferência)', numeric: true), const SizedBox(height: 14),
    Wrap(spacing: 8, runSpacing: 8, children: [
      FilledButton(onPressed: () => movimentar('DEPOSITO'), child: const Text('Depositar')),
      OutlinedButton(onPressed: () => movimentar('SAQUE'), child: const Text('Sacar')),
      OutlinedButton(onPressed: () => movimentar('TRANSFERENCIA'), child: const Text('Transferir')),
    ]),
  ]));

  Widget pendencias() => painel(child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
    titulo('Fila de operações (${fila.length})', descricao: 'Acompanhe as operações guardadas neste dispositivo.'),
    if (fila.isEmpty) const Padding(padding: EdgeInsets.symmetric(vertical: 12),
        child: Text('Nenhuma operação pendente.', style: TextStyle(color: _suave))),
    for (final item in fila) ListTile(contentPadding: EdgeInsets.zero,
      title: Text('${(jsonDecode(item['dados'] as String) as Map)['tipo']} — conta ${item['conta']}'),
      subtitle: Text('${item['estado']}${item['erro'] == null ? '' : ': ${item['erro']}'}'),
      leading: Icon(item['estado'] == 'CONFLITO' || item['estado'] == 'FALHA' ? Icons.warning_amber : Icons.schedule,
          color: item['estado'] == 'CONFLITO' || item['estado'] == 'FALHA' ? Colors.amber : _verde),
      trailing: item['estado'] == 'CONFLITO' || item['estado'] == 'FALHA'
          ? TextButton(onPressed: () => descartar(item), child: const Text('Descartar')) : null),
    OutlinedButton(onPressed: sincronizar, child: const Text('Tentar sincronizar')),
  ]));

  Widget painelConta() => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    const Text('VISÃO GERAL', style: TextStyle(color: _verde, fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 1.4)),
    const SizedBox(height: 8), Text('Olá, $usuario', style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w800, letterSpacing: -.5)),
    const SizedBox(height: 5), const Text('Acompanhe sua conta e suas movimentações.', style: TextStyle(color: _suave)),
    const SizedBox(height: 16), saldo(), const SizedBox(height: 14),
    lideranca(), const SizedBox(height: 14),
    painel(child: ExpansionTile(tilePadding: EdgeInsets.zero, childrenPadding: EdgeInsets.zero,
      title: const Text('Criar conta', style: TextStyle(fontWeight: FontWeight.w700)),
      subtitle: const Text('Abra uma nova conta na agência', style: TextStyle(color: _suave, fontSize: 12)),
      children: [input(accountName, 'Nome do titular'), const SizedBox(height: 12),
        input(initialBalance, 'Saldo inicial', numeric: true), const SizedBox(height: 12),
        SizedBox(width: double.infinity, child: OutlinedButton(onPressed: criarConta, child: const Text('Criar conta online')))])),
    const SizedBox(height: 14), movimentacoes(), const SizedBox(height: 14), pendencias(),
    const SizedBox(height: 14), painel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      titulo('Acompanhamento de transferências', descricao: 'Veja a confirmação dos créditos enviados.'),
      if (transferencias.isEmpty) const Padding(padding: EdgeInsets.only(top: 12),
          child: Text('Nenhuma transferência para acompanhar.', style: TextStyle(color: _suave))),
      for (final item in transferencias) ListTile(contentPadding: EdgeInsets.zero,
        title: Text('Transferência ${item['id']}'),
        subtitle: Text('Estado: ${(jsonDecode(item['dados'] as String) as Map)['status']}')),
    ])),
    const SizedBox(height: 18), Center(child: TextButton.icon(onPressed: sair,
        icon: const Icon(Icons.logout, size: 18), label: const Text('Sair'))),
  ]);

  @override
  Widget build(BuildContext context) => Theme(data: temaIceiBank(), child: Scaffold(
    appBar: AppBar(backgroundColor: _fundo, surfaceTintColor: Colors.transparent,
        title: marca(), toolbarHeight: 68,
        bottom: const PreferredSize(preferredSize: Size.fromHeight(1), child: Divider(height: 1, color: _borda))),
    bottomNavigationBar: usuario == null ? null : SafeArea(top: false, child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 12), child: aviso())),
    body: SafeArea(child: Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 560),
      child: ListView(padding: const EdgeInsets.fromLTRB(20, 24, 20, 32), children: [
        if (usuario == null) acesso() else painelConta(),
      ])))),
  ));
}
