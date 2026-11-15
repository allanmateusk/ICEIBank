import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiError implements Exception {
  ApiError(this.status, this.data);
  final int status;
  final dynamic data;
  @override
  String toString() => data.toString();
}

class Api {
  Api(this.host, {http.Client? client}) : _client = client;
  final String host;
  final http.Client? _client;
  String? token;
  Uri uri(int agencia, String path) => Uri.parse('http://$host:${4000 + agencia}$path');

  Future<Map<String, dynamic>> request(int agencia, String path, {Map<String, dynamic>? body, String? key}) async {
    final headers = <String, String>{'Content-Type': 'application/json', if (token != null) 'Authorization': 'Bearer $token', if (key != null) 'Idempotency-Key': key};
    final response = await (body == null
        ? (_client?.get(uri(agencia, path), headers: headers) ?? http.get(uri(agencia, path), headers: headers))
        : (_client?.post(uri(agencia, path), headers: headers, body: jsonEncode(body)) ?? http.post(uri(agencia, path), headers: headers, body: jsonEncode(body))))
        .timeout(const Duration(seconds: 5));
    dynamic data;
    try { data = jsonDecode(utf8.decode(response.bodyBytes)); } catch (_) { data = response.body; }
    if (response.statusCode < 200 || response.statusCode >= 300) throw ApiError(response.statusCode, data);
    return Map<String, dynamic>.from(data as Map);
  }
}
