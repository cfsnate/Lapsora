<script lang="ts">
	interface Props {
		availabilityRanges: { start: string; end: string }[];
		currentTime: Date | null;
		onSeek: (time: Date) => void;
		selectionStart?: Date | null;
		selectionEnd?: Date | null;
		onSelectionChange?: (start: Date | null, end: Date | null) => void;
	}

	let { availabilityRanges, currentTime, onSeek, selectionStart = null, selectionEnd = null, onSelectionChange }: Props = $props();

	let containerEl = $state<HTMLDivElement | null>(null);
	let containerWidth = $state(800);
	let viewStart = $state<Date>(new Date(Date.now() - 60 * 60 * 1000));
	let viewEnd = $state<Date>(new Date());
	let hoverX = $state<number | null>(null);
	let isDragging = $state(false);
	let dragStartX = $state(0);
	let dragStartView = $state<{ start: number; end: number }>({ start: 0, end: 0 });
	let activeZoom = $state('1h');
	let selectedDate = $state(new Date().toISOString().slice(0, 16));

	const zoomPresets = [
		{ label: '1h', ms: 60 * 60 * 1000 },
		{ label: '6h', ms: 6 * 60 * 60 * 1000 },
		{ label: '24h', ms: 24 * 60 * 60 * 1000 },
		{ label: '7d', ms: 7 * 24 * 60 * 60 * 1000 },
	];

	const MIN_WINDOW_MS = 5 * 60 * 1000;
	const MAX_WINDOW_MS = 30 * 24 * 60 * 60 * 1000;

	$effect(() => {
		if (!containerEl) return;
		const ro = new ResizeObserver((entries) => {
			for (const entry of entries) {
				containerWidth = entry.contentRect.width;
			}
		});
		ro.observe(containerEl);
		return () => ro.disconnect();
	});

	function timeToX(time: Date): number {
		return ((time.getTime() - viewStart.getTime()) / (viewEnd.getTime() - viewStart.getTime())) * containerWidth;
	}

	function xToTime(x: number): Date {
		return new Date(viewStart.getTime() + (x / containerWidth) * (viewEnd.getTime() - viewStart.getTime()));
	}

	function formatTimeLabel(date: Date): string {
		return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
	}

	function formatTooltipTime(date: Date): string {
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ', ' +
			date.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
	}

	let parsedRanges = $derived(
		availabilityRanges.map(r => ({ start: new Date(r.start), end: new Date(r.end) }))
	);

	let rects = $derived(
		parsedRanges
			.filter(r => r.end.getTime() > viewStart.getTime() && r.start.getTime() < viewEnd.getTime())
			.map(r => {
				const x = Math.max(0, timeToX(r.start));
				const x2 = Math.min(containerWidth, timeToX(r.end));
				return { x, width: Math.max(1, x2 - x) };
			})
	);

	let playheadX = $derived(
		currentTime && currentTime.getTime() >= viewStart.getTime() && currentTime.getTime() <= viewEnd.getTime()
			? timeToX(currentTime)
			: null
	);

	let timeLabels = $derived.by(() => {
		const range = viewEnd.getTime() - viewStart.getTime();
		const count = range > 4 * 24 * 60 * 60 * 1000 ? 7 : range > 12 * 60 * 60 * 1000 ? 6 : 5;
		const step = range / count;
		return Array.from({ length: count + 1 }, (_, i) => {
			const t = new Date(viewStart.getTime() + step * i);
			return { time: t, x: timeToX(t), label: formatTimeLabel(t) };
		});
	});

	function handleWheel(e: WheelEvent) {
		e.preventDefault();
		const rect = containerEl!.getBoundingClientRect();
		const mouseX = e.clientX - rect.left;
		const mouseRatio = mouseX / containerWidth;
		const currentRange = viewEnd.getTime() - viewStart.getTime();

		const zoomFactor = e.deltaY > 0 ? 1.3 : 1 / 1.3;
		let newRange = currentRange * zoomFactor;
		newRange = Math.max(MIN_WINDOW_MS, Math.min(MAX_WINDOW_MS, newRange));

		const mouseTime = viewStart.getTime() + mouseRatio * currentRange;
		let newStart = mouseTime - mouseRatio * newRange;
		let newEnd = mouseTime + (1 - mouseRatio) * newRange;

		// Don't let the view extend past now
		const now = Date.now();
		if (newEnd > now) {
			newEnd = now;
			newStart = now - newRange;
		}

		viewStart = new Date(newStart);
		viewEnd = new Date(newEnd);
		activeZoom = '';
	}

	function handlePointerDown(e: PointerEvent) {
		isDragging = true;
		dragStartX = e.clientX;
		dragStartView = { start: viewStart.getTime(), end: viewEnd.getTime() };
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
	}

	function handlePointerMove(e: PointerEvent) {
		if (containerEl) {
			const rect = containerEl.getBoundingClientRect();
			hoverX = Math.max(0, Math.min(containerWidth, e.clientX - rect.left));
		}
		if (isDragging) {
			const msPerPx = (dragStartView.end - dragStartView.start) / containerWidth;
			const dx = dragStartX - e.clientX;
			viewStart = new Date(dragStartView.start + dx * msPerPx);
			viewEnd = new Date(dragStartView.end + dx * msPerPx);
		}
	}

	function handlePointerUp(e: PointerEvent) {
		const wasDragging = isDragging;
		isDragging = false;
		if (!wasDragging || Math.abs(e.clientX - dragStartX) < 5) {
			if (containerEl) {
				const rect = containerEl.getBoundingClientRect();
				const localX = e.clientX - rect.left;
				const clickedTime = xToTime(localX);

				if (e.shiftKey) {
					if (!selectionStart) {
						onSelectionChange?.(clickedTime, null);
					} else if (!selectionEnd) {
						let s = selectionStart;
						let end = clickedTime;
						if (end < s) [s, end] = [end, s];
						onSelectionChange?.(s, end);
					} else {
						onSelectionChange?.(null, null);
					}
					return;
				}

				if (selectionStart || selectionEnd) {
					onSelectionChange?.(null, null);
				}
				onSeek(clickedTime);
			}
		}
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (e.key === 'Escape' && (selectionStart || selectionEnd)) {
			onSelectionChange?.(null, null);
		}
	}

	function handleZoomPreset(preset: { label: string; ms: number }) {
		const now = Date.now();
		viewEnd = new Date(now);
		viewStart = new Date(now - preset.ms);
		activeZoom = preset.label;
	}

	function handleDateChange() {
		const target = new Date(selectedDate);
		if (isNaN(target.getTime())) return;
		const duration = viewEnd.getTime() - viewStart.getTime();
		viewStart = new Date(target.getTime() - duration / 2);
		viewEnd = new Date(target.getTime() + duration / 2);
	}
</script>

<div class="rounded-lg border border-gray-800 bg-gray-900 p-4 space-y-2">
	<!-- Timeline track -->
	<div
		bind:this={containerEl}
		class="relative h-12 w-full cursor-pointer rounded bg-gray-800 touch-none"
		onwheel={handleWheel}
		onpointerdown={handlePointerDown}
		onpointermove={handlePointerMove}
		onpointerup={handlePointerUp}
		onpointerleave={() => { hoverX = null; }}
		onkeydown={handleKeyDown}
		role="slider"
		aria-label="Recording timeline"
		tabindex="0"
	>
		{#each rects as rect}
			<div class="absolute top-0 h-full bg-green-500 rounded-sm"
				style="left: {rect.x}px; width: {rect.width}px;"></div>
		{/each}

		{#if selectionStart && selectionEnd}
			<div class="absolute top-0 h-full bg-blue-500/30 pointer-events-none"
				style="left: {Math.max(0, timeToX(selectionStart))}px; width: {Math.max(1, timeToX(selectionEnd) - timeToX(selectionStart))}px;">
			</div>
			<div class="absolute top-0 h-full w-0.5 bg-white cursor-col-resize"
				style="left: {timeToX(selectionStart)}px;"
				aria-label="Export start marker">
			</div>
			<div class="absolute top-0 h-full w-0.5 bg-white cursor-col-resize"
				style="left: {timeToX(selectionEnd)}px;"
				aria-label="Export end marker">
			</div>
		{:else if selectionStart}
			<div class="absolute top-0 h-full w-0.5 bg-white pointer-events-none"
				style="left: {timeToX(selectionStart)}px;">
			</div>
		{/if}

		{#if playheadX !== null}
			<div class="absolute top-0 h-full w-0.5 bg-white pointer-events-none"
				style="left: {playheadX}px;"></div>
		{/if}

		{#if selectionStart && selectionEnd}
			<div class="absolute -top-8 rounded bg-gray-900 px-2 py-1 text-xs text-white border border-gray-700 shadow-lg pointer-events-none whitespace-nowrap"
				style="left: {timeToX(selectionStart)}px; transform: translateX(-50%);">
				{formatTooltipTime(selectionStart)}
			</div>
			<div class="absolute -top-8 rounded bg-gray-900 px-2 py-1 text-xs text-white border border-gray-700 shadow-lg pointer-events-none whitespace-nowrap"
				style="left: {timeToX(selectionEnd)}px; transform: translateX(-50%);">
				{formatTooltipTime(selectionEnd)}
			</div>
		{/if}

		{#if hoverX !== null && !isDragging}
			<div class="absolute top-0 h-full w-px bg-gray-500 pointer-events-none"
				style="left: {hoverX}px;"></div>
			<div class="absolute -top-8 rounded bg-gray-900 px-2 py-1 text-xs text-gray-300 shadow-lg border border-gray-700 pointer-events-none whitespace-nowrap"
				style="left: {hoverX}px; transform: translateX(-50%);">
				{formatTooltipTime(xToTime(hoverX))}
			</div>
		{/if}
	</div>

	<!-- Time axis labels -->
	<div class="relative h-4">
		{#each timeLabels as label}
			<span class="absolute text-xs text-gray-500 -translate-x-1/2"
				style="left: {label.x}px;">{label.label}</span>
		{/each}
	</div>

	<!-- Navigation row: date picker + zoom presets -->
	<div class="flex items-center justify-between gap-4">
		<input
			type="datetime-local"
			bind:value={selectedDate}
			onchange={handleDateChange}
			class="rounded-lg border border-gray-700 bg-gray-800 px-4 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
		/>
		<div class="flex items-center gap-1">
			{#each zoomPresets as preset}
				<button
					onclick={() => handleZoomPreset(preset)}
					class="rounded-md px-2 py-1 text-xs {activeZoom === preset.label ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700'}"
				>
					{preset.label}
				</button>
			{/each}
		</div>
	</div>
</div>
