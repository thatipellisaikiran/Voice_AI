import { useCallback, useEffect, useRef, useState } from 'react';

function base64ToArrayBuffer(base64) {
  const binary = atob(base64);
  const len = binary.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

export function useAudioPlayer() {
  const [isPlaying, setIsPlaying] = useState(false);

  const queueRef = useRef([]);
  const audioCtxRef = useRef(null);
  const currentSourceRef = useRef(null);
  const isPlayingRef = useRef(false);

  const getAudioContext = useCallback(async () => {
    if (!audioCtxRef.current || audioCtxRef.current.state === 'closed') {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      audioCtxRef.current = new AudioCtx();
    }
    if (audioCtxRef.current.state === 'suspended') {
      await audioCtxRef.current.resume();
    }
    return audioCtxRef.current;
  }, []);

  const playNext = useCallback(async () => {
    if (queueRef.current.length === 0) {
      isPlayingRef.current = false;
      setIsPlaying(false);
      return;
    }

    const nextBase64 = queueRef.current.shift();
    isPlayingRef.current = true;
    setIsPlaying(true);

    try {
      const ctx = await getAudioContext();
      const bufferCopy = base64ToArrayBuffer(nextBase64);
      const audioBuffer = await ctx.decodeAudioData(bufferCopy);

      if (!isPlayingRef.current) return;

      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);
      currentSourceRef.current = source;

      source.onended = () => {
        if (currentSourceRef.current === source) {
          currentSourceRef.current = null;
        }
        playNext();
      };

      source.start(0);
    } catch {
      currentSourceRef.current = null;
      playNext();
    }
  }, [getAudioContext]);

  const playAudio = useCallback(
    async (base64Mp3) => {
      if (!base64Mp3) return;
      queueRef.current.push(base64Mp3);
      if (!isPlayingRef.current) {
        await playNext();
      }
    },
    [playNext]
  );

  const stopAudio = useCallback(() => {
    queueRef.current = [];
    isPlayingRef.current = false;
    if (currentSourceRef.current) {
      try {
        currentSourceRef.current.onended = null;
        currentSourceRef.current.stop();
        currentSourceRef.current.disconnect();
      } catch {
        // Ignore
      }
      currentSourceRef.current = null;
    }
    setIsPlaying(false);
  }, []);

  useEffect(() => {
    return () => {
      stopAudio();
    };
  }, [stopAudio]);

  return {
    isPlaying,
    playAudio,
    stopAudio,
  };
}
