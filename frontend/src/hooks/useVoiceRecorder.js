import { useCallback, useEffect, useRef, useState } from 'react';

function pickSupportedMimeType() {
  if (typeof MediaRecorder === 'undefined') return '';
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
  ];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || '';
}

export function useVoiceRecorder({
  silenceThreshold = 12,
  silenceDurationMs = 380,
  onSpeechDetected = null,
} = {}) {
  const [isRecording, setIsRecording] = useState(false);
  const [isAlwaysListening, setIsAlwaysListening] = useState(true);
  const [audioBlob, setAudioBlob] = useState(null);
  const [mediaStream, setMediaStream] = useState(null);
  const [error, setError] = useState(null);

  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const chunksRef = useRef([]);
  const vadIntervalRef = useRef(null);
  const isStoppingRef = useRef(false);
  const speechDetectedRef = useRef(false);
  const silenceCounterRef = useRef(0);
  const activeRecordingRef = useRef(false);
  const onSpeechDetectedRef = useRef(onSpeechDetected);
  onSpeechDetectedRef.current = onSpeechDetected;

  const cleanupAudioContext = useCallback(() => {
    if (vadIntervalRef.current) {
      clearInterval(vadIntervalRef.current);
      vadIntervalRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    setMediaStream(null);
  }, []);

  const stopRecording = useCallback(() => {
    if (isStoppingRef.current || !activeRecordingRef.current) return;
    isStoppingRef.current = true;

    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      try {
        if (recorder.state === 'recording') {
          recorder.requestData();
        }
      } catch {
        // Ignore
      }
      recorder.stop();
    } else {
      activeRecordingRef.current = false;
      setIsRecording(false);
      isStoppingRef.current = false;
    }
  }, []);

  const startActualRecording = useCallback((stream) => {
    if (activeRecordingRef.current) return;
    activeRecordingRef.current = true;
    setIsRecording(true);
    chunksRef.current = [];
    speechDetectedRef.current = true;
    silenceCounterRef.current = 0;
    isStoppingRef.current = false;

    // Trigger barge-in callback
    onSpeechDetectedRef.current?.();

    const mimeType = pickSupportedMimeType();
    const recorderOptions = { audioBitsPerSecond: 128000 };
    if (mimeType) {
      recorderOptions.mimeType = mimeType;
    }

    try {
      const recorder = new MediaRecorder(stream, recorderOptions);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const blobType = mimeType || 'audio/webm';
        const blob = new Blob(chunksRef.current, { type: blobType });
        if (blob.size >= 400) {
          setAudioBlob(blob);
        }
        chunksRef.current = [];
        activeRecordingRef.current = false;
        setIsRecording(false);
        isStoppingRef.current = false;
        speechDetectedRef.current = false;
      };

      recorder.onerror = () => {
        activeRecordingRef.current = false;
        setIsRecording(false);
        isStoppingRef.current = false;
      };

      recorder.start(100);
    } catch (err) {
      activeRecordingRef.current = false;
      setIsRecording(false);
    }
  }, []);

  // Initialize Microphone with Echo Cancellation
  const initMicrophone = useCallback(async () => {
    if (streamRef.current && audioCtxRef.current) {
      return streamRef.current;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      const msg = 'Microphone capture is not supported in this browser.';
      setError(msg);
      throw new Error(msg);
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      streamRef.current = stream;
      setMediaStream(stream);

      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const audioCtx = new AudioCtx();
      if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
      }
      audioCtxRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.5;
      source.connect(analyser);
      analyserRef.current = analyser;

      return stream;
    } catch (err) {
      setError(err?.message || 'Microphone access denied.');
      throw err;
    }
  }, []);

  // VAD Loop: monitors mic levels in real-time
  useEffect(() => {
    let cancelled = false;

    if (!isAlwaysListening) {
      if (vadIntervalRef.current) {
        clearInterval(vadIntervalRef.current);
        vadIntervalRef.current = null;
      }
      if (activeRecordingRef.current) {
        stopRecording();
      }
      return undefined;
    }

    initMicrophone()
      .then((stream) => {
        if (cancelled) return;
        const analyser = analyserRef.current;
        if (!analyser) return;

        const freqData = new Uint8Array(analyser.frequencyBinCount);
        const maxSilenceTicks = Math.max(3, Math.round(silenceDurationMs / 100)); // ~350-380ms

        vadIntervalRef.current = setInterval(() => {
          analyser.getByteFrequencyData(freqData);

          // Compute average human speech band energy (bins 1 to 28)
          let sum = 0;
          const bins = Math.min(28, analyser.frequencyBinCount);
          for (let i = 1; i < bins; i++) {
            sum += freqData[i];
          }
          const energy = sum / (bins - 1);

          if (energy >= silenceThreshold) {
            // Speech detected!
            silenceCounterRef.current = 0;
            if (!activeRecordingRef.current && !isStoppingRef.current) {
              startActualRecording(stream);
            }
          } else if (activeRecordingRef.current) {
            // User was speaking, now silent
            silenceCounterRef.current += 1;
            if (silenceCounterRef.current >= maxSilenceTicks) {
              stopRecording();
            }
          }
        }, 100);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
      if (vadIntervalRef.current) {
        clearInterval(vadIntervalRef.current);
        vadIntervalRef.current = null;
      }
    };
  }, [initMicrophone, isAlwaysListening, silenceDurationMs, silenceThreshold, startActualRecording, stopRecording]);

  const clearAudioBlob = useCallback(() => {
    setAudioBlob(null);
  }, []);

  const toggleAlwaysListening = useCallback(async () => {
    if (isAlwaysListening) {
      setIsAlwaysListening(false);
      stopRecording();
    } else {
      setError(null);
      setIsAlwaysListening(true);
      await initMicrophone();
    }
  }, [initMicrophone, isAlwaysListening, stopRecording]);

  const startRecordingManual = useCallback(async () => {
    const stream = await initMicrophone();
    startActualRecording(stream);
  }, [initMicrophone, startActualRecording]);

  useEffect(() => {
    return () => {
      cleanupAudioContext();
    };
  }, [cleanupAudioContext]);

  return {
    isRecording,
    isAlwaysListening,
    toggleAlwaysListening,
    startRecording: startRecordingManual,
    stopRecording,
    audioBlob,
    clearAudioBlob,
    mediaStream,
    error,
  };
}
