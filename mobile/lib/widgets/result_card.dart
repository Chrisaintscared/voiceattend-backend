/// VoiceAttend AI – Result Card Widget
/// =========================================
/// Displays the voice recognition result after a successful attendance mark.
library;

import 'package:flutter/material.dart';
import '../services/attendance_service.dart';

class ResultCard extends StatelessWidget {
  final AttendanceResult result;

  const ResultCard({super.key, required this.result});

  @override
  Widget build(BuildContext context) {
    final confidencePct = (result.confidence * 100).toStringAsFixed(1);
    final logId         = result.log['id']?.toString() ?? '–';

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            const Color(0xFF00C9A7).withOpacity(0.12),
            const Color(0xFF0077B6).withOpacity(0.12),
          ],
          begin: Alignment.topLeft,
          end:   Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: const Color(0xFF00C9A7).withOpacity(0.35),
          width: 1.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Header ──────────────────────────────────────────────────────
          const Row(
            children: [
              Icon(Icons.person_pin_circle,
                  color: Color(0xFF00C9A7), size: 26),
              SizedBox(width: 10),
              Text(
                'Speaker Recognised',
                style: TextStyle(
                  color:      Color(0xFF00C9A7),
                  fontWeight: FontWeight.w700,
                  fontSize:   14,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),

          // ── User Name ────────────────────────────────────────────────────
          Text(
            result.userName,
            style: const TextStyle(
              color:      Colors.white,
              fontWeight: FontWeight.w800,
              fontSize:   28,
            ),
          ),
          const SizedBox(height: 14),

          // ── Confidence Bar ───────────────────────────────────────────────
          _InfoRow(
            label: 'Confidence',
            value: '$confidencePct%',
            trailing: ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: result.confidence,
                minHeight: 8,
                backgroundColor: Colors.white12,
                color: _confidenceColor(result.confidence),
              ),
            ),
          ),
          const SizedBox(height: 10),

          // ── Log ID ───────────────────────────────────────────────────────
          _InfoRow(label: 'Log ID', value: '#$logId'),
          const SizedBox(height: 10),

          // ── Timestamp ────────────────────────────────────────────────────
          _InfoRow(
            label: 'Recorded at',
            value: _formatTimestamp(result.log['timestamp']?.toString()),
          ),
        ],
      ),
    );
  }

  Color _confidenceColor(double v) {
    if (v >= 0.85) return const Color(0xFF00C9A7);
    if (v >= 0.60) return Colors.amberAccent;
    return Colors.redAccent;
  }

  String _formatTimestamp(String? raw) {
    if (raw == null) return '–';
    try {
      final dt = DateTime.parse(raw).toLocal();
      return '${dt.year}-${_p(dt.month)}-${_p(dt.day)} '
             '${_p(dt.hour)}:${_p(dt.minute)}:${_p(dt.second)}';
    } catch (_) {
      return raw;
    }
  }

  String _p(int v) => v.toString().padLeft(2, '0');
}

// ---------------------------------------------------------------------------
// Sub-widget – a labelled info row
// ---------------------------------------------------------------------------

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;
  final Widget? trailing;

  const _InfoRow({
    required this.label,
    required this.value,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label.toUpperCase(),
          style: TextStyle(
            color:    Colors.white.withOpacity(0.40),
            fontSize: 10,
            letterSpacing: 1.2,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 4),
        Row(
          children: [
            Text(
              value,
              style: const TextStyle(
                color:      Colors.white,
                fontSize:   15,
                fontWeight: FontWeight.w600,
              ),
            ),
            if (trailing != null) ...[
              const SizedBox(width: 12),
              Expanded(child: trailing!),
            ],
          ],
        ),
      ],
    );
  }
}
