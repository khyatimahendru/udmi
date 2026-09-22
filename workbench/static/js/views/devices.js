/**
 * Layer 2 — Device compliance view.
 *
 * Shows what the sequencer actually recorded for every device in a site model:
 * the per-verdict counts, the reports that exist on disk, and the commit action
 * for a device's results. The previous version of this screen rendered
 * metadata.json and nothing else, which told an operator nothing about whether
 * a device had been tested.
 *
 * Two honesty rules govern the rendering, both of them properties of the
 * backend that the UI must not paper over:
 *
 *   1. `pass + fail + skip` does not equal `total`. Verdicts the sequencer
 *      emits outside those three buckets (`errr` for a run that never reached
 *      the device) are deliberately left unbucketed by compliance.py. The
 *      remainder is displayed as its own quantity; folding it into `fail` would
 *      report a device that was never tested as a device that failed every
 *      sequence, and no percentage is derived from the three buckets alone.
 *   2. Report availability is per file. A device can have a sequencer json with
 *      no results.md, so download controls are driven by the `reports` array
 *      and never by `has_results`.
 */

import { api } from '../core/api.js';
import { store } from '../core/store.js';
import { SiteRootsDialog } from '../components/site-roots.js';
import { CommitDialog, requirePayloadFields } from '../components/commit-dialog.js';

/** The buckets compliance.py tallies. Anything else is the remainder. */
const RESULT_BUCKETS = ['pass', 'fail', 'skip'];

/** Report kind -> the file name it downloads as, for the button label. */
const REPORT_LABELS = {
  results_md: 'results.md',
  result_log: 'RESULT.log',
  sequencer_json: 'sequencer.json',
};

const DEVICE_FIELDS = [
  'device_id',
  'has_results',
  'reason',
  'last_run',
  'udmi_version',
  'status_message',
  'counts',
  'score',
  'sequences',
  'reports',
];

const COUNT_FIELDS = ['pass', 'fail', 'skip', 'total'];

export class DevicesView {
  constructor(root) {
    this.root = root;
    this.siteModels = [];
    this.devices = [];
    this.render();
  }

  render() {
    this.root.innerHTML = `
      <div class="workspace workspace-split">
        <aside class="panel panel-config">
          <h2 class="panel-title">Workspace</h2>
          <div class="field">
            <label class="visually-hidden" for="dev-site-model">Site model</label>
            <select id="dev-site-model" data-role="site"></select>
            <button type="button" class="link-button" data-act="manage-paths">
              Site model somewhere else? Add its path…
            </button>
          </div>
          <p class="site-facts" data-role="facts"></p>
          <h2 class="panel-title">Site rollup</h2>
          <dl class="compliance-totals" data-role="totals"></dl>
          <p class="field-hint">
            Counts come from <code>out/sequencer_&lt;device&gt;.json</code>. Verdicts outside
            pass, fail and skip are reported separately rather than counted as failures.
          </p>
        </aside>

        <section class="panel">
          <div class="panel-toolbar">
            <h2 class="panel-title">
              Sequencer compliance <span class="count" data-role="count"></span>
            </h2>
          </div>
          <div class="compliance-list" data-role="devices"></div>
        </section>
      </div>
      <div data-mount="site-roots"></div>
    `;

    this.siteSelect = this.root.querySelector('[data-role="site"]');
    this.factsEl = this.root.querySelector('[data-role="facts"]');
    this.totalsEl = this.root.querySelector('[data-role="totals"]');
    this.countEl = this.root.querySelector('[data-role="count"]');
    this.deviceListEl = this.root.querySelector('[data-role="devices"]');

    this.commitDialog = new CommitDialog();

    this.siteRoots = new SiteRootsDialog(this.root.querySelector('[data-mount="site-roots"]'), {
      loadRoots: () => api.listSiteRoots(),
      addRoot: (path) => api.addSiteRoot(path),
      removeRoot: (path) => api.removeSiteRoot(path),
      onChange: () => this.init(),
    });

    this.root
      .querySelector('[data-act="manage-paths"]')
      .addEventListener('click', () => this.siteRoots.open());

    this.siteSelect.addEventListener('change', () => {
      store.update('devices.site', { siteModel: this.siteSelect.value, deviceId: '' });
      this.loadCompliance();
    });
  }

  destroy() {}

  async init() {
    try {
      const { site_models: models, unavailable_roots: unavailable } = await api.listSiteModels();
      this.siteModels = models;
      this._fillSiteSelect(models);

      const { siteModel } = store.getState();
      if (siteModel && models.some((m) => m.path === siteModel)) {
        this.siteSelect.value = siteModel;
      } else {
        this.siteSelect.value = '';
      }
      await this.loadCompliance();

      // A registered path that has gone away is reported, never quietly dropped.
      for (const root of unavailable || []) {
        this.setNotice(`Registered path ${root.path} is unavailable: ${root.reason}`, true);
      }
    } catch (cause) {
      this.setNotice(cause.message, true);
    }
  }

  /** Groups models under the origin they were discovered in. */
  _fillSiteSelect(models) {
    this.siteSelect.textContent = '';
    const blank = document.createElement('option');
    blank.value = '';
    blank.textContent = 'Select a site model…';
    this.siteSelect.appendChild(blank);

    const groups = new Map();
    for (const model of models) {
      const key = model.source === 'repository' ? 'This repository' : model.source;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(model);
    }

    for (const [heading, entries] of groups) {
      const group = document.createElement('optgroup');
      group.label = heading;
      for (const model of entries) {
        const option = document.createElement('option');
        option.value = model.path;
        option.textContent = `${model.name} (${model.device_count})`;
        group.appendChild(option);
      }
      this.siteSelect.appendChild(group);
    }
  }

  async loadCompliance() {
    const siteModel = this.siteSelect.value;
    this.deviceListEl.textContent = '';
    this.totalsEl.textContent = '';

    const model = this.siteModels.find((m) => m.path === siteModel);
    this.factsEl.textContent = model
      ? [
          ...new Set(
            [model.site_name, model.registry_id, model.iot_provider, model.project_id].filter(
              Boolean
            )
          ),
        ].join(' · ')
      : '';

    if (!siteModel) {
      this.countEl.textContent = '';
      this.setNotice('Choose a site model above to see its sequencer compliance.');
      return;
    }

    this.setNotice('Reading recorded sequencer results…');

    try {
      const payload = await api.siteCompliance(siteModel);
      requirePayloadFields(payload, ['site_model', 'devices', 'totals'], 'Compliance response');

      this.devices = payload.devices;
      this.countEl.textContent = `${payload.totals.devices_with_results} of ${payload.totals.devices} with results`;
      this._renderTotals(payload.totals);

      this.deviceListEl.textContent = '';
      if (payload.devices.length === 0) {
        this.setNotice('This site model contains no devices.');
        return;
      }
      for (const device of payload.devices) {
        this.deviceListEl.appendChild(this.deviceRow(siteModel, device));
      }
    } catch (cause) {
      this.setNotice(cause.message, true);
    }
  }

  _renderTotals(totals) {
    requirePayloadFields(
      totals,
      ['devices', 'devices_with_results', ...COUNT_FIELDS],
      'Compliance totals'
    );

    const remainder = this._remainderCount(totals);
    const rows = [
      ['Devices', `${totals.devices_with_results} of ${totals.devices} with results`],
      ['Sequences recorded', String(totals.total)],
      ['Pass', String(totals.pass)],
      ['Fail', String(totals.fail)],
      ['Skip', String(totals.skip)],
      ['Errored / not run', String(remainder)],
    ];

    this.totalsEl.textContent = '';
    for (const [term, value] of rows) {
      const wrapper = document.createElement('div');
      const dt = document.createElement('dt');
      dt.textContent = term;
      const dd = document.createElement('dd');
      dd.textContent = value;
      wrapper.append(dt, dd);
      this.totalsEl.appendChild(wrapper);
    }
  }

  /** Sequences carrying a verdict outside pass/fail/skip. Never negative. */
  _remainderCount(counts) {
    return counts.total - counts.pass - counts.fail - counts.skip;
  }

  /** The distinct raw verdicts making up the unbucketed remainder. */
  _remainderVerdicts(sequences) {
    const verdicts = new Set();
    for (const sequence of sequences) {
      if (!RESULT_BUCKETS.includes(sequence.result)) {
        verdicts.add(sequence.result || '(blank verdict)');
      }
    }
    return [...verdicts].sort();
  }

  deviceRow(siteModel, device) {
    requirePayloadFields(device, DEVICE_FIELDS, 'Compliance device record');
    requirePayloadFields(device.counts, COUNT_FIELDS, `Counts for device ${device.device_id}`);

    const row = document.createElement('article');
    row.className = device.has_results ? 'compliance-row' : 'compliance-row is-untested';
    row.dataset.device = device.device_id;

    const head = document.createElement('header');
    head.className = 'compliance-head';

    const name = document.createElement('h3');
    name.className = 'device-name';
    name.textContent = device.device_id;

    const tags = document.createElement('span');
    tags.className = 'device-tags';
    if (!device.has_results) tags.appendChild(this.tag('not tested', 'warning'));
    if (device.udmi_version) tags.appendChild(this.tag(device.udmi_version, 'neutral'));

    head.append(name, tags);
    row.appendChild(head);

    if (device.has_results) {
      row.append(...this._resultsBody(device));
    } else {
      // The server names the missing artifact; that sentence is the whole
      // answer to "why is this device blank?", so it is shown as written.
      const reason = document.createElement('p');
      reason.className = 'compliance-reason';
      reason.textContent = device.reason;
      row.appendChild(reason);
    }

    row.appendChild(this._actions(siteModel, device));
    return row;
  }

  /** The verdict bar, counts, and run facts for a device that has results. */
  _resultsBody(device) {
    const counts = device.counts;
    const remainder = this._remainderCount(counts);
    const verdicts = this._remainderVerdicts(device.sequences);

    const bar = document.createElement('div');
    bar.className = 'verdict-bar';
    bar.setAttribute('role', 'img');
    bar.setAttribute(
      'aria-label',
      `${counts.total} sequences: ${counts.pass} pass, ${counts.fail} fail, ` +
        `${counts.skip} skip, ${remainder} errored or not run`
    );
    // Segment widths are shares of `total`, which the four quantities do sum
    // to. No pass rate is derived from the three buckets, because they do not
    // account for every recorded sequence.
    for (const [bucket, value] of [
      ['pass', counts.pass],
      ['fail', counts.fail],
      ['skip', counts.skip],
      ['other', remainder],
    ]) {
      if (value <= 0) continue;
      const segment = document.createElement('span');
      segment.className = `verdict-segment verdict-${bucket}`;
      segment.style.width = `${(value / counts.total) * 100}%`;
      bar.appendChild(segment);
    }

    const metrics = document.createElement('dl');
    metrics.className = 'verdict-counts';
    const entries = [
      ['Pass', String(counts.pass), 'pass'],
      ['Fail', String(counts.fail), 'fail'],
      ['Skip', String(counts.skip), 'skip'],
      [
        'Errored / not run',
        verdicts.length > 0 ? `${remainder} (${verdicts.join(', ')})` : String(remainder),
        'other',
      ],
      ['Sequences', String(counts.total), 'total'],
      ['Score', `${device.score.value} / ${device.score.total}`, 'score'],
    ];
    for (const [term, value, tone] of entries) {
      const wrapper = document.createElement('div');
      wrapper.className = `verdict-count verdict-${tone}`;
      const dt = document.createElement('dt');
      dt.textContent = term;
      const dd = document.createElement('dd');
      dd.textContent = value;
      wrapper.append(dt, dd);
      metrics.appendChild(wrapper);
    }

    const facts = document.createElement('p');
    facts.className = 'compliance-facts';
    facts.textContent = [
      device.last_run ? `Last run ${device.last_run}` : 'Run time not recorded',
      device.status_message,
    ]
      .filter(Boolean)
      .join(' · ');

    return [bar, metrics, facts];
  }

  /**
   * Download links for the reports that exist, plus the commit action.
   *
   * Each link is a plain anchor: the server sends the report as an attachment,
   * so the browser's own download machinery names the file and streams it
   * without the report ever being held in memory by the page.
   */
  _actions(siteModel, device) {
    const actions = document.createElement('div');
    actions.className = 'compliance-actions';

    if (device.reports.length === 0) {
      const none = document.createElement('span');
      none.className = 'compliance-no-reports';
      none.textContent = 'No report files on disk';
      actions.appendChild(none);
    }

    for (const kind of device.reports) {
      const label = REPORT_LABELS[kind];
      if (!label) {
        throw new Error(
          `Device ${device.device_id} reports an unknown report kind '${kind}'. ` +
            `Known kinds: ${Object.keys(REPORT_LABELS).join(', ')}.`
        );
      }
      const link = document.createElement('a');
      link.className = 'btn btn-ghost report-link';
      link.href = api.deviceReportUrl(siteModel, device.device_id, kind);
      link.setAttribute('download', '');
      link.textContent = label;
      link.setAttribute('aria-label', `Download ${label} for ${device.device_id}`);
      actions.appendChild(link);
    }

    const commit = document.createElement('button');
    commit.type = 'button';
    commit.className = 'btn btn-primary';
    commit.textContent = 'Commit results…';
    commit.setAttribute('aria-label', `Commit sequencer results for ${device.device_id}`);
    commit.addEventListener('click', () => this.openCommit(siteModel, device.device_id));
    actions.appendChild(commit);

    return actions;
  }

  async openCommit(siteModel, deviceId) {
    store.update('devices.select', { deviceId });
    try {
      const result = await this.commitDialog.open({ siteModel, deviceId });
      // Only a real commit changes what the compliance read would return.
      if (result) await this.loadCompliance();
    } catch (cause) {
      this.setNotice(cause.message, true);
    }
  }

  tag(text, tone) {
    const el = document.createElement('span');
    el.className = `badge badge-${tone}`;
    el.textContent = text;
    return el;
  }

  note(text, isError = false) {
    const el = document.createElement('p');
    el.className = `empty-note ${isError ? 'is-error' : ''}`;
    el.textContent = text;
    return el;
  }

  setNotice(text, isError = false) {
    this.deviceListEl.textContent = '';
    this.deviceListEl.appendChild(this.note(text, isError));
  }
}
