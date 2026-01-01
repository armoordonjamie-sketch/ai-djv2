import { useRef, useCallback, useEffect } from 'react';

/**
 * Professional audio ducking hook with sidechain-style attack/release curves.
 * 
 * Used during voice onboarding to smoothly reduce music volume when the AI agent speaks,
 * creating a natural "radio DJ" effect where music ducks under voice.
 */

export interface DuckingConfig {
  /** Time in ms to fade down when ducking starts (default: 50ms) */
  attackTime: number;
  /** Time in ms to fade up when ducking ends (default: 300ms) */
  releaseTime: number;
  /** Volume level when ducked, 0-1 (default: 0.25 = -12dB) */
  duckLevel: number;
  /** Volume level when not ducked, 0-1 (default: 1.0) */
  fullLevel: number;
}

export interface DuckingControls {
  /** Smoothly duck the audio (agent starts speaking) */
  duck: () => void;
  /** Smoothly release the ducking (agent stops speaking) */
  release: () => void;
  /** Set the ducking state directly */
  setDucked: (ducked: boolean) => void;
  /** Get current ducking state */
  isDucked: () => boolean;
  /** Connect an audio source to the ducking gain node */
  connectSource: (source: AudioNode) => void;
  /** Disconnect all sources */
  disconnect: () => void;
  /** Get the gain node for external connections */
  getGainNode: () => GainNode | null;
  /** Get or create the AudioContext */
  getContext: () => AudioContext | null;
  /** Clean up resources */
  cleanup: () => void;
  /** Start VAD - ducks when user speaks into mic */
  startVAD: (stream: MediaStream) => void;
  /** Stop VAD monitoring */
  stopVAD: () => void;
  /** Set agent speaking state (overrides VAD during agent speech) */
  setAgentSpeaking: (speaking: boolean) => void;
  /** Get agent speaking state */
  isAgentSpeaking: () => boolean;
}

const DEFAULT_CONFIG: DuckingConfig = {
  attackTime: 50,    // Fast duck-down
  releaseTime: 300,  // Slower fade-up for natural feel
  duckLevel: 0.25,   // -12dB when ducked
  fullLevel: 1.0,    // Full volume when not ducked
};

/**
 * Hook for professional audio ducking with smooth attack/release curves.
 * 
 * @param config - Optional ducking configuration
 * @returns Controls for managing audio ducking
 * 
 * @example
 * ```tsx
 * const { duck, release, connectSource, getContext } = useDucking();
 * 
 * // When agent starts speaking
 * useEffect(() => {
 *   if (isSpeaking) duck();
 *   else release();
 * }, [isSpeaking, duck, release]);
 * ```
 */
export function useDucking(config: Partial<DuckingConfig> = {}): DuckingControls {
  const mergedConfig = { ...DEFAULT_CONFIG, ...config };

  const audioContextRef = useRef<AudioContext | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);
  const isDuckedRef = useRef(false);
  const isInitializedRef = useRef(false);

  // VAD (Voice Activity Detection) refs
  const vadAnalyserRef = useRef<AnalyserNode | null>(null);
  const vadSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const vadIntervalRef = useRef<number | null>(null);
  const agentSpeakingRef = useRef(false);
  const userSpeakingRef = useRef(false);
  const vadActiveRef = useRef(false);

  // VAD thresholds
  const VAD_THRESHOLD = 15;  // dB above silence to trigger (adjust as needed)
  const VAD_RELEASE_DELAY = 200;  // ms to wait before releasing after speech stops
  const vadReleaseTimeoutRef = useRef<number | null>(null);

  /**
   * Initialize or get the AudioContext and GainNode.
   * Creates them lazily to comply with browser autoplay policies.
   */
  const ensureInitialized = useCallback(() => {
    if (isInitializedRef.current && audioContextRef.current && gainNodeRef.current) {
      return true;
    }

    try {
      // Create or reuse AudioContext
      if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
        const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
        audioContextRef.current = new AudioContextClass();
      }

      // Resume if suspended (iOS requirement)
      if (audioContextRef.current.state === 'suspended') {
        audioContextRef.current.resume().catch(console.warn);
      }

      // Create gain node if needed
      if (!gainNodeRef.current) {
        gainNodeRef.current = audioContextRef.current.createGain();
        gainNodeRef.current.gain.value = mergedConfig.fullLevel;
        gainNodeRef.current.connect(audioContextRef.current.destination);
      }

      isInitializedRef.current = true;
      return true;
    } catch (error) {
      console.error('[useDucking] Failed to initialize:', error);
      return false;
    }
  }, [mergedConfig.fullLevel]);

  /**
   * Smoothly duck the audio with exponential ramp.
   * Uses exponentialRampToValueAtTime for natural-sounding volume reduction.
   */
  const duck = useCallback(() => {
    if (!ensureInitialized() || !gainNodeRef.current || !audioContextRef.current) return;

    const ctx = audioContextRef.current;
    const gain = gainNodeRef.current.gain;
    const targetTime = ctx.currentTime + mergedConfig.attackTime / 1000;

    // Cancel any scheduled ramps
    gain.cancelScheduledValues(ctx.currentTime);

    // Set current value to avoid jumps
    gain.setValueAtTime(gain.value, ctx.currentTime);

    // Exponential ramp requires non-zero target
    const targetLevel = Math.max(0.001, mergedConfig.duckLevel);
    gain.exponentialRampToValueAtTime(targetLevel, targetTime);

    isDuckedRef.current = true;
    // console.log('[useDucking] Ducking audio over', mergedConfig.attackTime, 'ms');
  }, [ensureInitialized, mergedConfig.attackTime, mergedConfig.duckLevel]);

  /**
   * Smoothly release the ducking with exponential ramp.
   * Longer release time creates a more natural "breathing" effect.
   */
  const release = useCallback(() => {
    if (!ensureInitialized() || !gainNodeRef.current || !audioContextRef.current) return;

    const ctx = audioContextRef.current;
    const gain = gainNodeRef.current.gain;
    const targetTime = ctx.currentTime + mergedConfig.releaseTime / 1000;

    // Cancel any scheduled ramps
    gain.cancelScheduledValues(ctx.currentTime);

    // Set current value to avoid jumps
    gain.setValueAtTime(gain.value, ctx.currentTime);

    // Exponential ramp to full level
    gain.exponentialRampToValueAtTime(mergedConfig.fullLevel, targetTime);

    isDuckedRef.current = false;
    // console.log('[useDucking] Releasing ducking over', mergedConfig.releaseTime, 'ms');
  }, [ensureInitialized, mergedConfig.releaseTime, mergedConfig.fullLevel]);

  /**
   * Set ducking state directly (convenience wrapper).
   */
  const setDucked = useCallback((ducked: boolean) => {
    if (ducked) {
      duck();
    } else {
      release();
    }
  }, [duck, release]);

  /**
   * Check current ducking state.
   */
  const isDucked = useCallback(() => isDuckedRef.current, []);

  /**
   * Connect an audio source node to the ducking gain.
   * The source will be routed through the gain node for volume control.
   */
  const connectSource = useCallback((source: AudioNode) => {
    if (!ensureInitialized() || !gainNodeRef.current) return;

    try {
      source.connect(gainNodeRef.current);
      // console.log('[useDucking] Connected source to ducking gain');
    } catch (error) {
      console.error('[useDucking] Failed to connect source:', error);
    }
  }, [ensureInitialized]);

  /**
   * Disconnect all connections (for cleanup).
   */
  const disconnect = useCallback(() => {
    if (gainNodeRef.current) {
      try {
        gainNodeRef.current.disconnect();
      } catch {
        // Already disconnected
      }
    }
  }, []);

  /**
   * Get the gain node for external routing.
   */
  const getGainNode = useCallback(() => {
    ensureInitialized();
    return gainNodeRef.current;
  }, [ensureInitialized]);

  /**
   * Get or create the AudioContext.
   */
  const getContext = useCallback(() => {
    ensureInitialized();
    return audioContextRef.current;
  }, [ensureInitialized]);

  /**
   * Update ducking state based on VAD and agent speaking state.
   * Only releases if NEITHER agent NOR user is speaking.
   */
  const updateDuckingState = useCallback(() => {
    if (agentSpeakingRef.current || userSpeakingRef.current) {
      if (!isDuckedRef.current) {
        duck();
      }
    } else {
      if (isDuckedRef.current) {
        release();
      }
    }
  }, [duck, release]);

  /**
   * Set agent speaking state - takes priority over VAD.
   */
  const setAgentSpeaking = useCallback((speaking: boolean) => {
    agentSpeakingRef.current = speaking;
    updateDuckingState();
  }, [updateDuckingState]);

  /**
   * Get agent speaking state.
   */
  const isAgentSpeaking = useCallback(() => agentSpeakingRef.current, []);

  /**
   * Start VAD monitoring on a microphone stream.
   * Will duck audio when user speech is detected.
   */
  const startVAD = useCallback((stream: MediaStream) => {
    if (!ensureInitialized() || !audioContextRef.current) {
      console.warn('[useDucking] Cannot start VAD - audio context not initialized');
      return;
    }

    // Stop existing VAD if running
    if (vadIntervalRef.current) {
      clearInterval(vadIntervalRef.current);
    }
    if (vadSourceRef.current) {
      vadSourceRef.current.disconnect();
    }

    const ctx = audioContextRef.current;

    try {
      // Create analyser for VAD
      vadAnalyserRef.current = ctx.createAnalyser();
      vadAnalyserRef.current.fftSize = 256;
      vadAnalyserRef.current.smoothingTimeConstant = 0.5;

      // Connect microphone stream to analyser
      vadSourceRef.current = ctx.createMediaStreamSource(stream);
      vadSourceRef.current.connect(vadAnalyserRef.current);
      // Don't connect analyser to destination - we just want to analyze, not play back

      const dataArray = new Uint8Array(vadAnalyserRef.current.frequencyBinCount);
      vadActiveRef.current = true;

      console.log('[useDucking] VAD started');

      // Check audio level periodically
      vadIntervalRef.current = window.setInterval(() => {
        if (!vadAnalyserRef.current || !vadActiveRef.current) return;

        vadAnalyserRef.current.getByteFrequencyData(dataArray);

        // Calculate average volume (RMS-like)
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i];
        }
        const average = sum / dataArray.length;

        // Check if above threshold (speech detected)
        const isSpeaking = average > VAD_THRESHOLD;

        if (isSpeaking) {
          // Clear any pending release
          if (vadReleaseTimeoutRef.current) {
            clearTimeout(vadReleaseTimeoutRef.current);
            vadReleaseTimeoutRef.current = null;
          }

          if (!userSpeakingRef.current) {
            userSpeakingRef.current = true;
            console.log('[useDucking] User speech detected, ducking');
            updateDuckingState();
          }
        } else {
          // Speech stopped - use delay before releasing
          if (userSpeakingRef.current && !vadReleaseTimeoutRef.current) {
            vadReleaseTimeoutRef.current = window.setTimeout(() => {
              userSpeakingRef.current = false;
              vadReleaseTimeoutRef.current = null;
              console.log('[useDucking] User speech ended, checking release');
              updateDuckingState();
            }, VAD_RELEASE_DELAY);
          }
        }
      }, 50);  // Check every 50ms

    } catch (error) {
      console.error('[useDucking] Failed to start VAD:', error);
    }
  }, [ensureInitialized, updateDuckingState]);

  /**
   * Stop VAD monitoring.
   */
  const stopVAD = useCallback(() => {
    vadActiveRef.current = false;

    if (vadIntervalRef.current) {
      clearInterval(vadIntervalRef.current);
      vadIntervalRef.current = null;
    }

    if (vadReleaseTimeoutRef.current) {
      clearTimeout(vadReleaseTimeoutRef.current);
      vadReleaseTimeoutRef.current = null;
    }

    if (vadSourceRef.current) {
      vadSourceRef.current.disconnect();
      vadSourceRef.current = null;
    }

    if (vadAnalyserRef.current) {
      vadAnalyserRef.current.disconnect();
      vadAnalyserRef.current = null;
    }

    userSpeakingRef.current = false;
    console.log('[useDucking] VAD stopped');
  }, []);

  /**
   * Clean up all resources.
   * NOTE: This should only be called when the component unmounts,
   * NOT during normal operation.
   */
  const cleanup = useCallback(() => {
    // Stop VAD first
    stopVAD();
    console.log('[useDucking] Cleanup called');
    if (gainNodeRef.current) {
      try {
        gainNodeRef.current.disconnect();
      } catch {
        // Already disconnected
      }
      gainNodeRef.current = null;
    }

    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close().catch(console.warn);
      audioContextRef.current = null;
    }

    isInitializedRef.current = false;
    isDuckedRef.current = false;
  }, []);

  // Cleanup on unmount ONLY - use empty deps to prevent re-running
  useEffect(() => {
    return () => {
      console.log('[useDucking] Component unmounting, cleaning up');

      // Stop VAD
      if (vadIntervalRef.current) {
        clearInterval(vadIntervalRef.current);
      }
      if (vadReleaseTimeoutRef.current) {
        clearTimeout(vadReleaseTimeoutRef.current);
      }
      if (vadSourceRef.current) {
        vadSourceRef.current.disconnect();
      }
      if (vadAnalyserRef.current) {
        vadAnalyserRef.current.disconnect();
      }

      // Cleanup audio nodes
      if (gainNodeRef.current) {
        try {
          gainNodeRef.current.disconnect();
        } catch {
          // Already disconnected
        }
        gainNodeRef.current = null;
      }

      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close().catch(console.warn);
        audioContextRef.current = null;
      }

      isInitializedRef.current = false;
      isDuckedRef.current = false;
    };
  }, []); // Empty deps - only run on unmount

  return {
    duck,
    release,
    setDucked,
    isDucked,
    connectSource,
    disconnect,
    getGainNode,
    getContext,
    cleanup,
    startVAD,
    stopVAD,
    setAgentSpeaking,
    isAgentSpeaking,
  };
}

/**
 * Utility to create a ducking-aware audio buffer source.
 * Plays audio through the ducking system.
 */
export async function playAudioWithDucking(
  url: string,
  ducking: DuckingControls,
  onEnded?: () => void
): Promise<AudioBufferSourceNode | null> {
  const ctx = ducking.getContext();
  const gainNode = ducking.getGainNode();

  if (!ctx || !gainNode) {
    console.error('[playAudioWithDucking] Ducking not initialized');
    return null;
  }

  try {
    // Fetch and decode audio
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const arrayBuffer = await response.arrayBuffer();
    const audioBuffer = await ctx.decodeAudioData(arrayBuffer);

    // Create source
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;

    // Connect through ducking gain
    source.connect(gainNode);

    // Handle end
    source.onended = () => {
      onEnded?.();
    };

    // Play
    source.start(0);

    return source;
  } catch (error) {
    console.error('[playAudioWithDucking] Failed:', error);
    return null;
  }
}

export default useDucking;

