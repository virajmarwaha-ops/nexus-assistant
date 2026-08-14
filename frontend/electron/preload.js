const { contextBridge } = require("electron");

// Expose a minimal, safe surface to the renderer if/when native
// desktop hooks are needed (e.g. global shortcuts, tray icon control).
// Nothing sensitive is exposed here yet.
contextBridge.exposeInMainWorld("nexus", {
  platform: process.platform,
});
