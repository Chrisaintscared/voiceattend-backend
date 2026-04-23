// lib/services/auth_service.dart
// All HTTP calls for authentication, admin panel, and voice login.

import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthService {
  // 🌐 Backend base URL (REAL PHONE)
  static const String _baseUrl = 'http://192.168.1.30:8000';

  static const _storage = FlutterSecureStorage();
  static const _tokenKey = 'jwt_token';
  static const _userKey = 'current_user';

  // ─── STORAGE ────────────────────────────────────────────────
  static Future<void> saveToken(String token) async {
    await _storage.write(key: _tokenKey, value: token);
  }

  static Future<String?> getToken() async {
    return _storage.read(key: _tokenKey);
  }

  static Future<void> saveUser(Map<String, dynamic> user) async {
    await _storage.write(key: _userKey, value: jsonEncode(user));
  }

  static Future<Map<String, dynamic>?> getStoredUser() async {
    final raw = await _storage.read(key: _userKey);
    if (raw == null) return null;
    return jsonDecode(raw) as Map<String, dynamic>;
  }

  static Future<void> logout() async {
    await _storage.deleteAll();
  }

  static Future<Map<String, String>> _authHeaders() async {
    final token = await getToken();
    return {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  // ─── REGISTER ───────────────────────────────────────────────
  static Future<Map<String, dynamic>> register({
    required String name,
    required String email,
    required String password,
    String? role,
    required File voiceFile,
  }) async {
    final uri = Uri.parse('$_baseUrl/register');

    final req = http.MultipartRequest('POST', uri)
      ..fields['name'] = name
      ..fields['email'] = email
      ..fields['password'] = password
      ..files.add(await http.MultipartFile.fromPath('voice', voiceFile.path));

    if (role != null && role.isNotEmpty) {
      req.fields['role'] = role;
    }

    final streamed = await req.send();
    final body = await streamed.stream.bytesToString();

    final data = jsonDecode(body);

    if (streamed.statusCode == 201) {
      await saveToken(data['access_token']);
      await saveUser(data['user']);
      return Map<String, dynamic>.from(data);
    }

    throw Exception(data['detail'] ?? 'Registration failed');
  }

  // ─── LOGIN ──────────────────────────────────────────────────
  static Future<Map<String, dynamic>> login({
    required String email,
    required String password,
  }) async {
    final res = await http.post(
      Uri.parse('$_baseUrl/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'email': email,
        'password': password,
      }),
    );

    final data = jsonDecode(res.body);

    if (res.statusCode == 200) {
      await saveToken(data['access_token']);
      await saveUser(data['user']);
      return Map<String, dynamic>.from(data);
    }

    throw Exception(data['detail'] ?? 'Login failed');
  }

  // ─── VOICE LOGIN ────────────────────────────────────────────
  static Future<Map<String, dynamic>> voiceLogin(File voiceFile) async {
    final uri = Uri.parse('$_baseUrl/voice-login');

    final req = http.MultipartRequest('POST', uri)
      ..files.add(await http.MultipartFile.fromPath('voice', voiceFile.path));

    final streamed = await req.send();
    final body = await streamed.stream.bytesToString();

    final data = jsonDecode(body);

    if (streamed.statusCode == 200) {
      await saveToken(data['access_token']);
      await saveUser(data['user']);
      return Map<String, dynamic>.from(data);
    }

    throw Exception(data['detail'] ?? 'Voice login failed');
  }

  // ─── ADMIN: USERS ───────────────────────────────────────────
  static Future<List<Map<String, dynamic>>> adminListUsers() async {
    final res = await http.get(
      Uri.parse('$_baseUrl/admin/users'),
      headers: await _authHeaders(),
    );

    if (res.statusCode == 200) {
      final list = jsonDecode(res.body) as List;
      return list.map((e) => Map<String, dynamic>.from(e)).toList();
    }

    throw Exception('Could not load users');
  }

  static Future<void> adminDeleteUser(String userId) async {
    final res = await http.delete(
      Uri.parse('$_baseUrl/admin/users/$userId'),
      headers: await _authHeaders(),
    );

    if (res.statusCode != 204) {
      final data = jsonDecode(res.body);
      throw Exception(data['detail'] ?? 'Delete failed');
    }
  }

  // ─── ADMIN: ATTENDANCE ──────────────────────────────────────
  static Future<List<Map<String, dynamic>>> adminGetAttendance({
    int limit = 100,
  }) async {
    final res = await http.get(
      Uri.parse('$_baseUrl/admin/attendance?limit=$limit'),
      headers: await _authHeaders(),
    );

    if (res.statusCode == 200) {
      final list = jsonDecode(res.body) as List;
      return list.map((e) => Map<String, dynamic>.from(e)).toList();
    }

    throw Exception('Could not load attendance logs');
  }

  // ─── ADMIN: ROLE UPDATE ─────────────────────────────────────
  static Future<void> adminUpdateRole(
    String userId,
    String role,
  ) async {
    final res = await http.put(
      Uri.parse('$_baseUrl/admin/users/$userId/role'),
      headers: await _authHeaders(),
      body: jsonEncode({'role': role}),
    );

    if (res.statusCode != 200) {
      final data = jsonDecode(res.body);
      throw Exception(data['detail'] ?? 'Role update failed');
    }
  }
}
