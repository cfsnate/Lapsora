<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import type { Profile, Stream } from '$lib/types';

	let loading = $state(true);
	let streams = $state<Stream[]>([]);
	let profileMap = $state<Record<number, Profile[]>>({});
	let selectedProfileId = $state<number | null>(null);
	let logLines = $state<{ profile_id: number; ts: string; line: string }[]>([]);
	let liveLines = $state<{ profile_id: number; ts: string; line: string }[]>([]);
	let autoScroll = $state(true);
	let eventSource: EventSource | null = null;
	let logContainerEl = $state<HTMLDivElement | null>(null);

	// Auth guard + data loading
	$effect(() => {
		api.getMe().then((me) => {
			if (me.role !== 'admin') { goto('/'); return; }
			return Promise.all([api.getStreams(), api.getConsoleProfiles()]);
		}).then(async (results) => {
			if (!results) return;
			const [fetchedStreams, consoleData] = results;
			streams = fetchedStreams;

			const pMap: Record<number, Profile[]> = {};
			for (const stream of fetchedStreams) {
				pMap[stream.id] = await api.getStreamProfiles(stream.id);
			}
			profileMap = pMap;

			// Auto-select first profile that has logs
			const allProfiles = Object.values(pMap).flat();
			if (consoleData.profile_ids.length > 0) {
				selectedProfileId = consoleData.profile_ids[0];
			} else if (allProfiles.length > 0) {
				selectedProfileId = allProfiles[0].id;
			}
		}).catch(() => goto('/')).finally(() => { loading = false; });
	});

	// Load logs when profile changes
	$effect(() => {
		if (selectedProfileId === null) return;
		const pid = selectedProfileId;
		logLines = [];
		liveLines = [];

		api.getProfileLogs(pid).then((data) => {
			logLines = data.lines;
		}).catch(() => {});
	});

	// SSE connection for live updates
	$effect(() => {
		if (eventSource) {
			eventSource.close();
			eventSource = null;
		}

		const url = api.getConsoleStreamUrl();
		const es = new EventSource(url, { withCredentials: true });
		eventSource = es;

		es.addEventListener('console_log', (e: MessageEvent) => {
			try {
				const entry = JSON.parse(e.data);
				if (selectedProfileId !== null && entry.profile_id === selectedProfileId) {
					liveLines = [...liveLines, entry];
					// Cap live lines to prevent memory growth
					if (liveLines.length > 2000) {
						liveLines = liveLines.slice(-1000);
					}
				}
			} catch { /* ignore parse errors */ }
		});

		return () => {
			es.close();
			eventSource = null;
		};
	});

	// Auto-scroll
	$effect(() => {
		// Trigger on line changes
		const _trigger = logLines.length + liveLines.length;
		if (autoScroll && logContainerEl) {
			requestAnimationFrame(() => {
				if (logContainerEl) {
					logContainerEl.scrollTop = logContainerEl.scrollHeight;
				}
			});
		}
	});

	function allProfiles(): { profile: Profile; streamName: string }[] {
		const result: { profile: Profile; streamName: string }[] = [];
		for (const stream of streams) {
			for (const profile of profileMap[stream.id] ?? []) {
				result.push({ profile, streamName: stream.name });
			}
		}
		return result;
	}

	function formatTs(ts: string): string {
		try {
			const d = new Date(ts);
			return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
		} catch {
			return '';
		}
	}

	function handleScroll() {
		if (!logContainerEl) return;
		const { scrollTop, scrollHeight, clientHeight } = logContainerEl;
		// Auto-scroll is on if user is near the bottom
		autoScroll = scrollHeight - scrollTop - clientHeight < 50;
	}

	function clearLive() {
		liveLines = [];
	}
</script>

<svelte:head>
	<title>FFmpeg Console — Lapsora</title>
</svelte:head>

<div class="flex h-full flex-col gap-4">
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-2xl font-bold text-white">FFmpeg Console</h1>
			<p class="text-sm text-gray-400 mt-1">Live FFmpeg output from recording processes.</p>
		</div>
	</div>

	{#if loading}
		<p class="text-gray-400 text-sm">Loading...</p>
	{:else}
		<!-- Profile selector + controls -->
		<div class="flex items-center gap-3">
			<select
				bind:value={selectedProfileId}
				class="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
			>
				{#each allProfiles() as { profile, streamName }}
					<option value={profile.id}>{streamName} / {profile.name}</option>
				{/each}
			</select>
			<label class="flex items-center gap-2 text-sm text-gray-400">
				<input type="checkbox" bind:checked={autoScroll} class="rounded border-gray-600 bg-gray-800 text-blue-500" />
				Auto-scroll
			</label>
			<button
				onclick={clearLive}
				class="rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
			>
				Clear
			</button>
			<div class="ml-auto flex items-center gap-2">
				<span class="inline-block h-2 w-2 rounded-full {liveLines.length > 0 || logLines.length > 0 ? 'bg-green-400' : 'bg-gray-600'}"></span>
				<span class="text-xs text-gray-500">{logLines.length + liveLines.length} lines</span>
			</div>
		</div>

		<!-- Log viewer -->
		<div
			bind:this={logContainerEl}
			onscroll={handleScroll}
			class="flex-1 min-h-0 overflow-y-auto rounded-xl border border-gray-800 bg-gray-950 p-4 font-mono text-xs leading-relaxed"
		>
			{#if logLines.length === 0 && liveLines.length === 0}
				<p class="text-gray-600 italic">No log output yet. Logs appear when the recording process is running.</p>
			{:else}
				{#each logLines as entry}
					<div class="flex gap-3 hover:bg-gray-900/50">
						<span class="shrink-0 text-gray-600 select-none">{formatTs(entry.ts)}</span>
						<span class="{entry.line.startsWith('[lapsora]') ? 'text-blue-400' : entry.line.includes('error') || entry.line.includes('Error') ? 'text-red-400' : entry.line.includes('warning') || entry.line.includes('Warning') ? 'text-yellow-400' : 'text-gray-300'}">{entry.line}</span>
					</div>
				{/each}
				{#if liveLines.length > 0 && logLines.length > 0}
					<div class="border-t border-gray-800 my-2"></div>
				{/if}
				{#each liveLines as entry}
					<div class="flex gap-3 hover:bg-gray-900/50">
						<span class="shrink-0 text-gray-600 select-none">{formatTs(entry.ts)}</span>
						<span class="{entry.line.startsWith('[lapsora]') ? 'text-blue-400' : entry.line.includes('error') || entry.line.includes('Error') ? 'text-red-400' : entry.line.includes('warning') || entry.line.includes('Warning') ? 'text-yellow-400' : 'text-gray-300'}">{entry.line}</span>
					</div>
				{/each}
			{/if}
		</div>
	{/if}
</div>
