import 'dart:convert';
import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

double? projetarSaldo(Map<String, dynamic>? conta, List<Map<String, Object?>> fila) {
  if (conta == null) return null;
  final operacoes = fila.where((item) => item['conta'] == conta['id']);
  // Uma resposta perdida pode já estar refletida no saldo consultado.
  // Só o replay com o mesmo UUID permite concluir a reconciliação.
  if (operacoes.any((item) => item['estado'] == 'INCERTA')) return null;
  var saldo = (conta['saldo'] as num).toDouble();
  for (final item in operacoes.where((item) => item['estado'] == 'PENDENTE')) {
    final op = jsonDecode(item['dados'] as String) as Map;
    saldo += (op['tipo'] == 'DEPOSITO' ? 1 : -1) * (op['valor'] as num).toDouble();
  }
  return saldo;
}

class Storage {
  late Database db;
  Future<void> init() async {
    db = await openDatabase(p.join(await getDatabasesPath(), 'iceibank.db'),
        version: 2, onUpgrade: (db, oldVersion, newVersion) async {
      // A versão anterior não distinguia pedidos enviados de pedidos locais.
      await db.update('fila', {'estado': 'INCERTA'},
          where: 'estado = ?', whereArgs: ['PENDENTE']);
    }, onCreate: (db, _) async {
      await db.execute('CREATE TABLE contas (usuario TEXT NOT NULL, id INTEGER NOT NULL, dados TEXT NOT NULL, PRIMARY KEY(usuario,id))');
      await db.execute('CREATE TABLE fila (ordem INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT NOT NULL, id TEXT NOT NULL UNIQUE, conta INTEGER NOT NULL, dados TEXT NOT NULL, estado TEXT NOT NULL, erro TEXT)');
      await db.execute('CREATE TABLE transferencias (usuario TEXT NOT NULL, id TEXT NOT NULL, agencia INTEGER NOT NULL, dados TEXT NOT NULL, PRIMARY KEY(usuario,id))');
    });
  }

  Future<Map<String, dynamic>?> conta(String usuario, int id) async {
    final rows = await db.query('contas', where: 'usuario = ? AND id = ?', whereArgs: [usuario, id]);
    return rows.isEmpty ? null : Map<String, dynamic>.from(jsonDecode(rows.first['dados'] as String));
  }

  Future<void> salvarConta(String usuario, Map<String, dynamic> conta) async {
    await db.insert('contas', {'usuario': usuario, 'id': conta['id'], 'dados': jsonEncode(conta)}, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> enfileirar(String usuario, Map<String, dynamic> operacao) async {
    await db.insert('fila', {'usuario': usuario, 'id': operacao['operacaoId'], 'conta': operacao['contaId'], 'dados': jsonEncode(operacao), 'estado': 'PENDENTE'});
  }

  Future<List<Map<String, Object?>>> pendentes(String usuario, {int? conta}) => db.query('fila', where: conta == null ? 'usuario = ?' : 'usuario = ? AND conta = ?', whereArgs: conta == null ? [usuario] : [usuario, conta], orderBy: 'ordem');

  Future<void> falha(int ordem, String estado, String erro) async {
    await db.update('fila', {'estado': estado, 'erro': erro}, where: 'ordem = ?', whereArgs: [ordem]);
  }

  Future<void> descartar(String usuario, Map<String, Object?> item) async {
    await db.transaction((tx) async {
      await tx.delete('fila', where: 'usuario = ? AND ordem = ?', whereArgs: [usuario, item['ordem']]);
      await tx.update('fila', {'estado': 'CONFLITO', 'erro': 'Operação anterior descartada. Consulte o saldo e revise esta operação.'}, where: 'usuario = ? AND conta = ? AND ordem > ? AND estado = ?', whereArgs: [usuario, item['conta'], item['ordem'], 'PENDENTE']);
    });
  }

  Future<List<Map<String, Object?>>> transferencias(String usuario) => db.query('transferencias', where: 'usuario = ?', whereArgs: [usuario]);

  Future<void> salvarTransferencia(String usuario, int agencia, Map<String, dynamic> dados) async {
    await db.insert('transferencias', {'usuario': usuario, 'id': dados['transferenciaId'], 'agencia': agencia, 'dados': jsonEncode(dados)}, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> concluir(String usuario, Map<String, Object?> item, Map<String, dynamic> conta, {Map<String, dynamic>? transferencia}) async {
    await db.transaction((tx) async {
      await tx.insert('contas', {'usuario': usuario, 'id': conta['id'], 'dados': jsonEncode(conta)}, conflictAlgorithm: ConflictAlgorithm.replace);
      if (transferencia != null) {
        await tx.insert('transferencias', {'usuario': usuario, 'id': transferencia['transferenciaId'], 'agencia': (conta['id'] as int) % 3, 'dados': jsonEncode(transferencia)}, conflictAlgorithm: ConflictAlgorithm.replace);
      }
      await tx.delete('fila', where: 'ordem = ?', whereArgs: [item['ordem']]);
      final proximos = await tx.query('fila', where: 'usuario = ? AND conta = ? AND estado = ?', whereArgs: [usuario, conta['id'], 'PENDENTE'], orderBy: 'ordem', limit: 1);
      if (proximos.isNotEmpty) {
        final proximo = Map<String, dynamic>.from(jsonDecode(proximos.first['dados'] as String));
        proximo['vetorBase'] = conta['vetorVersao'];
        proximo['sessaoServidor'] = conta['sessaoServidor'];
        await tx.update('fila', {'dados': jsonEncode(proximo)}, where: 'ordem = ?', whereArgs: [proximos.first['ordem']]);
      }
    });
  }
}
