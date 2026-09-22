/**
 * Layer 2 — Mantis drawer.
 *
 * Mantis used to be a routed tab, so asking about a failing run meant
 * navigating away from it. The drawer overlays whichever view is mounted and
 * keeps one long-lived MantisPanel alive across navigation, so a diagnosis
 * that takes minutes survives a trip to the Devices screen and back.
 *
 * The pull tab is the only affordance that is visible on every view; the
 * drawer itself is off-screen until opened.
 */

import { MantisPanel } from './mantis-panel.js';

export class MantisDrawer {
  constructor(mountEl) {
    if (!mountEl) {
      throw new Error(
        'MantisDrawer requires a mount element: [data-role="mantis-mount"] is missing from index.html.'
      );
    }
    this.mountEl = mountEl;
    this.rootEl = null;
    this.shellEl = null;
    this.tabEl = null;
    this.panel = null;
    this.isOpen = false;
    this.listeners = new AbortController();
  }

  /** Builds the drawer and binds its shortcuts. Safe to call more than once. */
  mount() {
    if (this.rootEl) return;

    this.mountEl.innerHTML = `
      <aside class="mantis-drawer" data-role="drawer" aria-label="Mantis triage assistant">
        <button type="button" class="mantis-pull-tab" data-role="pull-tab"
                aria-controls="mantis-drawer-shell" aria-expanded="false"
                title="Mantis triage (Ctrl+K / Cmd+K)">
          <span class="material-symbols-outlined mantis-pull-tab-icon" aria-hidden="true">neurology</span>
          <span class="mantis-pull-tab-label">MANTIS</span>
        </button>
        <div class="mantis-drawer-shell" id="mantis-drawer-shell" data-role="shell" aria-hidden="true" inert>
          <div class="mantis-drawer-header">
            <span class="material-symbols-outlined" aria-hidden="true">neurology</span>
            <h2 class="mantis-drawer-title">Mantis</h2>
            <span class="mantis-drawer-hint">Ctrl+K</span>
            <button type="button" class="btn-icon" data-act="close" aria-label="Close Mantis drawer">
              <span class="material-symbols-outlined" aria-hidden="true">close</span>
            </button>
          </div>
          <div class="mantis-drawer-body" data-role="panel-mount"></div>
        </div>
      </aside>
    `;

    this.rootEl = this.mountEl.querySelector('[data-role="drawer"]');
    this.shellEl = this.mountEl.querySelector('[data-role="shell"]');
    this.tabEl = this.mountEl.querySelector('[data-role="pull-tab"]');

    this.tabEl.addEventListener('click', () => this.toggle());
    this.mountEl.querySelector('[data-act="close"]').addEventListener('click', () => this.close());

    window.addEventListener('keydown', (event) => this._onKeydown(event), {
      signal: this.listeners.signal,
    });

    this.panel = new MantisPanel(this.mountEl.querySelector('[data-role="panel-mount"]'));
    this.panel.init();
  }

  open() {
    if (this.isOpen) return;
    // Local Test Setup shares this edge; the shell decides who gets it.
    window.workbenchApp?.claimRightEdge?.(this);
    this.isOpen = true;
    this.rootEl.classList.add('is-open');
    this.shellEl.removeAttribute('inert');
    this.shellEl.setAttribute('aria-hidden', 'false');
    this.tabEl.setAttribute('aria-expanded', 'true');
    this.panel.focusComposer();
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    // Focus has to leave before the shell goes inert, otherwise the document
    // is left with no focused element and keyboard navigation restarts at the
    // top of the page.
    if (this.shellEl.contains(document.activeElement)) {
      this.tabEl.focus();
    }
    this.rootEl.classList.remove('is-open');
    this.shellEl.setAttribute('inert', '');
    this.shellEl.setAttribute('aria-hidden', 'true');
    this.tabEl.setAttribute('aria-expanded', 'false');
  }

  toggle() {
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  }

  /**
   * Opens the drawer and starts a triage turn for one failed test. This is the
   * only programmatic entry point; callers do not open the drawer and then
   * poke the panel separately.
   */
  openTriage({ siteModel, deviceId, testId }) {
    this.open();
    this.panel.runTriage({ siteModel, deviceId, testId });
  }

  _onKeydown(event) {
    if ((event.metaKey || event.ctrlKey) && (event.key === 'k' || event.key === 'K')) {
      const active = document.activeElement;
      const typing =
        active &&
        (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.isContentEditable);
      // Ctrl+K inside someone else's field belongs to that field, not to us.
      if (typing && !this.rootEl.contains(active)) return;
      event.preventDefault();
      this.toggle();
      return;
    }

    // Escape closes the drawer only while focus is inside it, so it never
    // steals the key from a dialog or a field on the view underneath.
    if (event.key === 'Escape' && this.isOpen && this.rootEl.contains(event.target)) {
      this.close();
    }
  }
}
