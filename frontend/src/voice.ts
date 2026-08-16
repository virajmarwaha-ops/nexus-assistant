// Continuous mic capture, downsampled to 16kHz mono PCM16 and streamed to
// the backend over the same WebSocket used for the connected dot. Capture
// happens here in the renderer rather than in Python — installing mic
// libraries in Python on Windows is famously painful (PyAudio breaks
// constantly), and Electron's Chromium runtime already has this solved.

const TARGET_SAMPLE_RATE = 16000;
const BUFFER_SIZE = 4096;

export class VoiceClient {
  private socket: WebSocket;
  private audioContext: AudioContext | null = null;
  private processor: ScriptProcessorNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private silentGain: GainNode | null = null;
  private stream: MediaStream | null = null;

  constructor(socket: WebSocket) {
    this.socket = socket;
  }

  get isActive(): boolean {
    return this.stream !== null;
  }

  async startMic(): Promise<void> {
    if (this.stream) return;

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });

    this.audioContext = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
    this.source = this.audioContext.createMediaStreamSource(this.stream);
    this.processor = this.audioContext.createScriptProcessor(BUFFER_SIZE, 1, 1);

    // A ScriptProcessorNode only fires while connected into the graph, but we
    // don't want the raw mic input audibly looping back out of the speakers —
    // route it through a silent gain node instead of straight to destination.
    this.silentGain = this.audioContext.createGain();
    this.silentGain.gain.value = 0;

    this.processor.onaudioprocess = (event) => {
      if (this.socket.readyState !== WebSocket.OPEN) return;
      const float32 = event.inputBuffer.getChannelData(0);
      const int16 = new Int16Array(float32.length);
      for (let i = 0; i < float32.length; i++) {
        const clamped = Math.max(-1, Math.min(1, float32[i]));
        int16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      }
      this.socket.send(int16.buffer);
    };

    this.source.connect(this.processor);
    this.processor.connect(this.silentGain);
    this.silentGain.connect(this.audioContext.destination);

    // Chromium creates AudioContexts suspended until explicitly resumed
    // (autoplay policy) — onaudioprocess never fires otherwise.
    if (this.audioContext.state === "suspended") {
      await this.audioContext.resume();
    }
  }

  stopMic(): void {
    this.processor?.disconnect();
    this.source?.disconnect();
    this.silentGain?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    void this.audioContext?.close();

    this.processor = null;
    this.source = null;
    this.silentGain = null;
    this.stream = null;
    this.audioContext = null;
  }

  notifyPlaybackDone(): void {
    if (this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: "playback_done" }));
    }
  }
}

/** Play an <audio> element to completion (caller owns the element so it can pause it on barge-in). */
export function playAudioElement(audio: HTMLAudioElement): Promise<void> {
  return new Promise((resolve, reject) => {
    audio.onended = () => resolve();
    audio.onerror = () => reject(new Error("Audio playback failed"));
    void audio.play().catch(reject);
  });
}

/** Fallback TTS using the browser's built-in voice, for when edge-tts is unavailable. */
export function speakWithBrowserVoice(text: string): Promise<void> {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in window) || !text.trim()) {
      resolve();
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    utterance.onend = () => resolve();
    utterance.onerror = () => resolve();
    window.speechSynthesis.speak(utterance);
  });
}
