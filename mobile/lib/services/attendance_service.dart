/// VoiceAttend AI – API Service
/// ================================
/// Wraps all HTTP calls to the FastAPI backend.
/// Change [baseUrl] to match your backend host.
library;

import 'dart:io';
import 'package:http/http.dart' as http;
import 'dart:convert';

/// Model representing a successful attendance mark response.
class AttendanceResult {
  final String userName;
  final double confidence;
  final Map<String, dynamic> log;

  const AttendanceResult({
    required this.userName,
    required this.confidence,
    required this.log,
  });

  factory AttendanceResult.fromJson(Map<String, dynamic> json) {
    return AttendanceResult(
      userName: json['user_name'] as String,
      confidence: (json['confidence'] as num).toDouble(),
      log: json['log'] as Map<String, dynamic>,
    );
  }
}

/// Model representing a single attendance log entry.
class LogEntry {
  final int id;
  final String userName;
  final String timestamp;

  const LogEntry({
    required this.id,
    required this.userName,
    required this.timestamp,
  });

  factory LogEntry.fromJson(Map<String, dynamic> json) {
    return LogEntry(
      id: json['id'] as int,
      userName: json['user_name'] as String,
      timestamp: json['timestamp'] as String,
    );
  }
}

// ---------------------------------------------------------------------------
// Service Class
// ---------------------------------------------------------------------------

class AttendanceService {
  /// Base URL of the FastAPI backend.
  /// For local development with a physical device, use your machine's LAN IP.
  /// For emulator, use 10.0.2.2 (Android) or localhost (iOS simulator).
  // static const String baseUrl = 'http://10.0.2.2:8000';
  //static const String baseUrl = 'http://10.0.4.169:8000';
  static const String baseUrl = 'http://192.168.1.30:8000';

  // -------------------------------------------------------------------------
  // POST /attendance/mark
  // -------------------------------------------------------------------------

  /// Upload an audio [file] to the backend for speaker recognition.
  ///
  /// Returns an [AttendanceResult] on success.
  /// Throws an [Exception] if the server returns a non-200 status.
  static Future<AttendanceResult> markAttendance(File audioFile) async {
    final uri = Uri.parse('$baseUrl/attendance/mark');
    final request = http.MultipartRequest('POST', uri);

    // Attach the audio file under the field name expected by FastAPI ("audio")
    request.files.add(
      await http.MultipartFile.fromPath(
        'audio',
        audioFile.path,
        // Adjust MIME type if your recorder produces a different format
        // MediaType('audio', 'wav'),
      ),
    );

    final streamedResponse = await request.send();
    final response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      final body = json.decode(response.body) as Map<String, dynamic>;
      return AttendanceResult.fromJson(body);
    } else {
      final body = json.decode(response.body) as Map<String, dynamic>;
      throw Exception(body['detail'] ?? 'Unknown server error');
    }
  }

  // -------------------------------------------------------------------------
  // GET /attendance/test
  // -------------------------------------------------------------------------

  /// Ping the backend to confirm it is reachable.
  ///
  /// Returns true if the server responds with status 200.
  static Future<bool> testConnection() async {
    try {
      final uri = Uri.parse('$baseUrl/attendance/test');
      final response = await http.get(uri).timeout(const Duration(seconds: 5));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // -------------------------------------------------------------------------
  // GET /attendance/logs
  // -------------------------------------------------------------------------

  /// Fetch all attendance logs from the backend.
  ///
  /// Returns a list of [LogEntry] objects.
  static Future<List<LogEntry>> fetchAllLogs() async {
    final uri = Uri.parse('$baseUrl/attendance/logs');
    final response = await http.get(uri);

    if (response.statusCode == 200) {
      final body = json.decode(response.body) as Map<String, dynamic>;
      final list = body['logs'] as List<dynamic>;
      return list
          .map((e) => LogEntry.fromJson(e as Map<String, dynamic>))
          .toList();
    } else {
      throw Exception('Failed to load logs: ${response.statusCode}');
    }
  }

  // -------------------------------------------------------------------------
  // GET /attendance/logs/{user_name}
  // -------------------------------------------------------------------------

  /// Fetch attendance logs for a specific [userName].
  static Future<List<LogEntry>> fetchLogsForUser(String userName) async {
    final encodedName = Uri.encodeComponent(userName);
    final uri = Uri.parse('$baseUrl/attendance/logs/$encodedName');
    final response = await http.get(uri);

    if (response.statusCode == 200) {
      final body = json.decode(response.body) as Map<String, dynamic>;
      final list = body['logs'] as List<dynamic>;
      return list
          .map((e) => LogEntry.fromJson(e as Map<String, dynamic>))
          .toList();
    } else {
      throw Exception('Failed to load user logs: ${response.statusCode}');
    }
  }
}
