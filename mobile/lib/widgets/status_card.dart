/// VoiceAttend AI – Status Card Widget
/// =========================================
/// Displays the current attendance flow state as a coloured banner card.
library;

import 'package:flutter/material.dart';
import '../screens/home_screen.dart';

class StatusCard extends StatelessWidget {
  final AttendanceState state;

  const StatusCard({super.key, required this.state});

  @override
  Widget build(BuildContext context) {
    final config = _configFor(state);

    return AnimatedContainer(
      duration: const Duration(milliseconds: 350),
      curve: Curves.easeInOut,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      decoration: BoxDecoration(
        color:        config.bgColor,
        borderRadius: BorderRadius.circular(16),
        border:       Border.all(color: config.borderColor, width: 1.2),
      ),
      child: Row(
        children: [
          Icon(config.icon, color: config.iconColor, size: 28),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  config.title,
                  style: TextStyle(
                    color:      config.iconColor,
                    fontWeight: FontWeight.w700,
                    fontSize:   15,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  config.subtitle,
                  style: TextStyle(
                    color:    config.iconColor.withOpacity(0.75),
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  _StatusConfig _configFor(AttendanceState state) {
    return switch (state) {
      AttendanceState.idle => _StatusConfig(
        title:       'Ready',
        subtitle:    'Press the microphone button to begin.',
        icon:        Icons.sensors,
        iconColor:   const Color(0xFF00C9A7),
        bgColor:     const Color(0xFF00C9A7).withOpacity(0.08),
        borderColor: const Color(0xFF00C9A7).withOpacity(0.25),
      ),
      AttendanceState.recording => _StatusConfig(
        title:       'Recording…',
        subtitle:    'Speak clearly. Press stop when finished.',
        icon:        Icons.fiber_manual_record,
        iconColor:   Colors.redAccent,
        bgColor:     Colors.redAccent.withOpacity(0.08),
        borderColor: Colors.redAccent.withOpacity(0.3),
      ),
      AttendanceState.processing => _StatusConfig(
        title:       'Analysing Voice',
        subtitle:    'Sending audio to AI for recognition…',
        icon:        Icons.auto_awesome,
        iconColor:   Colors.amberAccent,
        bgColor:     Colors.amberAccent.withOpacity(0.08),
        borderColor: Colors.amberAccent.withOpacity(0.3),
      ),
      AttendanceState.success => _StatusConfig(
        title:       'Attendance Marked ✓',
        subtitle:    'Recognition successful.',
        icon:        Icons.check_circle_outline,
        iconColor:   const Color(0xFF00C9A7),
        bgColor:     const Color(0xFF00C9A7).withOpacity(0.10),
        borderColor: const Color(0xFF00C9A7).withOpacity(0.4),
      ),
      AttendanceState.error => _StatusConfig(
        title:       'Error',
        subtitle:    'Something went wrong. See details below.',
        icon:        Icons.warning_amber_rounded,
        iconColor:   Colors.redAccent,
        bgColor:     Colors.redAccent.withOpacity(0.08),
        borderColor: Colors.redAccent.withOpacity(0.3),
      ),
    };
  }
}

// ---------------------------------------------------------------------------
// Internal config model
// ---------------------------------------------------------------------------

class _StatusConfig {
  final String title;
  final String subtitle;
  final IconData icon;
  final Color iconColor;
  final Color bgColor;
  final Color borderColor;

  const _StatusConfig({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.iconColor,
    required this.bgColor,
    required this.borderColor,
  });
}
