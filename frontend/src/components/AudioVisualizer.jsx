import React, { useEffect, useRef } from 'react';

export function AudioVisualizer({ isActive, stream, isSpeaking = false }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d');
    let rafId = null;
    let audioCtx = null;
    let analyser = null;
    let source = null;

    // Support High DPI displays
    const dpr = window.devicePixelRatio || 1;
    const displayWidth = 320;
    const displayHeight = 44;
    canvas.width = displayWidth * dpr;
    canvas.height = displayHeight * dpr;
    ctx.scale(dpr, dpr);

    const BAR_COUNT = 28;
    const barWidth = 3.5;
    const barGap = 6;
    const totalWidth = BAR_COUNT * barWidth + (BAR_COUNT - 1) * barGap;
    const startX = (displayWidth - totalWidth) / 2;

    const renderBars = (amplitudes, colorStart, colorEnd) => {
      ctx.clearRect(0, 0, displayWidth, displayHeight);

      const gradient = ctx.createLinearGradient(0, 0, displayWidth, 0);
      gradient.addColorStop(0, colorStart);
      gradient.addColorStop(1, colorEnd);
      ctx.fillStyle = gradient;

      for (let i = 0; i < BAR_COUNT; i++) {
        const amp = Math.max(0.08, Math.min(1.0, amplitudes[i] || 0.08));
        const barHeight = Math.max(4, amp * (displayHeight - 6));
        const x = startX + i * (barWidth + barGap);
        const y = (displayHeight - barHeight) / 2;

        ctx.beginPath();
        ctx.roundRect(x, y, barWidth, barHeight, barWidth / 2);
        ctx.fill();
      }
    };

    if (isActive && stream) {
      // Live microphone Web Audio AnalyserNode
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        audioCtx = new AudioCtx();
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 64;
        analyser.smoothingTimeConstant = 0.75;
        source = audioCtx.createMediaStreamSource(stream);
        source.connect(analyser);

        const freqData = new Uint8Array(analyser.frequencyBinCount);

        const drawMicWaveform = () => {
          analyser.getByteFrequencyData(freqData);
          const amplitudes = Array.from({ length: BAR_COUNT }, (_, i) => {
            const raw = freqData[i % analyser.frequencyBinCount] || 0;
            return raw / 255;
          });
          // Red glowing active microphone bars
          renderBars(amplitudes, '#DC2626', '#EF4444');
          rafId = requestAnimationFrame(drawMicWaveform);
        };
        drawMicWaveform();
      } catch {
        // Fallback if audio context fails
      }
    } else if (isSpeaking) {
      // Real-time animated AI speaking waveform
      let phase = 0;
      const drawSpeakingWaves = () => {
        phase += 0.14;
        const amplitudes = Array.from({ length: BAR_COUNT }, (_, i) => {
          const wave = Math.sin(phase + i * 0.42) * 0.38 + 0.45;
          const noise = Math.sin(phase * 1.5 + i * 0.8) * 0.12;
          return Math.max(0.12, Math.min(0.95, wave + noise));
        });
        // Blue AI speech waves
        renderBars(amplitudes, '#2563EB', '#60A5FA');
        rafId = requestAnimationFrame(drawSpeakingWaves);
      };
      drawSpeakingWaves();
    } else {
      // Idle ambient baseline
      let idlePhase = 0;
      const drawIdle = () => {
        idlePhase += 0.04;
        const amplitudes = Array.from({ length: BAR_COUNT }, (_, i) => {
          const centerDist = Math.abs(i - BAR_COUNT / 2) / (BAR_COUNT / 2);
          const wave = Math.sin(idlePhase + i * 0.25) * 0.04;
          return Math.max(0.06, (1 - centerDist * 0.6) * 0.16 + wave);
        });
        renderBars(amplitudes, '#94A3B8', '#CBD5E1');
        rafId = requestAnimationFrame(drawIdle);
      };
      drawIdle();
    }

    return () => {
      if (rafId) cancelAnimationFrame(rafId);
      if (source) source.disconnect();
      if (audioCtx) audioCtx.close().catch(() => {});
    };
  }, [isActive, stream, isSpeaking]);

  return (
    <div className="audio-visualizer-container">
      <canvas
        ref={canvasRef}
        className={`audio-visualizer ${isActive ? 'audio-visualizer--recording' : ''} ${
          isSpeaking ? 'audio-visualizer--speaking' : ''
        }`}
        style={{ width: 320, height: 44 }}
        aria-label="Real-time live audio waveform"
      />
    </div>
  );
}
