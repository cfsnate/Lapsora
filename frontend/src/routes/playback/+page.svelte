<script lang="ts">
	import { api } from '$lib/api';
	import type { Stream, Profile } from '$lib/types';

	type StreamWithProfiles = Stream & { profiles: Profile[] };

	let streams = $state<StreamWithProfiles[]>([]);
	let loading = $state(true);

	$effect(() => {
		api.getStreams()
			.then(async (ss) => {
				const withProfiles = await Promise.all(
					ss.map(async (s) => {
						const profiles = await api.getStreamProfiles(s.id).catch(() => []);
						return { ...s, profiles };
					})
				);
				streams = withProfiles;
			})
			.catch(() => {})
			.finally(() => { loading = false; });
	});

	let recordingStreams = $derived(
		streams.filter(s => s.profiles.some(p => p.recording_enabled))
	);
	let liveOnlyStreams = $derived(
		streams.filter(s => !s.profiles.some(p => p.recording_enabled))
	);
</script>

<svelte:head><title>Playback - Lapsora</title></svelte:head>

<div class="space-y-6">
	<div>
		<h1 class="text-3xl font-bold text-white">Playback</h1>
		<p class="mt-1 text-sm text-gray-400">Live view and recorded footage for your cameras.</p>
	</div>

	{#if loading}
		<div class="flex items-center gap-2 text-gray-400">
			<svg class="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none">
				<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25"></circle>
				<path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" class="opacity-75"></path>
			</svg>
			<span>Loading cameras...</span>
		</div>
	{:else if streams.length === 0}
		<div class="rounded-xl border border-gray-800 bg-gray-900 p-8 text-center">
			<p class="text-gray-400">No cameras configured. <a href="/streams" class="text-blue-400 hover:text-blue-300">Add a stream</a> to get started.</p>
		</div>
	{:else}
		{#if recordingStreams.length > 0}
			<div>
				<h2 class="mb-3 text-sm font-medium uppercase tracking-wider text-gray-500">Recording</h2>
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
					{#each recordingStreams as stream}
						<a
							href="/streams/{stream.id}/playback"
							class="group flex items-center gap-4 rounded-xl border border-gray-800 bg-gray-900 p-4 transition-colors hover:border-gray-700 hover:bg-gray-800"
						>
							<div class="relative h-20 w-32 shrink-0 overflow-hidden rounded-lg bg-gray-800">
								<img
									src={api.getStreamPreviewUrl(stream.id)}
									alt={stream.name}
									class="h-full w-full object-cover"
									onerror={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
								/>
								<span class="absolute bottom-1 right-1 flex items-center gap-1 rounded-full bg-black/60 px-1.5 py-0.5 text-xs text-red-400">
									<span class="relative flex h-1.5 w-1.5">
										<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75"></span>
										<span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-red-500"></span>
									</span>
									REC
								</span>
							</div>
							<div class="min-w-0 flex-1">
								<p class="truncate font-medium text-gray-100 group-hover:text-white">{stream.name}</p>
								<p class="mt-0.5 text-xs text-gray-500">
									{stream.profiles.filter(p => p.recording_enabled).length} recording profile{stream.profiles.filter(p => p.recording_enabled).length !== 1 ? 's' : ''}
								</p>
								<p class="mt-1 text-xs font-medium text-blue-400 group-hover:text-blue-300">Open playback →</p>
							</div>
						</a>
					{/each}
				</div>
			</div>
		{/if}

		{#if liveOnlyStreams.length > 0}
			<div>
				<h2 class="mb-3 text-sm font-medium uppercase tracking-wider text-gray-500">Live only</h2>
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
					{#each liveOnlyStreams as stream}
						<a
							href="/streams/{stream.id}/playback"
							class="group flex items-center gap-4 rounded-xl border border-gray-800 bg-gray-900 p-4 transition-colors hover:border-gray-700 hover:bg-gray-800"
						>
							<div class="relative h-20 w-32 shrink-0 overflow-hidden rounded-lg bg-gray-800">
								<img
									src={api.getStreamPreviewUrl(stream.id)}
									alt={stream.name}
									class="h-full w-full object-cover"
									onerror={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
								/>
							</div>
							<div class="min-w-0 flex-1">
								<p class="truncate font-medium text-gray-100 group-hover:text-white">{stream.name}</p>
								<p class="mt-0.5 text-xs text-gray-500">Live view only</p>
								<p class="mt-1 text-xs font-medium text-blue-400 group-hover:text-blue-300">Open live view →</p>
							</div>
						</a>
					{/each}
				</div>
			</div>
		{/if}

		{#if recordingStreams.length === 0}
			<div class="rounded-xl border border-gray-800 bg-gray-900 p-6">
				<p class="text-sm text-gray-400">
					No cameras have recording enabled. Enable recording in a profile's settings to start recording footage you can seek through.
				</p>
			</div>
		{/if}
	{/if}
</div>
