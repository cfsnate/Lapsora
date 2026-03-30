<script lang="ts">
	interface Props {
		currentTime: Date | null;
		playing: boolean;
		playbackRate: number;
		isLive: boolean;
		onPlayPause: () => void;
		onSpeedChange: (rate: number) => void;
		onGoLive: () => void;
	}

	let { currentTime, playing, playbackRate, isLive, onPlayPause, onSpeedChange, onGoLive }: Props = $props();

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

	{#if !isLive}
		<div class="flex items-center gap-1">
			{#each speeds as speed}
				<button
					onclick={() => onSpeedChange(speed)}
					class="rounded-md px-2 py-1 text-xs {playbackRate === speed ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700'}"
				>
					{speed}×
				</button>
			{/each}
		</div>
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
