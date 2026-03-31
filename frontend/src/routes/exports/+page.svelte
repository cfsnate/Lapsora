<script lang="ts">
	import { api } from '$lib/api';
	import type { ClipExport } from '$lib/types';
	import { formatBytes, formatDateTime } from '$lib/utils';

	let exports_ = $state<ClipExport[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let filterStatus = $state('');
	let deleteTarget = $state<ClipExport | null>(null);
	let cancelTarget = $state<ClipExport | null>(null);
	let playingExport = $state<ClipExport | null>(null);
	let deleting = $state(false);
	let cancelling = $state(false);

	async function loadExports() {
		try {
			exports_ = await api.getExports(filterStatus || undefined);
			error = null;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to load exports — try refreshing the page';
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		filterStatus;
		loading = true;
		loadExports();
	});

	$effect(() => {
		const hasActive = exports_.some(e => e.status === 'pending' || e.status === 'processing');
		if (!hasActive) return;
		const interval = setInterval(loadExports, 5000);
		return () => clearInterval(interval);
	});

	async function confirmDelete() {
		if (!deleteTarget) return;
		deleting = true;
		try {
			await api.deleteExport(deleteTarget.id);
			exports_ = exports_.filter(e => e.id !== deleteTarget!.id);
			deleteTarget = null;
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Delete failed');
		} finally {
			deleting = false;
		}
	}

	async function confirmCancel() {
		if (!cancelTarget) return;
		cancelling = true;
		try {
			await api.cancelExport(cancelTarget.id);
			exports_ = exports_.filter(e => e.id !== cancelTarget!.id);
			cancelTarget = null;
		} catch (err) {
			alert(err instanceof Error ? err.message : 'Cancel failed');
		} finally {
			cancelling = false;
		}
	}

	function formatTimeRange(start: string, end: string): string {
		return `${formatDateTime(start)} — ${formatDateTime(end)}`;
	}

	function statusColor(status: string): string {
		switch (status) {
			case 'pending': return 'border-yellow-800 bg-yellow-950/20';
			case 'processing': return 'border-blue-800 bg-blue-950/20';
			case 'failed': return 'border-red-800 bg-red-950/20';
			default: return 'border-gray-800';
		}
	}

	function statusLabel(status: string): string {
		return status.charAt(0).toUpperCase() + status.slice(1);
	}
</script>

<svelte:head><title>Clip Exports - Lapsora</title></svelte:head>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h1 class="text-3xl font-bold text-white">Clip Exports</h1>
		<select
			bind:value={filterStatus}
			class="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
		>
			<option value="">All</option>
			<option value="pending">Pending</option>
			<option value="processing">Processing</option>
			<option value="completed">Completed</option>
			<option value="failed">Failed</option>
		</select>
	</div>

	{#if loading}
		<div class="flex items-center gap-2 text-gray-400">
			<svg class="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none">
				<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25"></circle>
				<path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" class="opacity-75"></path>
			</svg>
			<span>Loading exports...</span>
		</div>
	{:else if error}
		<div class="rounded-xl border border-red-800 bg-red-950/50 p-4">
			<p class="text-sm text-red-400">{error}</p>
		</div>
	{:else if exports_.length === 0}
		<div class="rounded-xl border border-gray-800 bg-gray-900 p-8 text-center">
			<h2 class="text-lg font-bold text-gray-300">No Exports Yet</h2>
			<p class="mt-2 text-sm text-gray-500">Export a clip from any camera's playback page to see it here.</p>
		</div>
	{:else}
		<div class="space-y-3">
			{#each exports_ as exp (exp.id)}
				<div class="rounded-xl border bg-gray-900 p-4 transition-colors hover:border-gray-700 {statusColor(exp.status)}">
					<!-- Line 1: status + profile -->
					<div class="flex items-center gap-2">
						{#if exp.status === 'pending'}
							<svg class="h-4 w-4 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
							</svg>
							<span class="text-xs font-bold text-yellow-500">Pending</span>
						{:else if exp.status === 'processing'}
							<svg class="h-4 w-4 animate-spin text-blue-500" fill="none" viewBox="0 0 24 24">
								<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25"></circle>
								<path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" class="opacity-75"></path>
							</svg>
							<span class="text-xs font-bold text-blue-500">Processing</span>
						{:else if exp.status === 'completed'}
							<svg class="h-4 w-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
							</svg>
							<span class="text-xs font-bold text-green-500">Completed</span>
						{:else if exp.status === 'failed'}
							<svg class="h-4 w-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
							</svg>
							<span class="text-xs font-bold text-red-500">Failed</span>
						{/if}
						<span class="text-sm text-gray-200">{exp.stream_name ?? 'Unknown'}{exp.profile_name ? ` · ${exp.profile_name}` : ''}</span>
					</div>

					<!-- Line 2: metadata -->
					<div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-400">
						<span class="font-mono">{formatTimeRange(exp.start_time, exp.end_time)}</span>
						<span>·</span>
						<span>{exp.quality_preset}</span>
						{#if exp.resolution && exp.resolution !== 'original'}
							<span>·</span>
							<span>{exp.resolution}</span>
						{/if}
						{#if exp.status === 'completed' && exp.file_size}
							<span>·</span>
							<span>{formatBytes(exp.file_size)}</span>
						{/if}
					</div>

					{#if exp.status === 'failed' && exp.error_message}
						<p class="mt-1 text-xs text-red-400">Export failed: {exp.error_message}</p>
					{/if}

					<!-- Line 3: actions -->
					<div class="mt-2 flex items-center gap-1">
						<div class="flex-1"></div>
						{#if exp.status === 'completed'}
							<button
								onclick={() => { playingExport = exp; }}
								class="inline-flex items-center rounded px-3 py-2 text-xs font-bold text-green-400 hover:bg-gray-800"
							>
								<svg class="mr-1 h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24">
									<path d="M8 5v14l11-7z" />
								</svg>
								Play
							</button>
							<a
								href={api.getExportDownloadUrl(exp.id)}
								download
								class="inline-flex items-center rounded px-3 py-2 text-xs font-bold text-blue-400 hover:bg-gray-800"
							>
								<svg class="mr-1 h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
								</svg>
								Download
							</a>
						{/if}
						{#if exp.status === 'pending' || exp.status === 'processing'}
							<button
								onclick={() => { cancelTarget = exp; }}
								class="inline-flex items-center rounded px-3 py-2 text-xs font-bold text-yellow-400 hover:bg-gray-800"
							>
								<svg class="mr-1 h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
								</svg>
								Cancel Export
							</button>
						{/if}
						{#if exp.status === 'completed' || exp.status === 'failed'}
							<button
								onclick={() => { deleteTarget = exp; }}
								class="inline-flex items-center rounded px-3 py-2 text-xs font-bold text-red-400 hover:bg-gray-800"
							>
								<svg class="mr-1 h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
								</svg>
								Delete Clip
							</button>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<!-- Delete Confirmation Modal -->
{#if deleteTarget}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onclick={() => { deleteTarget = null; }}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="w-full max-w-sm rounded-xl bg-gray-900 p-6 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<h3 class="mb-2 text-lg font-bold text-gray-100">Delete Clip</h3>
			<p class="mb-4 text-sm text-gray-400">Are you sure you want to delete this clip? The file will be permanently removed.</p>
			<div class="flex justify-end gap-3">
				<button
					onclick={() => { deleteTarget = null; }}
					class="rounded-lg bg-gray-700 px-4 py-2 text-sm font-bold text-gray-300 hover:bg-gray-600"
				>
					Cancel
				</button>
				<button
					onclick={confirmDelete}
					disabled={deleting}
					class="rounded-lg bg-red-600 px-4 py-2 text-sm font-bold text-white hover:bg-red-500 disabled:opacity-50"
				>
					{deleting ? 'Deleting...' : 'Delete Clip'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Cancel Confirmation Modal -->
{#if cancelTarget}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onclick={() => { cancelTarget = null; }}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="w-full max-w-sm rounded-xl bg-gray-900 p-6 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<h3 class="mb-2 text-lg font-bold text-gray-100">Cancel Export</h3>
			<p class="mb-4 text-sm text-gray-400">Cancel this export? It cannot be resumed.</p>
			<div class="flex justify-end gap-3">
				<button
					onclick={() => { cancelTarget = null; }}
					class="rounded-lg bg-gray-700 px-4 py-2 text-sm font-bold text-gray-300 hover:bg-gray-600"
				>
					Keep Export
				</button>
				<button
					onclick={confirmCancel}
					disabled={cancelling}
					class="rounded-lg bg-yellow-600 px-4 py-2 text-sm font-bold text-white hover:bg-yellow-500 disabled:opacity-50"
				>
					{cancelling ? 'Cancelling...' : 'Cancel Export'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Clip Player Modal -->
{#if playingExport}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onclick={() => { playingExport = null; }}>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="mx-4 w-full max-w-3xl rounded-xl bg-gray-900 shadow-xl" onclick={(e) => e.stopPropagation()}>
			<div class="flex items-center justify-between border-b border-gray-800 p-4">
				<div>
					<h2 class="text-lg font-semibold text-gray-100">Clip Export</h2>
					<p class="text-xs text-gray-400">{playingExport.stream_name ?? ''}{playingExport.profile_name ? ` · ${playingExport.profile_name}` : ''}</p>
				</div>
				<button onclick={() => { playingExport = null; }} class="text-gray-400 hover:text-gray-200" aria-label="Close">
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
			<div class="p-4">
				<!-- svelte-ignore a11y_media_has_caption -->
				<video
					src={api.getExportDownloadUrl(playingExport.id)}
					controls
					autoplay
					class="w-full rounded-lg bg-black"
				></video>
			</div>
		</div>
	</div>
{/if}
