/**
 * Layer 1 — Local Test Setup Drawer & Topology Visualizer.
 *
 * Provides a collapsible slide-out drawer on the right side of the Sequencer tab.
 * Allows test operators to:
 *   1. Start / stop / restart the local test substrate (Mosquitto, UDMIS, etcd)
 *      in unprivileged isolated user-space mode (//mqtt/localhost:18833).
 *   2. View an interactive topology graph with real-time component health.
 *   3. Launch / stop simulated Pubber instances for the active device.
 *   4. Inspect live component logs (Setup, UDMIS, Mosquitto, Pubber).
 */

import { attachResizer, clampSize } from './resizer.js';

/** Below this the topology cards and the four log tabs start wrapping illegibly. */
const DRAWER_MIN_WIDTH_PX = 320;
/** Widest useful drawer; past this the service logs are mostly whitespace. */
const DRAWER_MAX_WIDTH_PX = 900;
/** Workspace width the drawer must always leave behind, so it can never cover the app. */
const WORKSPACE_FLOOR_PX = 360;
/**
 * Spec used only when the operator has not entered one. Matches the unprivileged
 * user-space default documented in `etc/shell_common.sh`. An operator-supplied
 * spec is never overridden by this.
 */
const DEFAULT_PROJECT_SPEC = '//mqtt/localhost:18833';

export class LocalSetupDrawer {
  constructor(container, { store, api, onNotify }) {
    this.container = container;
    this.store = store;
    this.api = api;
    this.onNotify = onNotify || (() => {});

    this.activeLogComponent = 'setup';
    this.pollInterval = null;
    this.logInterval = null;
    this.isOpen = false;

    this._build();
    this._bindEvents();
    this._mountResizer();
    this.unsubscribe = this.store.subscribe(() => this.render());
    this.startPolling();
  }

  _build() {
    this.container.innerHTML = `
      <aside class="local-setup-drawer" id="local-setup-drawer" aria-label="Local Test Setup Drawer">
        <div class="resize-handle resize-handle-x" id="local-setup-drawer-resizer"></div>

        <!-- Drawer Header -->
        <div class="drawer-header">
          <div class="drawer-title-group">
            <span class="material-symbols-outlined drawer-title-icon">account_tree</span>
            <div class="drawer-title-text">
              <h3 class="drawer-title">Local Test Setup</h3>
              <div class="drawer-subtitle">
                <span class="status-dot dot-down" id="drawer-header-dot"></span>
                <span id="drawer-header-status-text">DOWN</span>
              </div>
            </div>
          </div>
          <button type="button" class="btn-icon" id="btn-close-testbed-drawer" title="Close Drawer (Cmd+Shift+L)">
            <span class="material-symbols-outlined">close</span>
          </button>
        </div>

        <!-- Action Bar -->
        <div class="drawer-toolbar">
          <button type="button" class="btn btn-sm btn-primary" id="btn-testbed-start" title="Start local substrate (Mosquitto, UDMIS, etcd)">
            <span class="material-symbols-outlined">play_arrow</span>
            <span>Start Setup</span>
          </button>
          <button type="button" class="btn btn-sm btn-outlined btn-danger" id="btn-testbed-stop" title="Stop all local substrate services">
            <span class="material-symbols-outlined">stop</span>
            <span>Stop</span>
          </button>
          <button type="button" class="btn btn-sm btn-outlined" id="btn-testbed-restart" title="Clean restart of local substrate">
            <span class="material-symbols-outlined">refresh</span>
            <span>Restart</span>
          </button>
        </div>

        <!-- Notification Banner -->
        <div class="drawer-alert" id="drawer-alert" hidden>
          <span class="material-symbols-outlined alert-icon">info</span>
          <span class="alert-text" id="drawer-alert-text"></span>
        </div>

        <!-- Drawer Body -->
        <div class="drawer-body">
          <!-- Topology Section -->
          <div class="drawer-section">
            <div class="section-header">
              <div class="section-title-group">
                <span class="material-symbols-outlined section-icon">schema</span>
                <span class="section-title">Substrate Topology</span>
              </div>
              <span class="target-spec-tag" id="drawer-spec-tag">//mqtt/localhost:18833</span>
            </div>

            <div class="topology-canvas" id="topology-canvas">
              <!-- Rendered Nodes & Flow Connections -->
            </div>
          </div>

          <!-- Component Logs Console -->
          <div class="drawer-section logs-section">
            <div class="section-header">
              <div class="section-title-group">
                <span class="material-symbols-outlined section-icon">terminal</span>
                <span class="section-title">Service Logs</span>
              </div>
              <div class="log-tabs">
                <button type="button" class="log-tab active" data-component="setup">Setup</button>
                <button type="button" class="log-tab" data-component="udmis">UDMIS</button>
                <button type="button" class="log-tab" data-component="mosquitto">Mosquitto</button>
                <button type="button" class="log-tab" data-component="pubber">Pubber</button>
              </div>
            </div>
            <div class="testbed-terminal">
              <pre class="terminal-body" id="testbed-terminal-body">Loading service logs...</pre>
            </div>
          </div>
        </div>
      </aside>
    `;
  }

  _bindEvents() {
    const el = (sel) => this.container.querySelector(sel);

    // Close button
    el('#btn-close-testbed-drawer')?.addEventListener('click', () => {
      this.close();
    });

    // Start setup
    el('#btn-testbed-start')?.addEventListener('click', () => this.handleStart());

    // Stop setup
    el('#btn-testbed-stop')?.addEventListener('click', () => this.handleStop());

    // Restart setup
    el('#btn-testbed-restart')?.addEventListener('click', () => this.handleRestart());

    // Toggle Pubber mode (delegated for inline topology card switch)
    this.container.addEventListener('change', async (e) => {
      if (e.target && e.target.id === 'toggle-pubber-mode') {
        const isPubber = e.target.checked;
        this.store.update('SET_PUBBER_MODE', { pubberMode: isPubber });
        const state = this.store.getState();
        const testbed = state.testbedStatus || {};
        if (testbed.overall === 'UP') {
          if (isPubber && state.deviceId) {
            try {
              this.setAlert(`Launching Pubber emulator for ${state.deviceId}...`);
              await this.api.startPubber({
                siteModel: state.siteModel,
                deviceId: state.deviceId,
                projectSpec: (state.projectSpec || '').trim() || DEFAULT_PROJECT_SPEC,
                serialNo: state.serialNo || '1234',
              });
              this.setAlert(`Pubber emulator running for ${state.deviceId}`);
              this.pollStatus();
              setTimeout(() => this.setAlert(''), 3000);
            } catch (pubErr) {
              this.setAlert(`Failed to launch Pubber: ${pubErr.message}`, true);
            }
          } else if (!isPubber && state.deviceId) {
            try {
              await this.api.stopPubber(state.deviceId);
              this.setAlert('Switched to Physical Hardware mode. Pubber stopped.');
              this.pollStatus();
              setTimeout(() => this.setAlert(''), 3000);
            } catch (stopErr) {
              this.setAlert(`Failed to stop Pubber: ${stopErr.message}`, true);
            }
          }
        }
      }
    });

    // Log component tabs
    this.container.querySelectorAll('.log-tab').forEach((tab) => {
      tab.addEventListener('click', (e) => {
        const comp = e.currentTarget.dataset.component;
        this.activeLogComponent = comp;
        this.container.querySelectorAll('.log-tab').forEach((t) => t.classList.toggle('active', t === e.currentTarget));
        this.fetchLogs();
      });
    });

    // Keyboard shortcut Cmd+Shift+L / Ctrl+Shift+L
    window.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === 'L' || e.key === 'l')) {
        e.preventDefault();
        this.toggle();
      }
    });
  }

  /**
   * Bounds come from the live viewport, never from storage, so a width
   * persisted on a wide monitor cannot reopen as a drawer that buries the
   * workspace on a narrow one.
   */
  _drawerBounds() {
    const fits = Math.min(DRAWER_MAX_WIDTH_PX, window.innerWidth - WORKSPACE_FLOOR_PX);
    return { min: DRAWER_MIN_WIDTH_PX, max: Math.max(DRAWER_MIN_WIDTH_PX, fits) };
  }

  _mountResizer() {
    const { min, max } = this._drawerBounds();
    const width = clampSize(this.store.getState().localSetupDrawerWidth, min, max);
    this._applyDrawerWidth(width);

    this.detachResizer = attachResizer(
      this.container.querySelector('#local-setup-drawer-resizer'),
      {
        axis: 'x',
        // The drawer is pinned to the right edge, so its left edge moving left
        // is what makes it wider.
        direction: -1,
        label: 'Resize Local Test Setup drawer',
        min,
        max,
        value: width,
        onResize: (target) => this._applyDrawerWidth(clampSize(target, min, max)),
        onCommit: (applied) =>
          this.store.update('layout.localSetupDrawerWidth', { localSetupDrawerWidth: applied }),
      }
    );
  }

  _applyDrawerWidth(width) {
    // Written on the document element so the drawer and the workspace offset in
    // components.css stay in lockstep off a single property.
    document.documentElement.style.setProperty(
      '--local-setup-drawer-width',
      `${Math.round(width)}px`
    );
    return width;
  }

  startPolling() {
    if (this.pollInterval) clearInterval(this.pollInterval);
    this.pollStatus();
    // Poll every 3.5s
    this.pollInterval = setInterval(() => this.pollStatus(), 3500);

    // Poll logs every 3s if open
    if (this.logInterval) clearInterval(this.logInterval);
    this.logInterval = setInterval(() => {
      if (this.isOpen) {
        this.fetchLogs();
      }
    }, 3000);
  }

  stopPolling() {
    this.unsubscribe?.();
    if (this.pollInterval) clearInterval(this.pollInterval);
    if (this.logInterval) clearInterval(this.logInterval);
    // This is the drawer's only teardown hook, so the resize listeners go here.
    this.detachResizer?.();
  }

  async pollStatus() {
    try {
      const status = await this.api.getTestbedStatus();
      this.store.update('SET_TESTBED_STATUS', { testbedStatus: status }, { silent: true });
      this.render();
    } catch {
      // Server might be temporarily reloading or unreachable
    }
  }

  async fetchLogs() {
    const term = this.container.querySelector('#testbed-terminal-body');
    if (!term) return;
    try {
      const res = await this.api.getTestbedLogs(this.activeLogComponent, 150);
      term.textContent = res.logs || `(Empty log for ${this.activeLogComponent})`;
    } catch (e) {
      term.textContent = `Error reading ${this.activeLogComponent} logs: ${e.message}`;
    }
  }

  open() {
    if (this.isOpen) return;
    // Mantis shares this edge; the shell decides who gets it.
    window.workbenchApp?.claimRightEdge?.(this);
    this.isOpen = true;
    const drawer = this.container.querySelector('#local-setup-drawer');
    drawer?.classList.add('open');
    localStorage.setItem('udmi_testbed_drawer_open', 'true');
    this.fetchLogs();
    this.pollStatus();
    this.onNotify({ action: 'DRAWER_TOGGLED', isOpen: true });
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    const drawer = this.container.querySelector('#local-setup-drawer');
    drawer?.classList.remove('open');
    localStorage.setItem('udmi_testbed_drawer_open', 'false');
    this.onNotify({ action: 'DRAWER_TOGGLED', isOpen: false });
  }

  toggle() {
    if (this.isOpen) this.close();
    else this.open();
  }

  setAlert(text, isError = false) {
    const alertBox = this.container.querySelector('#drawer-alert');
    const alertText = this.container.querySelector('#drawer-alert-text');
    if (!alertBox || !alertText) return;
    if (!text) {
      alertBox.hidden = true;
      return;
    }
    alertText.textContent = text;
    alertBox.classList.toggle('error', isError);
    alertBox.hidden = false;
  }

  async handleStart() {
    const state = this.store.getState();
    if (!state.siteModel) {
      this.setAlert('Please select a Site Model in the Sequencer controls first.', true);
      return;
    }
    this.setAlert('Launching local testbed substrate (Mosquitto, UDMIS, etcd)...');

    // An explicitly entered spec is the operator's choice of port and must be
    // honoured verbatim -- unprivileged labs deliberately run on ports other
    // than the default. Only a blank field is filled in, and the resolved spec
    // is what gets sent, so the panel and the backend cannot disagree.
    const projectSpec = (state.projectSpec || '').trim() || DEFAULT_PROJECT_SPEC;
    if (projectSpec !== state.projectSpec) {
      this.store.update('SET_PROJECT_SPEC', { projectSpec });
    }

    try {
      await this.api.startTestbed({
        siteModel: state.siteModel,
        projectSpec,
        clean: false,
      });

      // Automatically launch Pubber if in Pubber mode and device is selected
      const isPubberMode = state.pubberMode !== false;
      if (isPubberMode && state.deviceId) {
        this.setAlert(`Substrate started. Launching Pubber for device ${state.deviceId}...`);
        try {
          await this.api.startPubber({
            siteModel: state.siteModel,
            deviceId: state.deviceId,
            projectSpec,
            serialNo: state.serialNo || '1234',
          });
          this.setAlert(`Local substrate and Pubber emulator (${state.deviceId}) started!`);
        } catch (pubErr) {
          this.setAlert(`Substrate started, but Pubber launch failed: ${pubErr.message}`, true);
        }
      } else if (isPubberMode && !state.deviceId) {
        this.setAlert('Local substrate running. Select a device in Sequencer to launch Pubber.');
      } else {
        this.setAlert('Local substrate running (Physical Device mode).');
      }

      this.activeLogComponent = 'setup';
      this.fetchLogs();
      this.pollStatus();
      setTimeout(() => this.setAlert(''), 5000);
    } catch (e) {
      this.setAlert(`Startup failed: ${e.message}`, true);
    }
  }

  async handleStop() {
    this.setAlert('Stopping local services and Pubber...');
    try {
      await this.api.stopTestbed();
      this.pollStatus();
      setTimeout(() => this.setAlert(''), 3000);
    } catch (e) {
      this.setAlert(`Stop failed: ${e.message}`, true);
    }
  }

  async handleRestart() {
    const state = this.store.getState();
    if (!state.siteModel) {
      this.setAlert('Please select a Site Model in the Sequencer controls first.', true);
      return;
    }
    this.setAlert('Executing clean restart of local testbed substrate...');
    const projectSpec = (state.projectSpec || '').trim() || DEFAULT_PROJECT_SPEC;
    try {
      await this.api.restartTestbed({
        siteModel: state.siteModel,
        projectSpec,
      });

      const isPubberMode = state.pubberMode !== false;
      if (isPubberMode && state.deviceId) {
        this.setAlert(`Substrate restarted. Launching Pubber for ${state.deviceId}...`);
        try {
          await this.api.startPubber({
            siteModel: state.siteModel,
            deviceId: state.deviceId,
            projectSpec,
            serialNo: state.serialNo || '1234',
          });
          this.setAlert(`Local substrate and Pubber (${state.deviceId}) restarted!`);
        } catch (pubErr) {
          this.setAlert(`Substrate restarted, but Pubber launch failed: ${pubErr.message}`, true);
        }
      }

      this.pollStatus();
      setTimeout(() => this.setAlert(''), 5000);
    } catch (e) {
      this.setAlert(`Restart failed: ${e.message}`, true);
    }
  }

  render() {
    const state = this.store.getState();
    const testbed = state.testbedStatus || {};
    const overall = testbed.overall || 'DOWN';
    const components = testbed.components || {};

    // Header Status
    const dot = this.container.querySelector('#drawer-header-dot');
    const statusText = this.container.querySelector('#drawer-header-status-text');
    if (dot && statusText) {
      dot.className = `status-dot dot-${overall.toLowerCase()}`;
      statusText.textContent = overall;
    }

    // Spec tag
    const specTag = this.container.querySelector('#drawer-spec-tag');
    if (specTag) {
      specTag.textContent = state.projectSpec || testbed.project_spec || DEFAULT_PROJECT_SPEC;
    }

    // Render Topology Canvas
    this.renderTopology(state, components);
  }

  renderTopology(state, components) {
    const canvas = this.container.querySelector('#topology-canvas');
    if (!canvas) return;

    const dutDev = state.deviceId || '(No Device)';
    const isPubber = state.pubberMode !== false;
    const pubberComp = components.pubber || {};
    const mqttComp = components.mqtt_broker || { status: 'DOWN', port: 18833 };
    const udmisComp = components.udmis || { status: 'DOWN' };
    const etcdComp = components.etcd || { status: 'DOWN', port: 2379 };

    const getBadge = (status) => {
      const s = (status || 'DOWN').toUpperCase();
      const cls = s === 'UP' ? 'badge-up' : s === 'INITIALIZING' ? 'badge-init' : s === 'ERROR' ? 'badge-error' : 'badge-down';
      return `<span class="health-badge ${cls}">${s === 'INITIALIZING' ? '<span class="spinner-inline"></span>' : ''}${s}</span>`;
    };

    const dutSubtitle = isPubber
      ? (pubberComp.status === 'UP' ? `Pubber Emulator (PID: ${pubberComp.pid || 'Active'})` : 'Pubber Emulator (Auto-start)')
      : 'Physical Hardware (External Target)';

    const dutBadge = isPubber
      ? getBadge(pubberComp.status)
      : '<span class="health-badge badge-up">CONNECTED</span>';

    canvas.innerHTML = `
      <div class="topology-stack">
        <!-- Node 1: DUT / Device with inline Pubber toggle -->
        <div class="topology-card ${state.deviceId ? 'active-device' : 'empty-device'}">
          <div class="node-icon-box">
            <span class="material-symbols-outlined">${isPubber ? 'smart_toy' : 'home_iot_device'}</span>
          </div>
          <div class="node-info">
            <div class="node-title">${dutDev}</div>
            <div class="node-subtitle">${dutSubtitle}</div>
          </div>
          <div class="node-controls-group">
            <div class="pubber-switch-container" title="Toggle Pubber Simulation vs Physical Hardware">
              <label class="m3-switch" title="Toggle Pubber simulation">
                <input type="checkbox" id="toggle-pubber-mode" ${isPubber ? 'checked' : ''} />
                <span class="m3-switch-track">
                  <span class="m3-switch-thumb"></span>
                </span>
              </label>
              <span class="mode-text-sm" id="pubber-mode-text">${isPubber ? 'Pubber' : 'Physical'}</span>
            </div>
            <div class="node-status">
              ${dutBadge}
            </div>
          </div>
        </div>

        <!-- Connection 1 -->
        <div class="topology-flow-edge">
          <div class="flow-line"></div>
          <span class="flow-pill">MQTT :${mqttComp.port || 18833} (Telemetry & State)</span>
          <span class="flow-arrow">▼</span>
        </div>

        <!-- Node 2: Mosquitto Broker -->
        <div class="topology-card">
          <div class="node-icon-box">
            <span class="material-symbols-outlined">cell_tower</span>
          </div>
          <div class="node-info">
            <div class="node-title">Local Mosquitto</div>
            <div class="node-subtitle">Port ${mqttComp.port || 18833} (Isolated User Mode)</div>
          </div>
          <div class="node-status">
            ${getBadge(mqttComp.status)}
          </div>
        </div>

        <!-- Connection 2 -->
        <div class="topology-flow-edge">
          <div class="flow-line"></div>
          <span class="flow-pill">Reflective Message Sync</span>
          <span class="flow-arrow">▼</span>
        </div>

        <!-- Node 3: UDMIS Pod -->
        <div class="topology-card">
          <div class="node-icon-box">
            <span class="material-symbols-outlined">dns</span>
          </div>
          <div class="node-info">
            <div class="node-title">Local UDMIS Pod</div>
            <div class="node-subtitle">Message Ingest & Schema Validation</div>
          </div>
          <div class="node-status">
            ${getBadge(udmisComp.status)}
          </div>
        </div>

        <!-- Connection 3 -->
        <div class="topology-flow-edge">
          <div class="flow-line"></div>
          <span class="flow-pill">KV Device State & Metadata</span>
          <span class="flow-arrow">▼</span>
        </div>

        <!-- Node 4: etcd State Store -->
        <div class="topology-card">
          <div class="node-icon-box">
            <span class="material-symbols-outlined">database</span>
          </div>
          <div class="node-info">
            <div class="node-title">etcd State Store</div>
            <div class="node-subtitle">Port ${etcdComp.port || 2379}</div>
          </div>
          <div class="node-status">
            ${getBadge(etcdComp.status)}
          </div>
        </div>
      </div>
    `;
  }
}
