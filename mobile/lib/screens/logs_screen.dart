/// VoiceAttend AI – Logs Screen
/// ================================
/// Displays all attendance records fetched from the backend.
library;

import 'package:flutter/material.dart';
import '../services/attendance_service.dart';

class LogsScreen extends StatefulWidget {
  const LogsScreen({super.key});

  @override
  State<LogsScreen> createState() => _LogsScreenState();
}

class _LogsScreenState extends State<LogsScreen> {
  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------

  late Future<List<LogEntry>> _logsFuture;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  void _refresh() {
    setState(() {
      _logsFuture = AttendanceService.fetchAllLogs();
    });
  }

  // -------------------------------------------------------------------------
  // Build
  // -------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A1628),

      // ── App Bar ───────────────────────────────────────────────────────────
      appBar: AppBar(
        backgroundColor: const Color(0xFF0A1628),
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, color: Color(0xFF00C9A7)),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          'Attendance Logs',
          style: TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.w700,
            fontSize: 20,
          ),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: Color(0xFF00C9A7)),
            onPressed: _refresh,
          ),
          const SizedBox(width: 8),
        ],
      ),

      // ── Body ──────────────────────────────────────────────────────────────
      body: FutureBuilder<List<LogEntry>>(
        future: _logsFuture,
        builder: (context, snapshot) {
          // Loading state
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(
              child: CircularProgressIndicator(color: Color(0xFF00C9A7)),
            );
          }

          // Error state
          if (snapshot.hasError) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.cloud_off, color: Colors.redAccent, size: 48),
                    const SizedBox(height: 16),
                    Text(
                      'Failed to load logs:\n${snapshot.error}',
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.redAccent, fontSize: 14),
                    ),
                    const SizedBox(height: 20),
                    ElevatedButton.icon(
                      onPressed: _refresh,
                      icon: const Icon(Icons.refresh),
                      label: const Text('Retry'),
                    ),
                  ],
                ),
              ),
            );
          }

          // Empty state
          final logs = snapshot.data ?? [];
          if (logs.isEmpty) {
            return const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.inbox_outlined, color: Colors.white24, size: 64),
                  SizedBox(height: 16),
                  Text(
                    'No attendance records yet.\nMark attendance on the Home screen.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.white38, fontSize: 14),
                  ),
                ],
              ),
            );
          }

          // Log list
          return ListView.separated(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            itemCount: logs.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) => _LogTile(entry: logs[index]),
          );
        },
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Log Tile Widget
// ---------------------------------------------------------------------------

class _LogTile extends StatelessWidget {
  final LogEntry entry;
  const _LogTile({required this.entry});

  @override
  Widget build(BuildContext context) {
    // Parse ISO timestamp for display
    String formattedTime = entry.timestamp;
    try {
      final dt = DateTime.parse(entry.timestamp).toLocal();
      formattedTime =
          '${dt.year}-${_pad(dt.month)}-${_pad(dt.day)}  '
          '${_pad(dt.hour)}:${_pad(dt.minute)}:${_pad(dt.second)}';
    } catch (_) {}

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF132237),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.white.withOpacity(0.06)),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),

        // Avatar with initials
        leading: CircleAvatar(
          backgroundColor: const Color(0xFF00C9A7).withOpacity(0.15),
          child: Text(
            entry.userName.isNotEmpty
                ? entry.userName[0].toUpperCase()
                : '?',
            style: const TextStyle(
              color: Color(0xFF00C9A7),
              fontWeight: FontWeight.bold,
              fontSize: 18,
            ),
          ),
        ),

        title: Text(
          entry.userName,
          style: const TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.w600,
            fontSize: 15,
          ),
        ),

        subtitle: Text(
          formattedTime,
          style: TextStyle(
            color: Colors.white.withOpacity(0.45),
            fontSize: 12,
          ),
        ),

        trailing: Text(
          '#${entry.id}',
          style: TextStyle(
            color: Colors.white.withOpacity(0.25),
            fontSize: 12,
          ),
        ),
      ),
    );
  }

  String _pad(int v) => v.toString().padLeft(2, '0');
}
