/// <reference types="vite/client" />

interface Window {
  nexus?: {
    platform: string;
    reportVoiceState: (state: string) => void;
  };
}
