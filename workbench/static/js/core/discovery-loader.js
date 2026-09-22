/**
 * Layer 2 — Discovery loader.
 *
 * Fetches repository discovery data and folds it into the workspace store.
 * Separating this from the sequencer view keeps "what the repository contains"
 * apart from "what the user is doing with it", and keeps both modules within
 * the single-responsibility and file-size guardrails.
 */

import { api } from './api.js';
import { store } from './store.js';

export class DiscoveryLoader {
  constructor({ onNotice }) {
    this.onNotice = onNotice;
    this.siteModels = [];
  }

  /** Loads the site model list, sequence catalog, and run option whitelists. */
  async loadCatalog() {
    const [models, sequences, options] = await Promise.all([
      api.listSiteModels(),
      api.listSequences(),
      api.sequencerOptions(),
    ]);
    this.siteModels = models.site_models;

    // A registered path that has gone away is reported, never quietly dropped.
    for (const root of models.unavailable_roots || []) {
      this.onNotice(`Registered site model path ${root.path} is unavailable: ${root.reason}`, 'warn');
    }
    return { siteModels: this.siteModels, sequences: sequences.sequences, options };
  }

  /**
   * Confirms a persisted site model still exists. A stale selection is cleared
   * and reported rather than silently retried against a missing directory.
   */
  validateSiteModel(siteModel) {
    if (!siteModel) return false;
    if (this.siteModels.some((model) => model.path === siteModel)) return true;

    this.onNotice(`Saved site model '${siteModel}' no longer exists; select another.`, 'warn');
    store.update('site.invalid', { siteModel: '', deviceId: '' });
    return false;
  }

  /** Loads the device inventory for a site model. Returns [] on failure. */
  async loadDevices(siteModel) {
    if (!siteModel) return [];
    try {
      const { devices } = await api.listDevices(siteModel);
      return devices;
    } catch (cause) {
      this.onNotice(cause.message, 'error');
      return [];
    }
  }

  /**
   * Reloads recorded results for a device.
   *
   * `relabel` exists because this refresh serves two different callers. When
   * the operator picks a different device, the summary should announce that it
   * is showing history. When a run has just finished, the summary is already
   * displaying that run's verdict, and overwriting it with 'Historical runs'
   * silently discards the outcome the operator was waiting for.
   */
  async loadResults(siteModel, deviceId, { relabel = true } = {}) {
    if (!siteModel || !deviceId) return null;
    try {
      const payload = await api.getResults(siteModel, deviceId);
      const currentStatus = store.getState().testStatus || {};
      const update = {
        results: payload.results,
        resultsDirExists: payload.results_dir_exists,
        testStatus: currentStatus,
      };
      if (relabel) {
        update.statusLabel =
          Object.keys(payload.results).length ? 'Historical runs' : 'Idle';
      }
      store.update('results.load', update);

      if (!payload.results_dir_exists) {
        this.onNotice(
          `No previous results on disk for ${deviceId} (${payload.results_dir}). ` +
            'Run a sequence to create them.',
          'notice'
        );
      }
      return payload;
    } catch (cause) {
      this.onNotice(cause.message, 'error');
      return null;
    }
  }

  /**
   * Project spec suggestions, discovered rather than invented: the site's own
   * project_id plus any spec recorded in previous run artifacts.
   */
  projectSpecSuggestions(siteModel, results) {
    const model = this.siteModels.find((candidate) => candidate.path === siteModel);
    const discovered = new Set();
    if (model?.project_id) discovered.add(model.project_id);
    for (const record of Object.values(results || {})) {
      if (record.project_spec) discovered.add(record.project_spec);
    }
    return [...discovered].sort();
  }
}
