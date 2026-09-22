/**
 * Layer 1 — Sequence selection list.
 *
 * Rows are built once and then patched in place. v1 rebuilt the entire list
 * with innerHTML on every status change, which reset the search filter, wiped
 * focus, and churned the DOM twice per test. This implementation keeps a node
 * index and only touches the parts that actually changed.
 *
 * Purely presentational: it receives data and emits semantic callbacks.
 */

const STATUS_GLYPH = {
  pass: '\u2713',
  fail: '\u2717',
  skip: '\u2013',
  running: '\u25CF',
  queued: '\u25CB',
  unknown: '\u00B7',
};

const STATUS_LABEL = {
  pass: 'Passed',
  fail: 'Failed',
  skip: 'Skipped',
  running: 'Running',
  queued: 'Queued',
  unknown: 'Not run',
};

export class TestList {
  constructor(container, { onToggle, onOpenArtifacts, onDiagnose = null } = {}) {
    this.container = container;
    this.onToggle = onToggle;
    this.onOpenArtifacts = onOpenArtifacts;
    this.onDiagnose = onDiagnose;
    this.rows = new Map();
    this.sequences = [];
  }

  /** Builds the row set. Called only when the sequence catalog itself changes. */
  setSequences(sequences) {
    this.sequences = sequences;
    this.rows.clear();
    this.container.textContent = '';

    if (sequences.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'empty-note';
      empty.textContent = 'No sequences discovered in the repository catalog.';
      this.container.appendChild(empty);
      return;
    }

    let currentBucket = null;
    const fragment = document.createDocumentFragment();

    for (const sequence of sequences) {
      const bucket = sequence.bucket || 'uncategorised';
      if (bucket !== currentBucket) {
        currentBucket = bucket;
        const header = document.createElement('div');
        header.className = 'bucket-header';
        header.textContent = bucket;
        header.dataset.bucket = bucket;
        fragment.appendChild(header);
      }
      fragment.appendChild(this._buildRow(sequence));
    }
    this.container.appendChild(fragment);
  }

  _buildRow(sequence) {
    const row = document.createElement('div');
    row.className = 'test-row';
    row.dataset.test = sequence.name;
    row.dataset.bucket = sequence.bucket || 'uncategorised';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'test-check';
    checkbox.id = `test-${sequence.name}`;
    checkbox.addEventListener('change', () => this.onToggle(sequence.name, checkbox.checked));

    const label = document.createElement('label');
    label.className = 'test-label';
    label.htmlFor = checkbox.id;

    const nameEl = document.createElement('span');
    nameEl.className = 'test-name';
    nameEl.textContent = sequence.name;

    const stageEl = document.createElement('span');
    stageEl.className = `stage-chip stage-${(sequence.stage || 'unknown').toLowerCase()}`;
    stageEl.textContent = sequence.stage || 'UNKNOWN';

    const title = document.createElement('div');
    title.className = 'test-title-line';
    title.append(nameEl, stageEl);

    const description = document.createElement('div');
    description.className = 'test-desc';
    description.textContent = sequence.description || '';

    const provenance = document.createElement('div');
    provenance.className = 'test-provenance';

    label.append(title, description, provenance);

    const actions = document.createElement('div');
    actions.className = 'test-actions';

    const diagnoseButton = document.createElement('button');
    diagnoseButton.type = 'button';
    diagnoseButton.className = 'btn-diagnose';
    diagnoseButton.textContent = '🔍 Diagnose with Mantis';
    diagnoseButton.title = 'Diagnose test failure with Mantis Assistant';
    diagnoseButton.hidden = true;
    diagnoseButton.addEventListener('click', (event) => {
      event.stopPropagation();
      this.onDiagnose?.(sequence.name);
    });

    const statusButton = document.createElement('button');
    statusButton.type = 'button';
    statusButton.className = 'status-chip status-unknown';
    statusButton.textContent = STATUS_GLYPH.unknown;
    statusButton.title = STATUS_LABEL.unknown;
    statusButton.disabled = true;
    statusButton.addEventListener('click', () => this.onOpenArtifacts(sequence.name));

    actions.append(diagnoseButton, statusButton);
    row.append(checkbox, label, actions);
    this.rows.set(sequence.name, { row, checkbox, statusButton, diagnoseButton, provenance });
    return row;
  }

  /** Patches checkbox state without rebuilding rows. */
  setSelection(selectedTests) {
    const selected = new Set(selectedTests);
    for (const [name, refs] of this.rows) {
      refs.checkbox.checked = selected.has(name);
    }
  }

  setDisabled(disabled) {
    for (const refs of this.rows.values()) {
      refs.checkbox.disabled = disabled;
    }
  }

  /** Patches one row's status glyph and artifact affordance. */
  setStatus(testName, status, recorded = null) {
    const refs = this.rows.get(testName);
    if (!refs) return;

    const resolved = status || 'unknown';
    refs.statusButton.className = `status-chip status-${resolved}`;
    refs.statusButton.textContent = STATUS_GLYPH[resolved] ?? STATUS_GLYPH.unknown;
    refs.statusButton.title = recorded?.artifacts?.length
      ? `${STATUS_LABEL[resolved] ?? 'Unknown'} — view artifacts`
      : STATUS_LABEL[resolved] ?? 'Unknown';
    refs.statusButton.disabled = !recorded?.artifacts?.length;

    if (refs.diagnoseButton) {
      refs.diagnoseButton.hidden = resolved !== 'fail';
    }

    refs.provenance.textContent = '';
    if (recorded?.timestamp) {
      const when = document.createElement('span');
      when.textContent = new Date(recorded.timestamp).toLocaleString();
      refs.provenance.appendChild(when);
    }
    if (recorded?.project_spec) {
      const target = document.createElement('span');
      target.className = 'provenance-target';
      target.textContent = recorded.project_spec;
      refs.provenance.appendChild(target);
    }
  }

  /**
   * Flags a row whose feature stage is below the active minimum stage.
   * Such a sequence is skipped by the runner without reporting any result,
   * so it must be visibly distinct from one that simply has not run yet.
   */
  setStageExcluded(testName, excluded, minStage) {
    const refs = this.rows.get(testName);
    if (!refs) return;

    refs.row.classList.toggle('is-stage-excluded', Boolean(excluded));
    if (excluded) {
      refs.checkbox.title =
        `Below the "${minStage}" minimum stage — this sequence will not run. ` +
        'Adjust the minimum stage filter to include it.';
    } else {
      refs.checkbox.removeAttribute('title');
    }
  }

  /** Scrolls the active test into view so the running row is never off-screen. */
  revealTest(testName) {
    this.rows.get(testName)?.row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  /** Applies search, bucket, and stage filters to row visibility. */
  applyFilters(query, bucket, admittedStages = null, selectedTests = []) {
    const needle = (query || '').trim().toLowerCase();
    const visibleBuckets = new Set();
    const selected = new Set(selectedTests || []);

    for (const sequence of this.sequences) {
      const refs = this.rows.get(sequence.name);
      if (!refs) continue;
      const matchesQuery =
        !needle ||
        sequence.name.toLowerCase().includes(needle) ||
        (sequence.description || '').toLowerCase().includes(needle);
      const matchesBucket = !bucket || (sequence.bucket || 'uncategorised') === bucket;
      const isAdmitted =
        !admittedStages ||
        admittedStages.length === 0 ||
        admittedStages.includes((sequence.stage || 'STABLE').toUpperCase());
      const isSelected = selected.has(sequence.name);
      const matchesStage = isAdmitted || isSelected;

      const visible = matchesQuery && matchesBucket && matchesStage;
      refs.row.hidden = !visible;
      if (visible) visibleBuckets.add(sequence.bucket || 'uncategorised');
    }

    for (const header of this.container.querySelectorAll('.bucket-header')) {
      header.hidden = !visibleBuckets.has(header.dataset.bucket);
    }
    return visibleBuckets.size;
  }

  /** Names of rows currently passing the active filters. */
  visibleTestNames() {
    return this.sequences
      .filter((sequence) => this.rows.get(sequence.name)?.row.hidden === false)
      .map((sequence) => sequence.name);
  }
}
