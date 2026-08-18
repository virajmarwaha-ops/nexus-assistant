import React from "react";
import { ChecklistItem } from "./api";

interface Props {
  items: ChecklistItem[];
  onRecheck: () => void;
  onContinueAnyway: () => void;
  checking: boolean;
}

export default function ChecklistScreen({ items, onRecheck, onContinueAnyway, checking }: Props): JSX.Element {
  const allOk = items.every((item) => item.ok);

  return (
    <div className="hud-root" style={{ alignItems: "center", justifyContent: "center" }}>
      <div className="hud-corner-frame" />
      <div className="hud-panel" style={{ width: 560, maxWidth: "90%" }}>
        <div className="hud-panel-title">First-run checklist</div>
        <div style={{ marginBottom: 16, color: "var(--hud-text-dim)" }}>
          Something in setup looks incomplete — here's exactly what's missing.
        </div>

        {items.map((item) => (
          <div key={item.id} style={{ display: "flex", gap: 10, alignItems: "flex-start", marginBottom: 14 }}>
            <span
              style={{
                flexShrink: 0,
                width: 18,
                textAlign: "center",
                color: item.ok ? "var(--hud-idle)" : "var(--hud-red)",
                fontWeight: "bold",
              }}
            >
              {item.ok ? "✓" : "✗"}
            </span>
            <div>
              <div>{item.label}</div>
              {!item.ok && (
                <div style={{ color: "var(--hud-text-dim)", fontSize: 13, marginTop: 2 }}>{item.hint}</div>
              )}
            </div>
          </div>
        ))}

        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button className="hud-button" onClick={onRecheck} disabled={checking}>
            {checking ? "Checking..." : "Recheck"}
          </button>
          {!allOk && (
            <button className="hud-button hud-button-danger" onClick={onContinueAnyway}>
              Continue anyway
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
