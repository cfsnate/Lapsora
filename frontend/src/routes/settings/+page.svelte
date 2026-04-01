<script lang="ts">
	import { api } from '$lib/api';
	import { setUse24h } from '$lib/utils';
	import type { NotificationURL, NotificationEventsConfig, HealthConfig, LocationConfig, CaptureGapConfig, Go2rtcConfig, TimeFormatConfig, OIDCConfig, OIDCConfigUpdate, TLSConfig, TLSCertificateInfo } from '$lib/types';
	import CleanupScheduleManager from '$lib/components/CleanupScheduleManager.svelte';

	let urls = $state<NotificationURL[]>([]);
	let events = $state<NotificationEventsConfig>({
		capture_failure: true,
		stream_unhealthy: true,
		stream_recovered: true,
		timelapse_complete: true,
		timelapse_failure: true,
		retention_summary: false,
		low_disk_space: true,
		capture_gap: true,
		recording_started: true,
		recording_stopped: true,
		recording_failed: true,
		clip_export_complete: true,
		clip_export_failed: true,
	});
	let healthConfig = $state<HealthConfig>({
		check_interval_seconds: 300,
		failure_threshold: 3,
		low_disk_threshold_percent: 10
	});
	let locationConfig = $state<LocationConfig>({
		latitude: 0.0,
		longitude: 0.0
	});

	let captureGapConfig = $state<CaptureGapConfig>({ enabled: true });
	let savingCaptureGap = $state(false);

	let go2rtcConfig = $state<Go2rtcConfig>({ url: '' });
	let savingGo2rtc = $state(false);
	let testingGo2rtc = $state(false);
	let go2rtcTestResult = $state<string | null>(null);

	let timeFormatConfig = $state<TimeFormatConfig>({ use_24h: false });
	let savingTimeFormat = $state(false);

	let recordingRetentionDays = $state(14);
	let savingRecordingRetention = $state(false);
	let showDeleteAllRecordings = $state(false);
	let deletingAllRecordings = $state(false);
	let deleteRecordingsResult = $state<string | null>(null);

	// OIDC config state
	let oidcConfig = $state<OIDCConfig | null>(null);
	let oidcForm = $state<OIDCConfigUpdate>({ issuer_url: '', client_id: '', client_secret: '', provider_name: '', groups_claim: 'groups' });
	let savingOIDC = $state(false);
	let oidcSaveResult = $state<{ ok: boolean; message: string } | null>(null);

	// TLS config state
	let tlsConfig = $state<TLSConfig | null>(null);
	let tlsForm = $state({ domain: '', email: '', acme_directory_url: 'https://acme-v02.api.letsencrypt.org/directory', acme_ca_bundle: '', enabled: false });
	let savingTLS = $state(false);
	let tlsSaveResult = $state<{ ok: boolean; message: string } | null>(null);
	let certInfo = $state<TLSCertificateInfo | null>(null);
	let acquiring = $state(false);
	let acquireResult = $state<{ ok: boolean; message: string } | null>(null);

	let loading = $state(true);
	let newLabel = $state('');
	let newUrl = $state('');
	let testingId = $state<number | null>(null);
	let savingEvents = $state(false);
	let savingHealth = $state(false);
	let savingLocation = $state(false);

	$effect(() => {
		Promise.all([api.getNotificationSettings(), api.getHealthConfig(), api.getLocationConfig(), api.getCaptureGapConfig(), api.getGo2rtcConfig(), api.getTimeFormatConfig(), api.getRecordingRetention()])
			.then(([notifSettings, hc, loc, gapCfg, g2rCfg, tfCfg, rrCfg]) => {
				urls = notifSettings.urls;
				events = notifSettings.events;
				healthConfig = hc;
				locationConfig = loc;
				captureGapConfig = gapCfg;
				go2rtcConfig = g2rCfg;
				timeFormatConfig = tfCfg;
				recordingRetentionDays = rrCfg.default_retention_days;
			})
			.finally(() => {
				loading = false;
			});
		api.getOIDCConfig().then((cfg) => {
			oidcConfig = cfg;
			oidcForm = {
				issuer_url: cfg.issuer_url ?? '',
				client_id: '',
				client_secret: '',
				provider_name: cfg.provider_name ?? '',
				groups_claim: cfg.groups_claim ?? 'groups'
			};
		}).catch(() => {
			// OIDC not yet configured
		});
		api.getTLSConfig().then((cfg) => {
			tlsConfig = cfg;
			tlsForm = {
				domain: cfg.domain,
				email: cfg.email,
				acme_directory_url: cfg.acme_directory_url || 'https://acme-v02.api.letsencrypt.org/directory',
				acme_ca_bundle: cfg.acme_ca_bundle || '',
				enabled: cfg.enabled,
			};
			if (cfg.has_certificate) {
				api.getCertificateInfo().then((info) => { certInfo = info; }).catch(() => {});
			}
		}).catch(() => {
			// TLS not loaded — user may not be admin
		});
	});

	async function addUrl() {
		if (!newLabel.trim() || !newUrl.trim()) return;
		const nu = await api.addNotificationURL({ label: newLabel.trim(), url: newUrl.trim() });
		urls = [...urls, nu];
		newLabel = '';
		newUrl = '';
	}

	async function removeUrl(id: number) {
		await api.deleteNotificationURL(id);
		urls = urls.filter((u) => u.id !== id);
	}

	async function toggleUrl(nu: NotificationURL) {
		const updated = await api.updateNotificationURL(nu.id, { enabled: !nu.enabled });
		urls = urls.map((u) => (u.id === updated.id ? updated : u));
	}

	async function testUrl(id: number) {
		testingId = id;
		try {
			const result = await api.testNotificationURL(id);
			alert(result.success ? 'Test notification sent!' : 'Test notification failed.');
		} catch {
			alert('Failed to send test notification.');
		}
		testingId = null;
	}

	async function saveEvents() {
		savingEvents = true;
		try {
			await api.updateNotificationEvents(events);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save event settings');
		} finally {
			savingEvents = false;
		}
	}

	async function saveHealth() {
		savingHealth = true;
		try {
			await api.updateHealthConfig(healthConfig);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save health settings');
		} finally {
			savingHealth = false;
		}
	}

	async function saveLocation() {
		savingLocation = true;
		try {
			await api.updateLocationConfig(locationConfig);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save location');
		} finally {
			savingLocation = false;
		}
	}

	async function saveCaptureGap() {
		savingCaptureGap = true;
		try {
			await api.updateCaptureGapConfig(captureGapConfig);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save capture gap settings');
		} finally {
			savingCaptureGap = false;
		}
	}

	async function saveGo2rtc() {
		savingGo2rtc = true;
		go2rtcTestResult = null;
		try {
			await api.updateGo2rtcConfig(go2rtcConfig);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save go2rtc config');
		} finally {
			savingGo2rtc = false;
		}
	}

	async function testGo2rtc() {
		testingGo2rtc = true;
		go2rtcTestResult = null;
		try {
			const result = await api.testGo2rtcServer(go2rtcConfig);
			go2rtcTestResult = result.success ? 'Connected successfully' : result.message || 'Connection failed';
		} catch (err) {
			go2rtcTestResult = err instanceof Error ? err.message : 'Test failed';
		}
		testingGo2rtc = false;
	}

	async function saveTimeFormat() {
		savingTimeFormat = true;
		try {
			await api.updateTimeFormatConfig(timeFormatConfig);
			setUse24h(timeFormatConfig.use_24h);
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save time format');
		} finally {
			savingTimeFormat = false;
		}
	}

	async function saveRecordingRetention() {
		savingRecordingRetention = true;
		try {
			await api.updateRecordingRetention({ default_retention_days: recordingRetentionDays });
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Failed to save recording retention');
		} finally {
			savingRecordingRetention = false;
		}
	}

	async function confirmDeleteAllRecordings() {
		deletingAllRecordings = true;
		deleteRecordingsResult = null;
		try {
			const result = await api.deleteAllRecordings();
			deleteRecordingsResult = `Deleted ${result.segments_deleted} segments, freed ${(result.bytes_freed / 1024 / 1024).toFixed(1)} MB`;
			showDeleteAllRecordings = false;
		} catch (err) {
			deleteRecordingsResult = `Error: ${err instanceof Error ? err.message : 'Failed to delete recordings'}`;
		} finally {
			deletingAllRecordings = false;
		}
	}

	async function saveOIDCConfig() {
		savingOIDC = true;
		oidcSaveResult = null;
		try {
			const updated = await api.saveOIDCConfig(oidcForm);
			oidcConfig = updated;
			oidcSaveResult = { ok: true, message: 'OIDC configuration saved.' };
		} catch (err) {
			oidcSaveResult = { ok: false, message: err instanceof Error ? err.message : 'Failed to save OIDC configuration.' };
		} finally {
			savingOIDC = false;
		}
	}

	async function saveTLSConfig() {
		savingTLS = true;
		tlsSaveResult = null;
		try {
			const updated = await api.saveTLSConfig(tlsForm);
			tlsConfig = updated;
			tlsSaveResult = { ok: true, message: 'TLS configuration saved.' };
		} catch (err) {
			tlsSaveResult = { ok: false, message: err instanceof Error ? err.message : 'Failed to save TLS configuration.' };
		} finally {
			savingTLS = false;
		}
	}

	async function acquireCert(force = false) {
		acquiring = true;
		acquireResult = null;
		try {
			const result = await api.acquireCertificate(force);
			acquireResult = { ok: result.success, message: result.message };
			// Refresh cert info after acquisition
			try { certInfo = await api.getCertificateInfo(); } catch { /* no cert yet */ }
			// Refresh config to update has_certificate
			try { tlsConfig = await api.getTLSConfig(); } catch { /* ignore */ }
		} catch (err) {
			acquireResult = { ok: false, message: err instanceof Error ? err.message : 'Certificate acquisition failed.' };
		} finally {
			acquiring = false;
		}
	}

	const eventLabels: Record<string, string> = {
		capture_failure: 'Snapshot failure',
		stream_unhealthy: 'Stream unhealthy',
		stream_recovered: 'Stream recovered',
		timelapse_complete: 'Timelapse complete',
		timelapse_failure: 'Timelapse failure',
		retention_summary: 'Retention summary',
		low_disk_space: 'Low disk space',
		capture_gap: 'Snapshot gap',
		recording_started: 'Recording started',
		recording_stopped: 'Recording stopped',
		recording_failed: 'Recording failed',
		clip_export_complete: 'Clip export complete',
		clip_export_failed: 'Clip export failed',
	};
</script>

<svelte:head><title>Settings - Lapsora</title></svelte:head>

<div class="space-y-8">
	<h1 class="text-3xl font-bold text-white">Settings</h1>

	{#if loading}
		<p class="text-gray-400">Loading settings...</p>
	{:else}
		<!-- Display -->
		<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
			<h2 class="mb-4 text-xl font-semibold text-white">Display</h2>
			<label class="mb-4 flex items-center gap-3">
				<input
					type="checkbox"
					bind:checked={timeFormatConfig.use_24h}
					class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600"
				/>
				<span class="text-sm text-gray-200">Use 24-hour time format</span>
			</label>
			<button
				onclick={saveTimeFormat}
				disabled={savingTimeFormat}
				class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
			>
				{savingTimeFormat ? 'Saving...' : 'Save'}
			</button>
		</section>

		<!-- Notification URLs -->
		<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
			<h2 class="mb-4 text-xl font-semibold text-white">Notification URLs</h2>
			<p class="mb-4 text-sm text-gray-400">
				Add Apprise-compatible URLs to receive alerts via Discord, Telegram, email, ntfy, and 100+ services.
			</p>

			{#if urls.length > 0}
				<div class="mb-4 space-y-2">
					{#each urls as nu}
						<div class="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-800/50 p-3">
							<div class="flex items-center gap-3">
								<button
									onclick={() => toggleUrl(nu)}
									class="rounded px-2 py-1 text-xs font-medium transition-colors {nu.enabled ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-400'}"
								>
									{nu.enabled ? 'On' : 'Off'}
								</button>
								<span class="text-sm text-gray-200">{nu.label}</span>
							</div>
							<div class="flex items-center gap-2">
								<button
									onclick={() => testUrl(nu.id)}
									disabled={testingId === nu.id}
									class="rounded bg-blue-900 px-3 py-1 text-xs text-blue-300 transition-colors hover:bg-blue-800 disabled:opacity-50"
								>
									{testingId === nu.id ? 'Testing...' : 'Test'}
								</button>
								<button
									onclick={() => removeUrl(nu.id)}
									class="rounded bg-red-900 px-3 py-1 text-xs text-red-300 transition-colors hover:bg-red-800"
								>
									Delete
								</button>
							</div>
						</div>
					{/each}
				</div>
			{/if}

			<div class="flex gap-2">
				<input
					bind:value={newLabel}
					placeholder="Label (e.g. Discord)"
					class="flex-1 rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none"
				/>
				<input
					bind:value={newUrl}
					placeholder="Apprise URL (e.g. discord://...)"
					class="flex-[2] rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none"
				/>
				<button
					onclick={addUrl}
					class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500"
				>
					Add
				</button>
			</div>
		</section>

		<!-- Event Toggles -->
		<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
			<h2 class="mb-4 text-xl font-semibold text-white">Notification Events</h2>
			<p class="mb-4 text-sm text-gray-400">
				Choose which events trigger external notifications (Apprise). All events always appear in the in-app notification panel.
			</p>

			<div class="mb-4 grid grid-cols-2 gap-3">
				{#each Object.entries(eventLabels) as [key, label]}
					<label class="flex items-center gap-3 rounded-lg border border-gray-800 bg-gray-800/50 p-3">
						<input
							type="checkbox"
							bind:checked={events[key as keyof NotificationEventsConfig]}
							class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600"
						/>
						<span class="text-sm text-gray-200">{label}</span>
					</label>
				{/each}
			</div>

			<button
				onclick={saveEvents}
				disabled={savingEvents}
				class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
			>
				{savingEvents ? 'Saving...' : 'Save Event Settings'}
			</button>
		</section>

		<!-- Health Monitoring -->
		<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
			<h2 class="mb-4 text-xl font-semibold text-white">Health Monitoring</h2>
			<p class="mb-4 text-sm text-gray-400">
				Configure how often streams are checked and when they're marked as unhealthy.
			</p>

			<div class="mb-4 grid grid-cols-3 gap-4">
				<div>
					<label for="check-interval" class="mb-1 block text-sm text-gray-400">Check interval (seconds)</label>
					<input
						id="check-interval"
						type="number"
						min="30"
						bind:value={healthConfig.check_interval_seconds}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none"
					/>
				</div>
				<div>
					<label for="failure-threshold" class="mb-1 block text-sm text-gray-400">Failure threshold</label>
					<input
						id="failure-threshold"
						type="number"
						min="1"
						bind:value={healthConfig.failure_threshold}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none"
					/>
				</div>
				<div>
					<label for="disk-threshold" class="mb-1 block text-sm text-gray-400">Low disk threshold (%)</label>
					<input
						id="disk-threshold"
						type="number"
						min="1"
						max="50"
						bind:value={healthConfig.low_disk_threshold_percent}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none"
					/>
				</div>
			</div>

			<button
				onclick={saveHealth}
				disabled={savingHealth}
				class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
			>
				{savingHealth ? 'Saving...' : 'Save Health Settings'}
			</button>
		</section>
		<!-- Location -->
		<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
			<h2 class="mb-4 text-xl font-semibold text-white">Location</h2>
			<p class="mb-4 text-sm text-gray-400">
				Used for sunrise/sunset capture scheduling. Set your camera site's coordinates.
			</p>

			<div class="mb-4 grid grid-cols-2 gap-4">
				<div>
					<label for="latitude" class="mb-1 block text-sm text-gray-400">Latitude</label>
					<input
						id="latitude"
						type="number"
						step="0.0001"
						min="-90"
						max="90"
						bind:value={locationConfig.latitude}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none"
					/>
				</div>
				<div>
					<label for="longitude" class="mb-1 block text-sm text-gray-400">Longitude</label>
					<input
						id="longitude"
						type="number"
						step="0.0001"
						min="-180"
						max="180"
						bind:value={locationConfig.longitude}
						class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-600 focus:outline-none"
					/>
				</div>
			</div>

			<button
				onclick={saveLocation}
				disabled={savingLocation}
				class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
			>
				{savingLocation ? 'Saving...' : 'Save Location'}
			</button>
		</section>

		<!-- go2rtc -->
		<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
			<h2 class="mb-4 text-xl font-semibold text-white">go2rtc</h2>
			<p class="mb-4 text-sm text-gray-400">
				Connect to an external go2rtc server for stream discovery, live MSE video, and HTTP snapshot capture.
			</p>

			<div class="mb-4">
				<label for="go2rtc-url" class="mb-1 block text-sm text-gray-400">Server URL</label>
				<input
					id="go2rtc-url"
					type="text"
					bind:value={go2rtcConfig.url}
					placeholder="http://192.168.1.100:1984"
					class="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-blue-600 focus:outline-none"
				/>
			</div>

			{#if go2rtcTestResult}
				<p class="mb-3 text-sm {go2rtcTestResult.startsWith('Connected') ? 'text-green-400' : 'text-red-400'}">{go2rtcTestResult}</p>
			{/if}

			<div class="flex gap-2">
				<button
					onclick={testGo2rtc}
					disabled={testingGo2rtc || !go2rtcConfig.url}
					class="rounded-lg border border-gray-600 px-4 py-2 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-800 disabled:opacity-50"
				>
					{testingGo2rtc ? 'Testing...' : 'Test Connection'}
				</button>
				<button
					onclick={saveGo2rtc}
					disabled={savingGo2rtc}
					class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
				>
					{savingGo2rtc ? 'Saving...' : 'Save'}
				</button>
			</div>
		</section>

		<!-- Jobs -->
		<section class="space-y-6">
			<h2 class="text-xl font-semibold text-white">Jobs</h2>

			<!-- Snapshot Gap Alerting -->
			<div class="rounded-xl border border-gray-800 bg-gray-900 p-6">
				<h3 class="mb-2 text-lg font-medium text-white">Snapshot Gap Alerting</h3>
				<p class="mb-4 text-sm text-gray-400">
					Alert when no snapshot is captured within 3× a profile's configured interval. Checks run every 60 minutes.
				</p>
				<label class="mb-4 flex items-center gap-3">
					<input
						type="checkbox"
						bind:checked={captureGapConfig.enabled}
						class="h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-600"
					/>
					<span class="text-sm text-gray-200">Enable snapshot gap alerting</span>
				</label>
				<button
					onclick={saveCaptureGap}
					disabled={savingCaptureGap}
					class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
				>
					{savingCaptureGap ? 'Saving...' : 'Save'}
				</button>
			</div>

			<!-- Recording Retention -->
			<div class="rounded-xl border border-gray-800 bg-gray-900 p-6">
				<h3 class="mb-2 text-lg font-medium text-white">Recording Retention</h3>
				<p class="mb-4 text-sm text-gray-400">
					Default retention period for continuous recordings. Recordings older than this are automatically deleted. Individual profiles can override this in their recording settings.
				</p>
				<div class="flex items-end gap-3">
					<div>
						<label for="recording-retention" class="mb-1 block text-sm font-medium text-gray-300">Retention (days)</label>
						<input
							id="recording-retention"
							type="number"
							bind:value={recordingRetentionDays}
							min="1"
							max="365"
							class="w-32 rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
					</div>
					<button
						onclick={saveRecordingRetention}
						disabled={savingRecordingRetention}
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
					>
						{savingRecordingRetention ? 'Saving...' : 'Save'}
					</button>
				</div>

				<!-- Delete All Recordings -->
				<div class="mt-6 border-t border-gray-700 pt-4">
					<h4 class="mb-1 text-sm font-medium text-red-400">Danger Zone</h4>
					<p class="mb-3 text-xs text-gray-500">Permanently delete all recording segments from disk and database. Active recordings will be stopped and restarted.</p>
					<button
						onclick={() => { showDeleteAllRecordings = true; }}
						class="rounded-lg border border-red-800 bg-red-950/50 px-4 py-2 text-sm font-medium text-red-400 transition-colors hover:bg-red-900/50 hover:text-red-300"
					>
						Delete All Recordings
					</button>
					{#if deleteRecordingsResult}
						<p class="mt-2 text-xs {deleteRecordingsResult.startsWith('Error') ? 'text-red-400' : 'text-green-400'}">{deleteRecordingsResult}</p>
					{/if}
				</div>
			</div>

			<!-- Data Cleanup -->
			<div>
				<h3 class="mb-2 text-lg font-medium text-white">Snapshot & Timelapse Cleanup</h3>
				<p class="mb-4 text-sm text-gray-400">
					Configure per-profile cleanup schedules to automatically remove old snapshots and timelapses.
				</p>
				<CleanupScheduleManager />
			</div>

			<!-- OIDC / SSO -->
			<div class="rounded-xl border border-gray-800 bg-gray-900 p-6">
				<h3 class="mb-1 text-lg font-medium text-white">OIDC / SSO</h3>
				<p class="mb-4 text-sm text-gray-400">
					Configure an OpenID Connect provider to enable single sign-on. Users who log in via OIDC are auto-provisioned if they don't have an account.
				</p>

				<!-- IdP configuration helper -->
				<div class="mb-5 rounded-lg border border-gray-700 bg-gray-800/60 p-4 space-y-3">
					<h4 class="text-sm font-medium text-gray-300">Settings for your Identity Provider</h4>
					<p class="text-xs text-gray-500">Copy these values into your Okta / Keycloak / Azure AD app registration.</p>
					<div class="space-y-2">
						<div>
							<span class="text-xs font-medium text-gray-400">Sign-in redirect URI</span>
							<div class="mt-0.5 flex items-center gap-2">
								<code class="flex-1 truncate rounded bg-gray-900 px-2 py-1 text-xs text-blue-300 border border-gray-700">{window.location.origin}/api/auth/oidc/callback</code>
								<button
									type="button"
									onclick={() => { navigator.clipboard.writeText(`${window.location.origin}/api/auth/oidc/callback`); }}
									class="rounded px-2 py-1 text-xs text-gray-400 hover:bg-gray-700 hover:text-white"
									title="Copy to clipboard"
								>
									<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
										<rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
									</svg>
								</button>
							</div>
						</div>
						<div>
							<span class="text-xs font-medium text-gray-400">Sign-out redirect URI <span class="text-gray-600">(if required)</span></span>
							<div class="mt-0.5 flex items-center gap-2">
								<code class="flex-1 truncate rounded bg-gray-900 px-2 py-1 text-xs text-blue-300 border border-gray-700">{window.location.origin}/login</code>
								<button
									type="button"
									onclick={() => { navigator.clipboard.writeText(`${window.location.origin}/login`); }}
									class="rounded px-2 py-1 text-xs text-gray-400 hover:bg-gray-700 hover:text-white"
									title="Copy to clipboard"
								>
									<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
										<rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
									</svg>
								</button>
							</div>
						</div>
						<div>
							<span class="text-xs font-medium text-gray-400">Allowed grant types</span>
							<p class="mt-0.5 text-xs text-gray-300">Authorization Code (with PKCE if no client secret)</p>
						</div>
					</div>
				</div>
				{#if oidcConfig?.enabled}
					<div class="mb-4 rounded-lg border border-green-800 bg-green-900/20 px-3 py-2 text-sm text-green-300">
						OIDC is currently <strong>enabled</strong> with provider "{oidcConfig.provider_name || oidcConfig.issuer_url}".
					</div>
				{/if}
				<form onsubmit={(e) => { e.preventDefault(); saveOIDCConfig(); }} class="space-y-4">
					<div>
						<label for="oidc-issuer-url" class="mb-1 block text-sm font-medium text-gray-300">Issuer URL</label>
						<input
							id="oidc-issuer-url"
							type="url"
							bind:value={oidcForm.issuer_url}
							placeholder="https://accounts.example.com"
							class="w-full rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
					</div>
					<div>
						<label for="oidc-client-id" class="mb-1 block text-sm font-medium text-gray-300">Client ID</label>
						<input
							id="oidc-client-id"
							type="text"
							bind:value={oidcForm.client_id}
							placeholder="your-client-id"
							class="w-full rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
					</div>
					<div>
						<label for="oidc-client-secret" class="mb-1 block text-sm font-medium text-gray-300">Client Secret <span class="text-gray-500">(optional)</span></label>
						<input
							id="oidc-client-secret"
							type="password"
							bind:value={oidcForm.client_secret}
							placeholder="Leave blank for public client (PKCE)"
							class="w-full rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<p class="mt-1 text-xs text-gray-500">Not required for public clients (e.g. Okta SPA apps). PKCE will be used automatically when no secret is provided.</p>
					</div>
					<div>
						<label for="oidc-provider-name" class="mb-1 block text-sm font-medium text-gray-300">Provider Name <span class="text-gray-500">(optional)</span></label>
						<input
							id="oidc-provider-name"
							type="text"
							bind:value={oidcForm.provider_name}
							placeholder="Google, Okta, Keycloak…"
							class="w-full rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
					</div>
					<div>
						<label for="oidc-groups-claim" class="mb-1 block text-sm font-medium text-gray-300">Groups Claim <span class="text-gray-500">(default: groups)</span></label>
						<input
							id="oidc-groups-claim"
							type="text"
							bind:value={oidcForm.groups_claim}
							placeholder="groups"
							class="w-full rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<p class="mt-1 text-xs text-gray-500">The OIDC token claim that contains the user's group list. Common values: groups, roles, realm_access.roles</p>
					</div>
					{#if oidcSaveResult}
						<p class="text-sm {oidcSaveResult.ok ? 'text-green-400' : 'text-red-400'}">{oidcSaveResult.message}</p>
					{/if}
					<button
						type="submit"
						disabled={savingOIDC}
						class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
					>
						{savingOIDC ? 'Saving...' : 'Save OIDC Configuration'}
					</button>
				</form>
			</div>
		</section>
	{/if}

		<!-- TLS / ACME Certificates -->
		{#if tlsConfig !== null}
		<section class="rounded-xl border border-gray-800 bg-gray-900 p-6">
			<div class="space-y-4">
				<h3 class="mb-1 text-lg font-medium text-white">TLS / ACME Certificates</h3>
				<p class="text-sm text-gray-400">
					Acquire and manage TLS certificates via ACME (Let's Encrypt). Port binding is configured in your Docker Compose file.
				</p>

				<!-- Current certificate status -->
				{#if certInfo}
					<div class="rounded-lg border {certInfo.is_expired ? 'border-red-700 bg-red-950/30' : certInfo.days_until_expiry <= 30 ? 'border-yellow-700 bg-yellow-950/30' : 'border-green-700 bg-green-950/30'} p-4">
						<div class="flex items-center gap-2 mb-2">
							{#if certInfo.is_expired}
								<span class="inline-block h-2 w-2 rounded-full bg-red-400"></span>
								<span class="text-sm font-medium text-red-300">Certificate Expired</span>
							{:else if certInfo.days_until_expiry <= 30}
								<span class="inline-block h-2 w-2 rounded-full bg-yellow-400"></span>
								<span class="text-sm font-medium text-yellow-300">Expires in {certInfo.days_until_expiry} days</span>
							{:else}
								<span class="inline-block h-2 w-2 rounded-full bg-green-400"></span>
								<span class="text-sm font-medium text-green-300">Valid — {certInfo.days_until_expiry} days remaining</span>
							{/if}
						</div>
						<div class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-400">
							<span>Domain</span><span class="text-gray-300">{certInfo.domain}</span>
							<span>Issuer</span><span class="text-gray-300">{certInfo.issuer}</span>
							<span>Valid from</span><span class="text-gray-300">{new Date(certInfo.not_before).toLocaleDateString()}</span>
							<span>Valid until</span><span class="text-gray-300">{new Date(certInfo.not_after).toLocaleDateString()}</span>
						</div>
					</div>
				{:else if tlsConfig.has_certificate}
					<p class="text-sm text-gray-400">Certificate present but info unavailable.</p>
				{:else}
					<div class="rounded-lg border border-gray-700 bg-gray-800/50 p-3">
						<p class="text-sm text-gray-400">No certificate installed. Configure a domain and acquire one below.</p>
					</div>
				{/if}

				<!-- Config form -->
				<form onsubmit={(e) => { e.preventDefault(); saveTLSConfig(); }} class="space-y-4">
					<div class="flex items-center gap-3">
						<label class="relative inline-flex cursor-pointer items-center">
							<input type="checkbox" bind:checked={tlsForm.enabled} class="peer sr-only" />
							<div class="peer h-5 w-9 rounded-full bg-gray-600 after:absolute after:left-[2px] after:top-[2px] after:h-4 after:w-4 after:rounded-full after:bg-white after:transition-all peer-checked:bg-blue-600 peer-checked:after:translate-x-full"></div>
						</label>
						<span class="text-sm text-gray-300">Enable TLS</span>
					</div>
					<div>
						<label for="tls-domain" class="mb-1 block text-sm font-medium text-gray-300">Domain</label>
						<input
							id="tls-domain"
							type="text"
							bind:value={tlsForm.domain}
							placeholder="nvr.example.com"
							class="w-full rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
					</div>
					<div>
						<label for="tls-email" class="mb-1 block text-sm font-medium text-gray-300">ACME Email</label>
						<input
							id="tls-email"
							type="email"
							bind:value={tlsForm.email}
							placeholder="admin@example.com"
							class="w-full rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<p class="mt-1 text-xs text-gray-500">Let's Encrypt will send expiry warnings to this address.</p>
					</div>
					<div>
						<label for="tls-acme-url" class="mb-1 block text-sm font-medium text-gray-300">ACME Directory URL</label>
						<input
							id="tls-acme-url"
							type="url"
							bind:value={tlsForm.acme_directory_url}
							placeholder="https://acme-v02.api.letsencrypt.org/directory"
							class="w-full rounded-md border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						/>
						<p class="mt-1 text-xs text-gray-500">Default is Let's Encrypt production. Use a custom ACME CA if needed.</p>
					</div>
					<div>
						<label class="mb-1 block text-sm font-medium text-gray-300">CA Bundle <span class="text-gray-500">(optional)</span></label>
						{#if tlsForm.acme_ca_bundle}
							<div class="flex items-center gap-2 rounded-md border border-gray-600 bg-gray-800 px-3 py-2">
								<svg class="h-4 w-4 flex-shrink-0 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
								</svg>
								<span class="flex-1 truncate text-sm text-gray-300" title={tlsForm.acme_ca_bundle}>{tlsForm.acme_ca_bundle.split('/').pop()}</span>
								<button
									type="button"
									onclick={async () => {
										try {
											await api.deleteCaBundle();
											tlsForm.acme_ca_bundle = '';
											tlsSaveResult = { ok: true, message: 'CA bundle removed.' };
										} catch (err) {
											tlsSaveResult = { ok: false, message: err instanceof Error ? err.message : 'Failed to remove CA bundle.' };
										}
									}}
									class="rounded px-2 py-1 text-xs text-red-400 hover:bg-gray-700 hover:text-red-300"
								>
									Remove
								</button>
							</div>
						{:else}
							<label
								class="flex cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed border-gray-600 bg-gray-800 px-3 py-3 text-sm text-gray-400 transition-colors hover:border-gray-500 hover:text-gray-300"
							>
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
								</svg>
								Upload CA Bundle (.pem)
								<input
									type="file"
									accept=".pem,.crt,.cer"
									class="hidden"
									onchange={async (e) => {
										const target = e.currentTarget as HTMLInputElement;
										const file = target.files?.[0];
										if (!file) return;
										try {
											const result = await api.uploadCaBundle(file);
											tlsForm.acme_ca_bundle = result.path;
											tlsSaveResult = { ok: true, message: 'CA bundle uploaded.' };
										} catch (err) {
											tlsSaveResult = { ok: false, message: err instanceof Error ? err.message : 'Failed to upload CA bundle.' };
										}
										target.value = '';
									}}
								/>
							</label>
						{/if}
						<p class="mt-1 text-xs text-gray-500">PEM certificate bundle for internal ACME servers with self-signed or private CA certificates.</p>
					</div>
					{#if tlsSaveResult}
						<p class="text-sm {tlsSaveResult.ok ? 'text-green-400' : 'text-red-400'}">{tlsSaveResult.message}</p>
					{/if}
					<div class="flex gap-3">
						<button
							type="submit"
							disabled={savingTLS}
							class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
						>
							{savingTLS ? 'Saving...' : 'Save Configuration'}
						</button>
						<button
							type="button"
							disabled={acquiring || !tlsForm.domain}
							onclick={() => acquireCert(false)}
							class="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green-500 disabled:opacity-50"
						>
							{acquiring ? 'Acquiring...' : 'Acquire Certificate'}
						</button>
						{#if tlsConfig?.has_certificate}
							<button
								type="button"
								disabled={acquiring}
								onclick={() => acquireCert(true)}
								class="rounded-lg border border-gray-600 px-4 py-2 text-sm text-gray-300 transition-colors hover:bg-gray-800 disabled:opacity-50"
							>
								Force Renew
							</button>
						{/if}
					</div>
					{#if acquireResult}
						<p class="text-sm {acquireResult.ok ? 'text-green-400' : 'text-red-400'}">{acquireResult.message}</p>
					{/if}
				</form>
			</div>
		</section>
		{/if}
</div>

<!-- Delete All Recordings Confirmation Modal -->
{#if showDeleteAllRecordings}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onclick={() => { if (!deletingAllRecordings) showDeleteAllRecordings = false; }}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="mx-4 w-full max-w-sm rounded-xl bg-gray-900 p-6 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<h3 class="mb-2 text-lg font-semibold text-red-400">Delete All Recordings</h3>
			<p class="mb-2 text-sm text-gray-300">
				This will <strong class="text-white">permanently delete</strong> all recording segment files from disk and remove all segment records from the database.
			</p>
			<p class="mb-4 text-sm text-gray-400">
				Active recordings will be stopped and automatically restarted afterward. This action <strong class="text-red-400">cannot be undone</strong>.
			</p>
			<div class="flex justify-end gap-3">
				<button
					onclick={() => { showDeleteAllRecordings = false; }}
					disabled={deletingAllRecordings}
					class="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 disabled:opacity-50"
				>
					Cancel
				</button>
				<button
					onclick={confirmDeleteAllRecordings}
					disabled={deletingAllRecordings}
					class="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
				>
					{deletingAllRecordings ? 'Deleting...' : 'Delete Everything'}
				</button>
			</div>
		</div>
	</div>
{/if}
