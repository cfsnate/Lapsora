<script lang="ts">
	interface Props {
		currentTime: Date | null;
		playing: boolean;
		playbackRate: number;
		isLive: boolean;
		hasSelection?: boolean;
		clipMode?: boolean;
		onPlayPause: () => void;
		onSpeedChange: (rate: number) => void;
		onGoLive: () => void;
		onExportClick?: () => void;
		onClipModeToggle?: () => void;
	}

	let { currentTime, playing, playbackRate, isLive, hasSelection = false, clipMode = false, onPlayPause, onSpeedChange, onGoLive, onExportClick, onClipModeToggle }: Props = $props();

	let timeDisplay = $derived(
		currentTime
			? currentTime.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
			: '--:--:--'
	);

	const speeds = [0.5, 1, 2, 4, 8];
</script>

<div class="flex items-center gap-4 rounded-lg bg-gray-900 px-4 py-3">
	<button onclick={onPlayPause} class="text-gray-300 hover:text-white" aria-label={playing ? 'Pause' : 'Play'}>
		{#if playing}
			<svg class="h-6 w-6" fill="currentColor" viewBox="0 0 24 24"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/></svg>
		{:else}
			<svg class="h-6 w-6" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
		{/if}
	</button>

	<span class="text-sm font-mono text-white">{timeDisplay}</span>

	<div class="flex-1"></div>

	<div class="flex items-center gap-1">
		{#each speeds as speed}
			<button
				onclick={() => onSpeedChange(speed)}
				disabled={isLive}
				class="rounded-md px-2 py-1 text-xs {isLive ? 'cursor-not-allowed opacity-40 bg-gray-800 text-gray-600' : playbackRate === speed ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700'}"
			>
				{speed}×
			</button>
		{/each}
	</div>

	<!-- Clip export mode toggle -->
	{#if onClipModeToggle}
		<button
			onclick={onClipModeToggle}
			class="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors {clipMode ? 'bg-orange-600 text-white hover:bg-orange-500' : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700'}"
			aria-label={clipMode ? 'Cancel clip selection' : 'Select clip to export'}
		>
			<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 002.828 2.828L18 9.828V15h2V5h-10v2h5.172z" />
			</svg>
			{clipMode ? 'Cancel' : 'Clip Export'}
		</button>
	{/if}

	{#if hasSelection && onExportClick}
		<button onclick={onExportClick}
			class="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white hover:bg-blue-500 transition-colors">
			<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
			</svg>
			Export Clip
		</button>
	{/if}

	{#if !isLive}
		<button onclick={onGoLive} class="rounded-md bg-red-500 px-4 py-1 text-xs text-white hover:bg-red-600">
			Go Live
		</button>
	{:else}
		<span class="flex items-center gap-1.5 text-xs font-medium text-red-400">
			<span class="relative flex h-2 w-2">
				<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75"></span>
				<span class="relative inline-flex h-2 w-2 rounded-full bg-red-500"></span>
			</span>
			LIVE
		</span>
	{/if}
</div>

{#if clipMode && !hasSelection}
	<div class="mt-1 text-center text-xs text-orange-400/80">
		Click a start point on the timeline, then click the end point
	</div>
{/if}
