<script lang="ts">
	import { page } from '$app/stores';
	import { api } from '$lib/api';
	import type { Stream, Profile, PlaybackAvailabilityRange } from '$lib/types';
	import UnifiedPlayer from '$lib/components/UnifiedPlayer.svelte';
	import PlaybackControls from '$lib/components/PlaybackControls.svelte';
	import Timeline from '$lib/components/Timeline.svelte';
	import ExportDialog from '$lib/components/ExportDialog.svelte';

	let id = $derived(Number($page.params.id));

	let stream = $state<Stream | null>(null);
	let profiles = $state<Profile[]>([]);
	let selectedProfileId = $state<number | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	let mode = $state<'live' | 'recording'>('live');
	let playbackRate = $state(1);
	let currentTime = $state<Date | null>(null);
	let playing = $state(false);
	let hlsSrc = $state('');
	let liveWsUrl = $state<string | null>(null);
	let liveHlsSrc = $state<string | null>(null);
	// Separate tracking for the playback window so hlsSrc mutations don't re-trigger effects
	let playbackWindowStart = $state<Date | null>(null);
	let playbackWindowEnd = $state<Date | null>(null);

	let availabilityRanges = $state<PlaybackAvailabilityRange[]>([]);

	let selectionStart = $state<Date | null>(null);
	let selectionEnd = $state<Date | null>(null);
	let showExportDialog = $state(false);
	let hasSelection = $derived(selectionStart !== null && selectionEnd !== null);

	let recordingProfiles = $derived(profiles.filter(p => p.recording_enabled));
	let selectedProfile = $derived(recordingProfiles.find(p => p.id === selectedProfileId) ?? null);

	$effect(() => {
		const currentId = id;
		loading = true;
		error = null;

		Promise.all([api.getStream(currentId), api.getStreamProfiles(currentId)])
			.then(async ([s, p]) => {
				stream = s;
				profiles = p;
				const recProfiles = p.filter(pr => pr.recording_enabled);
				selectedProfileId = recProfiles[0]?.id ?? null;

				// Always start in live mode and attempt to get the live URL
				mode = 'live';
				try {
					const data = await api.getStreamLiveUrl(currentId);
					liveWsUrl = data.ws_url;
					liveHlsSrc = data.hls_url;
				} catch { /* live URL unavailable */ }
			})
			.catch((err) => { error = err instanceof Error ? err.message : 'Failed to load'; })
			.finally(() => { loading = false; });
	});

	$effect(() => {
		if (!selectedProfileId) return;
		const profId = selectedProfileId;

		function fetchAvailability() {
			// Fetch last 7 days of availability. Use UTC date so it aligns with
			// how the backend stores segment timestamps.
			const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
			const dateStr = sevenDaysAgo.toISOString().slice(0, 10);
			api.getAvailability(profId, dateStr, 7)
				.then((ranges) => { availabilityRanges = ranges; })
				.catch(() => { availabilityRanges = []; });
		}

		fetchAvailability();
		// Poll every 30s so the timeline updates as recordings accumulate
		const interval = setInterval(fetchAvailability, 30_000);
		return () => clearInterval(interval);
	});

	function handleSeek(time: Date) {
		if (!selectedProfileId) return;
		mode = 'recording';
		const start = new Date(time.getTime() - 30 * 60 * 1000);
		const end = new Date(time.getTime() + 30 * 60 * 1000);
		playbackWindowStart = start;
		playbackWindowEnd = end;
		hlsSrc = api.getPlaylistUrl(selectedProfileId, start.toISOString(), end.toISOString());
		playing = true;
	}

	function handleGoLive() {
		mode = 'live';
		hlsSrc = '';
		playbackWindowStart = null;
		playbackWindowEnd = null;
		playbackRate = 1;
		if (!liveWsUrl && !liveHlsSrc) {
			api.getStreamLiveUrl(id).then(d => {
				liveWsUrl = d.ws_url;
				liveHlsSrc = d.hls_url;
			}).catch(() => {});
		}
	}

	function handlePlayPause() {
		playing = !playing;
	}

	function handleSpeedChange(rate: number) {
		playbackRate = rate;
	}

	function handleTimeUpdate(time: Date | null) {
		currentTime = time;
		if (!time || !selectedProfileId || mode !== 'recording') return;
		if (!playbackWindowEnd) return;
		// Advance the window when within 5 minutes of its end
		if (time.getTime() > playbackWindowEnd.getTime() - 5 * 60 * 1000) {
			const newStart = new Date(time.getTime() - 30 * 60 * 1000);
			const newEnd = new Date(time.getTime() + 30 * 60 * 1000);
			playbackWindowStart = newStart;
			playbackWindowEnd = newEnd;
			hlsSrc = api.getPlaylistUrl(selectedProfileId, newStart.toISOString(), newEnd.toISOString());
		}
	}

	function handleSelectionChange(start: Date | null, end: Date | null) {
		selectionStart = start;
		selectionEnd = end;
	}

	function handleExportClick() {
		showExportDialog = true;
	}

	function handleExportClose() {
		showExportDialog = false;
	}

	function handleExportSubmit(exportId: number) {
		showExportDialog = false;
		selectionStart = null;
		selectionEnd = null;
	}

	function handleProfileChange(profileId: number) {
		selectedProfileId = profileId;
		if (mode === 'recording' && playbackWindowStart && playbackWindowEnd && selectedProfileId) {
			hlsSrc = api.getPlaylistUrl(profileId, playbackWindowStart.toISOString(), playbackWindowEnd.toISOString());
		}
	}
</script>

<svelte:head><title>{stream?.name ?? 'Playback'} - Lapsora</title></svelte:head>

{#if loading}
	<div class="flex items-center gap-2 text-gray-400">
		<svg class="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none">
			<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25"></circle>
			<path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" class="opacity-75"></path>
		</svg>
		<span>Loading playback...</span>
	</div>
{:else if error}
	<div class="rounded-xl border border-red-800 bg-red-950/50 p-4">
		<p class="text-sm text-red-400">{error}</p>
	</div>
{:else if stream}
	<div class="space-y-4">
		<!-- Header -->
		<div class="flex items-center justify-between">
			<div class="flex items-center gap-3">
				<a href="/streams/{id}" class="text-gray-400 hover:text-gray-200">
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
					</svg>
				</a>
				<h1 class="text-3xl font-bold text-white">{stream.name}</h1>
				{#if mode === 'live'}
					<span class="flex items-center gap-1.5 rounded-full bg-red-900 px-2.5 py-0.5 text-xs font-medium text-red-300">
						<span class="relative flex h-2 w-2">
							<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75"></span>
							<span class="relative inline-flex h-2 w-2 rounded-full bg-red-500"></span>
						</span>
						LIVE
					</span>
				{/if}
			</div>
			{#if recordingProfiles.length > 1}
				<select
					value={selectedProfileId}
					onchange={(e) => handleProfileChange(Number((e.target as HTMLSelectElement).value))}
					class="rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-100 focus:border-blue-500 focus:outline-none"
				>
					{#each recordingProfiles as p}
						<option value={p.id}>{p.name}</option>
					{/each}
				</select>
			{/if}
		</div>

		<!-- Video Player -->
		{#if (mode === 'live' && (liveWsUrl || liveHlsSrc)) || (mode === 'recording' && hlsSrc)}
			<UnifiedPlayer
				{mode}
				wsUrl={liveWsUrl ?? undefined}
				hlsSrc={mode === 'live' ? (liveHlsSrc ?? undefined) : (hlsSrc || undefined)}
				{playbackRate}
				onTimeUpdate={handleTimeUpdate}
				onError={(msg) => console.error('Player error:', msg)}
				onReady={() => { playing = true; }}
			/>
		{:else if mode === 'live'}
			<div class="flex aspect-video w-full items-center justify-center overflow-hidden rounded-lg bg-black">
				<div class="flex items-center gap-3 text-gray-400">
					<svg class="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none">
						<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25"></circle>
						<path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" class="opacity-75"></path>
					</svg>
					<span class="text-sm">Connecting to live stream...</span>
				</div>
			</div>
		{:else}
			<div class="flex aspect-video w-full items-center justify-center overflow-hidden rounded-lg bg-black">
				<div class="text-center">
					<p class="text-lg font-medium text-gray-400">No Recording Selected</p>
					<p class="mt-1 text-sm text-gray-500">
						{recordingProfiles.length === 0
							? 'Enable recording in profile settings to record footage.'
							: 'Click a point on the timeline below to start playback.'}
					</p>
				</div>
			</div>
		{/if}

		<!-- Playback Controls -->
		<PlaybackControls
			{currentTime}
			{playing}
			{playbackRate}
			isLive={mode === 'live'}
			{hasSelection}
			onPlayPause={handlePlayPause}
			onSpeedChange={handleSpeedChange}
			onGoLive={handleGoLive}
			onExportClick={handleExportClick}
		/>

		<!-- Timeline -->
		{#if selectedProfileId}
			<Timeline
				{availabilityRanges}
				{currentTime}
				onSeek={handleSeek}
				{selectionStart}
				{selectionEnd}
				onSelectionChange={handleSelectionChange}
			/>
		{/if}

		{#if selectedProfileId && selectionStart && selectionEnd}
			<ExportDialog
				open={showExportDialog}
				profileId={selectedProfileId}
				startTime={selectionStart}
				endTime={selectionEnd}
				onclose={handleExportClose}
				onsubmit={handleExportSubmit}
			/>
		{/if}
	</div>
{/if}
