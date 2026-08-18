const { app, BrowserWindow, globalShortcut, Tray, Menu, ipcMain } = require("electron");
const path = require("path");

const isDev = !app.isPackaged;
const ICON_PATH = path.join(__dirname, "assets", "icon.png");
const TRAY_ICON_PATH = path.join(__dirname, "assets", "tray.png");
const SUMMON_SHORTCUT = "CommandOrControl+Shift+Space";

let win = null;
let tray = null;
let isQuitting = false;
let lastVoiceState = "idle";

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 820,
    frame: false,
    alwaysOnTop: true,
    icon: ICON_PATH,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const startUrl = isDev
    ? "http://localhost:5173"
    : `file://${path.join(__dirname, "../dist/index.html")}`;

  win.loadURL(startUrl);

  if (isDev) {
    win.webContents.openDevTools({ mode: "detach" });
  }

  // Closing the window (Alt+F4, taskbar) hides it to the tray instead of
  // quitting — the app only truly exits via the tray's Quit item, since the
  // whole point of the orb is to stay summonable without relaunching.
  win.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      win.hide();
    }
  });

  win.on("focus", updateClickThrough);
  win.on("blur", updateClickThrough);
}

// Click-through so the idle orb never blocks whatever's behind it — but
// only while unfocused, so it doesn't swallow the click you just used to
// focus it. Interactive states (listening/thinking/speaking) always take
// clicks so voice replies and the confirm gate stay reachable.
function updateClickThrough() {
  if (!win) return;
  const shouldIgnore = lastVoiceState === "idle" && !win.isFocused();
  win.setIgnoreMouseEvents(shouldIgnore, { forward: true });
}

function toggleSummon() {
  if (!win) return;
  if (win.isVisible() && win.isFocused()) {
    win.hide();
  } else {
    win.show();
    win.focus();
  }
}

function createTray() {
  tray = new Tray(TRAY_ICON_PATH);
  tray.setToolTip("NEXUS");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Show / Hide NEXUS", click: toggleSummon },
      { type: "separator" },
      {
        label: "Quit",
        click: () => {
          isQuitting = true;
          app.quit();
        },
      },
    ])
  );
  tray.on("click", toggleSummon);
}

app.whenReady().then(() => {
  createWindow();
  createTray();

  globalShortcut.register(SUMMON_SHORTCUT, toggleSummon);

  ipcMain.on("nexus:voice-state", (_event, state) => {
    lastVoiceState = typeof state === "string" ? state : "idle";
    updateClickThrough();
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    } else {
      win.show();
    }
  });
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
