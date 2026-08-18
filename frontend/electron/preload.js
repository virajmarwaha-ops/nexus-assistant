const { contextBridge, ipcRenderer } = require("electron");

// Expose a minimal, safe surface to the renderer for native desktop hooks
// (global shortcut summon, tray, click-through). No Node/fs/ipcRenderer
// object itself is exposed — only these specific functions.
contextBridge.exposeInMainWorld("nexus", {
  platform: process.platform,
  reportVoiceState: (state) => ipcRenderer.send("nexus:voice-state", state),
});
