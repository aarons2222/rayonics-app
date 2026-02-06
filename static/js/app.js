// ══════════════════════════════════════════════════════════════════════════
// Rayonics Key Reader — WebSocket Client
// Connects to a local Python server that handles BLE + crypto
// ══════════════════════════════════════════════════════════════════════════

(() => {
  "use strict";

  // ── Elements ───────────────────────────────────────────────────────────
  const $  = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  const wsIndicator  = $("#ws-indicator");
  const wsLabel      = $("#ws-label");
  const bleIndicator = $("#ble-indicator");
  const bleLabel     = $("#ble-label");

  const btnConnectServer = $("#btn-connect-server");
  const btnScan          = $("#btn-scan");
  const btnDisconnect    = $("#btn-disconnect");
  const btnClearLog      = $("#btn-clear-log");
  const chkClear         = $("#chk-clear-events");

  const inServer   = $("#in-server");
  const inSyscode  = $("#in-syscode");
  const inRegcode  = $("#in-regcode");

  const deviceList = $("#device-list");
  const keyInfoDiv = $("#key-info");
  const eventsBody = $("#events-body");
  const eventCount = $("#event-count");
  const logArea    = $("#log-area");

  // ── State ──────────────────────────────────────────────────────────────
  let ws = null;
  let connected = false;   // BLE connected
  let wsConnected = false; // WS connected
  let busy = false;
  let autoReconnect = false;

  // ── URL param overrides ────────────────────────────────────────────────
  const params = new URLSearchParams(location.search);
  if (params.has("server"))  inServer.value  = params.get("server");
  if (params.has("syscode")) inSyscode.value = params.get("syscode");
  if (params.has("regcode")) inRegcode.value = params.get("regcode");

  // Auto-connect when served by the local Python server (same origin)
  if (location.hostname === "localhost" || location.hostname === "127.0.0.1") {
    inServer.value = location.host;
    setTimeout(connectServer, 300);
  }

  // ── WebSocket ──────────────────────────────────────────────────────────

  function connectServer() {
    const host = inServer.value.trim();
    if (!host) { log("Enter a server address", "error"); return; }

    // Validate codes
    const sys = inSyscode.value.trim();
    const reg = inRegcode.value.trim();
    if (!/^[0-9a-fA-F]{8}$/.test(sys)) { log("Syscode must be 8 hex chars", "error"); return; }
    if (!/^[0-9a-fA-F]{8}$/.test(reg)) { log("Regcode must be 8 hex chars", "error"); return; }

    if (ws) {
      autoReconnect = false;
      ws.close();
      ws = null;
    }

    const url = `ws://${host}/ws`;
    log(`Connecting to ${url}…`, "info");
    wsIndicator.className = "indicator connecting";
    wsLabel.textContent = "Connecting…";
    btnConnectServer.disabled = true;

    ws = new WebSocket(url);

    ws.onopen = () => {
      wsConnected = true;
      autoReconnect = true;
      setWS(true);
      btnScan.disabled = false;
      btnConnectServer.textContent = "⚡ Reconnect";
      btnConnectServer.disabled = false;
      log("Connected to server ✓", "success");

      // Send config (syscode/regcode) to server
      send({ action: "set_codes", syscode: sys, regcode: reg });
    };

    ws.onclose = () => {
      const wasConnected = wsConnected;
      wsConnected = false;
      setWS(false);
      setBLE(false, "");
      btnScan.disabled = true;
      btnReadKey.disabled = true;
      btnReadEvents.disabled = true;
      btnDisconnect.disabled = true;
      btnConnectServer.disabled = false;

      if (wasConnected) {
        log("Server connection lost", "warn");
        if (autoReconnect) {
          log("Reconnecting in 3s…", "info");
          setTimeout(connectServer, 3000);
        }
      }
    };

    ws.onerror = () => {
      btnConnectServer.disabled = false;
      if (!wsConnected) {
        log("Could not connect — is the server running?", "error");
        wsIndicator.className = "indicator disconnected";
        wsLabel.textContent = "Server ✗";
      }
    };

    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      handleMessage(msg);
    };
  }

  function send(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  }

  // ── Incoming message router ────────────────────────────────────────────

  function handleMessage(msg) {
    switch (msg.type) {
      case "devices":   onDevices(msg.devices); break;
      case "key_info":  onKeyInfo(msg.data);    break;
      case "events":    onEvents(msg.data);     break;
      case "status":    onStatus(msg);          break;
      case "log":       onLog(msg);             break;
      case "error":     onError(msg);           break;
      default:
        log(`Unknown: ${msg.type}`, "warn");
    }
  }

  // ── Handlers ───────────────────────────────────────────────────────────

  function onDevices(devices) {
    busy = false;
    btnScan.disabled = false;
    btnScan.textContent = "🔍 Scan";
    deviceList.innerHTML = "";

    if (devices.length === 0) {
      deviceList.innerHTML = '<p class="placeholder" style="color:var(--text-dim);font-size:.85rem">No devices found</p>';
      return;
    }

    devices
      .sort((a, b) => (b.rssi || -100) - (a.rssi || -100))
      .forEach((d) => {
        const el = document.createElement("div");
        el.className = "device-item";
        el.innerHTML = `
          <span class="name">${esc(d.name || "Unknown")}</span>
          <span class="addr">${esc(d.address)}</span>
          <span class="rssi">RSSI ${d.rssi} dBm</span>
        `;
        el.addEventListener("click", () => {
          if (busy) return;
          busy = true;
          send({ action: "connect", address: d.address, clear: chkClear.checked });
          bleIndicator.className = "indicator connecting";
          bleLabel.textContent = `Connecting to ${d.name || d.address}…`;
        });
        deviceList.appendChild(el);
      });
  }

  function onKeyInfo(data) {
    busy = false;
    keyInfoDiv.innerHTML = "";

    const fields = [
      ["Key ID",      data.keyId],
      ["Key Type",    `${data.keyTypeName} (0x${(data.keyType || 0).toString(16).toUpperCase().padStart(2, "0")})`],
      ["Group ID",    data.groupId],
      ["Verify Day",  data.verifyDay],
      ["Battery",     batteryHTML(data.power)],
      ["BLE Online",  data.isBleOnline ? "Yes" : "No"],
      ["Version",     `<span class="value version">${esc(data.version || "—")}</span>`],
    ];

    fields.forEach(([label, value]) => {
      const item = document.createElement("div");
      item.className = "info-item";
      item.innerHTML = `<span class="label">${label}</span><span class="value">${value}</span>`;
      keyInfoDiv.appendChild(item);
    });
  }

  function onEvents(events) {
    busy = false;
    eventsBody.innerHTML = "";
    eventCount.textContent = events.length;

    events.forEach((ev, i) => {
      const tr = document.createElement("tr");
      if (ev.error) {
        tr.innerHTML = `<td>${i + 1}</td><td colspan="4" style="color:var(--danger)">${esc(ev.error)}</td>`;
      } else {
        tr.innerHTML = `
          <td>${i + 1}</td>
          <td>${esc(ev.time || "—")}</td>
          <td>${ev.lockId ?? "—"}</td>
          <td>${ev.keyId ?? "—"}</td>
          <td>${esc(ev.eventName || String(ev.event))}</td>
        `;
      }
      eventsBody.appendChild(tr);
    });
  }

  function onStatus(msg) {
    connected = msg.connected;
    setBLE(msg.connected, msg.device || "");

    btnDisconnect.disabled = !msg.connected;

    if (!msg.connected) {
      keyInfoDiv.innerHTML = '<p class="placeholder">Connect to a device to see key info</p>';
      eventsBody.innerHTML = "";
      eventCount.textContent = "";
    }
    busy = false;
  }

  function onLog(msg) {
    log(msg.message, msg.level || "info");
  }

  function onError(msg) {
    busy = false;
    btnScan.disabled = !wsConnected;
    log(msg.message, "error");
  }

  // ── UI helpers ─────────────────────────────────────────────────────────

  function setWS(on) {
    wsIndicator.className = `indicator ${on ? "connected" : "disconnected"}`;
    wsLabel.textContent = on ? "Server ✓" : "Server ✗";
  }

  function setBLE(on, name) {
    bleIndicator.className = `indicator ${on ? "connected" : "disconnected"}`;
    bleLabel.textContent = on ? `🔑 ${name}` : "No device";
  }

  function log(message, level = "info") {
    const line = document.createElement("div");
    line.className = `log-line ${level}`;

    const now = new Date();
    const ts  = now.toLocaleTimeString("en-GB", { hour12: false });
    line.innerHTML = `<span class="log-time">${ts}</span>${esc(message)}`;

    logArea.appendChild(line);
    logArea.scrollTop = logArea.scrollHeight;
  }

  function batteryHTML(pct) {
    if (pct == null || pct === "?") return "—";
    const n = typeof pct === "string" ? parseInt(pct) : pct;
    const cls = n > 50 ? "high" : n > 20 ? "medium" : "low";
    return `
      <span class="battery-bar">
        <span class="bar"><span class="fill ${cls}" style="width:${n}%"></span></span>
        ${n}%
      </span>
    `;
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // ── Button handlers ────────────────────────────────────────────────────

  btnConnectServer.addEventListener("click", () => {
    connectServer();
  });

  btnScan.addEventListener("click", () => {
    if (busy) return;
    busy = true;
    btnScan.disabled = true;
    btnScan.textContent = "Scanning…";
    deviceList.innerHTML = "";
    send({ action: "scan" });
  });

  btnDisconnect.addEventListener("click", () => {
    send({ action: "disconnect" });
  });

  btnClearLog.addEventListener("click", () => {
    logArea.innerHTML = "";
  });

  // Allow Enter in server input to connect
  inServer.addEventListener("keydown", (e) => {
    if (e.key === "Enter") connectServer();
  });

})();
