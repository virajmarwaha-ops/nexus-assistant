import React from "react";

export type VoiceState = "idle" | "listening" | "thinking" | "speaking";

const STATE_COLOR: Record<VoiceState, string> = {
  idle: "#12b886",
  listening: "#1c7ed6",
  thinking: "#7048e8",
  speaking: "#f08c00",
};

const DISCONNECTED_COLOR = "#3a4a4d";

interface HudOrbProps {
  connected: boolean;
  voiceState: VoiceState;
  size?: number;
}

export default function HudOrb({ connected, voiceState, size = 220 }: HudOrbProps): JSX.Element {
  const color = connected ? STATE_COLOR[voiceState] : DISCONNECTED_COLOR;
  const active = connected && (voiceState === "listening" || voiceState === "thinking");
  const center = size / 2;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ overflow: "visible" }}>
      <circle
        cx={center}
        cy={center}
        r={center - 6}
        fill="none"
        stroke={color}
        strokeOpacity={0.18}
        strokeWidth={1.5}
      />
      <circle
        cx={center}
        cy={center}
        r={center - 22}
        fill="none"
        stroke={color}
        strokeOpacity={connected ? 0.55 : 0.2}
        strokeWidth={2}
        strokeDasharray="6 10"
        style={{
          transformOrigin: "center",
          animation: active ? "hud-spin 4s linear infinite" : undefined,
        }}
      />
      <circle
        cx={center}
        cy={center}
        r={center - 40}
        fill="none"
        stroke={color}
        strokeOpacity={connected ? 0.8 : 0.25}
        strokeWidth={2}
        strokeDasharray="2 6"
        style={{
          transformOrigin: "center",
          animation: active ? "hud-spin 6s linear infinite reverse" : undefined,
        }}
      />
      <circle
        cx={center}
        cy={center}
        r={center - 58}
        fill={color}
        fillOpacity={connected ? 0.25 : 0.1}
        stroke={color}
        strokeWidth={2}
        style={{
          filter: connected ? `drop-shadow(0 0 14px ${color})` : undefined,
          animation: connected ? "hud-pulse 2.2s ease-in-out infinite" : undefined,
        }}
      />
    </svg>
  );
}
