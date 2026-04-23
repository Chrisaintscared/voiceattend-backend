/// VoiceAttend AI – Audio Recorder Service
/// ==========================================
/// Wraps the [record] package to start/stop microphone recording.
/// The recorded file is saved to the app's temporary directory.
library;

import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

class AudioRecorderService {
  // Private singleton instance of the recorder
  final AudioRecorder _recorder = AudioRecorder();

  // Path where the last recording was saved
  String? _outputPath;

  // -------------------------------------------------------------------------
  // Start Recording
  // -------------------------------------------------------------------------

  /// Begin recording from the device microphone.
  ///
  /// Saves audio as a WAV file in the app's temporary directory.
  /// Returns true if recording started successfully.
  Future<bool> startRecording() async {
    // Check / request microphone permission
    final hasPermission = await _recorder.hasPermission();
    if (!hasPermission) return false;

    // Build a unique output path
    final tempDir = await getTemporaryDirectory();
    final timestamp = DateTime.now().millisecondsSinceEpoch;
    _outputPath = '${tempDir.path}/voiceattend_$timestamp.wav';

    // Start recording to WAV at 16 kHz mono (ideal for speech models)
    await _recorder.start(
      const RecordConfig(
        encoder:    AudioEncoder.wav,
        sampleRate: 16000,
        numChannels: 1,
      ),
      path: _outputPath!,
    );

    return true;
  }

  // -------------------------------------------------------------------------
  // Stop Recording
  // -------------------------------------------------------------------------

  /// Stop recording and return the saved audio [File].
  ///
  /// Returns null if no recording was in progress or the file is missing.
  Future<File?> stopRecording() async {
    final path = await _recorder.stop();
    if (path == null) return null;

    final file = File(path);
    return await file.exists() ? file : null;
  }

  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------

  /// Returns true if the recorder is currently active.
  Future<bool> get isRecording => _recorder.isRecording();

  // -------------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------------

  /// Release recorder resources.
  Future<void> dispose() async {
    await _recorder.dispose();
  }
}
