/// VoiceAttend AI – Home Screen
/// ================================
/// The main screen users see on launch.
///
/// Features:
///   • Animated microphone button to start/stop recording
///   • Status cards showing the recognition result
///   • Navigation to the Logs screen
library;

import 'dart:io';
import 'package:flutter/material.dart';
import '../services/audio_recorder_service.dart';
import '../services/attendance_service.dart';
import '../widgets/status_card.dart';
import '../widgets/pulse_button.dart';
import '../widgets/result_card.dart';

/// Possible states of the attendance flow.
enum AttendanceState { idle, recording, processing, success, error }

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen>
    with SingleTickerProviderStateMixin {
  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------

  final AudioRecorderService _recorderService = AudioRecorderService();
  AttendanceState _state = AttendanceState.idle;
  AttendanceResult? _lastResult;
  String _errorMessage = '';

  // -------------------------------------------------------------------------
  // Lifecycle
  // -------------------------------------------------------------------------

  @override
  void dispose() {
    _recorderService.dispose();
    super.dispose();
  }

  // -------------------------------------------------------------------------
  // Recording Logic
  // -------------------------------------------------------------------------

  Future<void> _onMicButtonPressed() async {
    if (_state == AttendanceState.recording) {
      await _stopAndProcess();
    } else if (_state == AttendanceState.idle ||
               _state == AttendanceState.success ||
               _state == AttendanceState.error) {
      await _startRecording();
    }
  }

  Future<void> _startRecording() async {
    final started = await _recorderService.startRecording();
    if (!started) {
      setState(() {
        _state        = AttendanceState.error;
        _errorMessage = 'Microphone permission denied. '
                        'Please grant access in your device settings.';
      });
      return;
    }
    setState(() {
      _state       = AttendanceState.recording;
      _lastResult  = null;
      _errorMessage = '';
    });
  }

  Future<void> _stopAndProcess() async {
    // Stop the recording and get the audio file
    final File? audioFile = await _recorderService.stopRecording();
    if (audioFile == null) {
      setState(() {
        _state        = AttendanceState.error;
        _errorMessage = 'Recording failed – no audio data was captured.';
      });
      return;
    }

    // Show processing spinner while calling the backend
    setState(() => _state = AttendanceState.processing);

    try {
      final result = await AttendanceService.markAttendance(audioFile);
      setState(() {
        _state      = AttendanceState.success;
        _lastResult = result;
      });
    } catch (e) {
      setState(() {
        _state        = AttendanceState.error;
        _errorMessage = e.toString().replaceFirst('Exception: ', '');
      });
    }
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
        title: Row(
          children: [
            Container(
              width: 32, height: 32,
              decoration: BoxDecoration(
                color: const Color(0xFF00C9A7),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(Icons.graphic_eq, color: Colors.black, size: 20),
            ),
            const SizedBox(width: 10),
            const Text(
              'VoiceAttend AI',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w700,
                fontSize: 20,
                letterSpacing: 0.5,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.list_alt, color: Color(0xFF00C9A7)),
            tooltip: 'View Logs',
            onPressed: () => Navigator.pushNamed(context, '/logs'),
          ),
          const SizedBox(width: 8),
        ],
      ),

      // ── Body ──────────────────────────────────────────────────────────────
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Status indicator card
              StatusCard(state: _state),
              const SizedBox(height: 40),

              // ── Microphone Button ────────────────────────────────────────
              Center(
                child: _state == AttendanceState.processing
                    ? _buildProcessingIndicator()
                    : PulseButton(
                        isRecording: _state == AttendanceState.recording,
                        onPressed:   _onMicButtonPressed,
                      ),
              ),
              const SizedBox(height: 16),

              // Helper text below mic button
              Center(
                child: Text(
                  _buttonHintText(),
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.55),
                    fontSize: 13,
                    letterSpacing: 0.3,
                  ),
                ),
              ),
              const SizedBox(height: 40),

              // ── Result / Error Cards ─────────────────────────────────────
              if (_state == AttendanceState.success && _lastResult != null)
                ResultCard(result: _lastResult!),

              if (_state == AttendanceState.error)
                _buildErrorCard(),

              const SizedBox(height: 32),

              // ── Footer Note ──────────────────────────────────────────────
              Center(
                child: Text(
                  'Speak clearly for 3–5 seconds, then tap again to mark.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.35),
                    fontSize: 12,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // -------------------------------------------------------------------------
  // Helper Widgets
  // -------------------------------------------------------------------------

  Widget _buildProcessingIndicator() {
    return const Column(
      children: [
        SizedBox(
          width: 100, height: 100,
          child: CircularProgressIndicator(
            color: Color(0xFF00C9A7),
            strokeWidth: 6,
          ),
        ),
        SizedBox(height: 16),
        Text(
          'Analysing voice…',
          style: TextStyle(color: Color(0xFF00C9A7), fontSize: 14),
        ),
      ],
    );
  }

  Widget _buildErrorCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.red.shade900.withOpacity(0.3),
        border: Border.all(color: Colors.redAccent.withOpacity(0.6)),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: Colors.redAccent, size: 28),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              _errorMessage,
              style: const TextStyle(color: Colors.redAccent, fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }

  String _buttonHintText() {
    return switch (_state) {
      AttendanceState.idle       => 'Tap to start recording',
      AttendanceState.recording  => 'Tap to stop and mark attendance',
      AttendanceState.processing => 'Processing…',
      AttendanceState.success    => 'Tap to record again',
      AttendanceState.error      => 'Tap to try again',
    };
  }
}
