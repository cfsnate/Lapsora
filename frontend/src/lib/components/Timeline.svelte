<script lang="ts">
	interface Props {
		availabilityRanges: { start: string; end: string }[];
		currentTime: Date | null;
		onSeek: (time: Date) => void;
		selectionStart?: Date | null;
		selectionEnd?: Date | null;
		clipMode?: boolean;
		onSelectionChange?: (start: Date | null, end: Date | null) => void;
	}

	let { availabilityRanges, currentTime, onSeek, selectionStart = null, selectionEnd = null, clipMode = false, onSelectionChange }: Props = $props();

	let containerEl = $state<HTMLDivElement | null>(null);
	let containerWidth = $state(0);
	let viewStart = $state<Date>(new Date(Date.now() - 60 * 60 * 1000));
	let viewEnd = $state<Date>(new Date());
	let hoverX = $state<number | null>(null);
	let isDragging = $state(false);
	let dragStartX = $state(0);
	let dragStartView = $state<{ start: number; end: number }>({ start: 0, end: 0 });
	let activeZoom = $state('1h');
	let hasAutoFit = $state(false);
	function toLocalISOString(d: Date): string {
		const pad = (n: number) => String(n).padStart(2, '0');
		return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
	}

	let selectedDate = $state(toLocalISOString(new Date()));

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

	// Auto-fit view to recording data on first load
	$effect(() => {
		if (hasAutoFit || availabilityRanges.length === 0) return;
		hasAutoFit = true;

		// Find the most recent recording end time
		let latestEnd = 0;
		let earliestStart = Infinity;
		for (const r of availabilityRanges) {
			const s = new Date(r.start).getTime();
			const e = new Date(r.end).getTime();
			if (e > latestEnd) latestEnd = e;
			if (s < earliestStart) earliestStart = s;
		}

		const totalSpan = latestEnd - earliestStart;
		const now = Date.now();

		if (totalSpan <= 6 * 60 * 60 * 1000) {
			// Less than 6 hours of recordings: show a 6h window centered on the data
			const center = (earliestStart + latestEnd) / 2;
			const windowMs = 6 * 60 * 60 * 1000;
			viewEnd = new Date(Math.min(now, center + windowMs / 2));
			viewStart = new Date(viewEnd.getTime() - windowMs);
			activeZoom = '6h';
		} else if (totalSpan <= 24 * 60 * 60 * 1000) {
			// Show 24h window ending at now (or latest recording)
			viewEnd = new Date(Math.min(now, latestEnd + 30 * 60 * 1000));
			viewStart = new Date(viewEnd.getTime() - 24 * 60 * 60 * 1000);
			activeZoom = '24h';
		} else {
			// More than a day: show the full span with 10% padding
			const pad = totalSpan * 0.1;
			viewStart = new Date(earliestStart - pad);
			viewEnd = new Date(Math.min(now, latestEnd + pad));
			activeZoom = '';
		}
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
		containerWidth <= 0 ? [] :
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
		if (containerWidth <= 0) return [];
		const range = viewEnd.getTime() - viewStart.getTime();
		const isMultiDay = range > 24 * 60 * 60 * 1000;
		// Adjust label count based on container width to prevent overlap
		const minLabelSpacing = isMultiDay ? 100 : 70;
		const maxLabels = Math.max(2, Math.floor(containerWidth / minLabelSpacing));
		const count = Math.min(maxLabels, range > 4 * 24 * 60 * 60 * 1000 ? 7 : range > 12 * 60 * 60 * 1000 ? 6 : 5);
		const step = range / count;
		return Array.from({ length: count + 1 }, (_, i) => {
			const t = new Date(viewStart.getTime() + step * i);
			const label = isMultiDay
				? t.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' + t.toLocaleTimeString('en-US', { hour: 'numeric', hour12: true })
				: formatTimeLabel(t);
			return { time: t, x: timeToX(t), label };
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

				// In clip mode (or with Shift held), clicks set selection points
				if (clipMode || e.shiftKey) {
					if (!selectionStart) {
						onSelectionChange?.(clickedTime, null);
					} else if (!selectionEnd) {
						let s = selectionStart;
						let end = clickedTime;
						if (end < s) [s, end] = [end, s];
						onSelectionChange?.(s, end);
					} else {
						// Reset and start new selection
						onSelectionChange?.(clickedTime, null);
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
		class="relative h-12 w-full rounded bg-gray-800 touch-none {clipMode ? 'cursor-crosshair' : 'cursor-pointer'}"
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
			<div class="absolute top-0 h-full bg-green-500/80 rounded-sm"
				style="left: {Math.round(rect.x)}px; width: {Math.round(rect.width)}px;"></div>
		{/each}

		{#if selectionStart && selectionEnd}
			<div class="absolute top-0 h-full bg-blue-500/30 pointer-events-none"
				style="transform: translateX({Math.max(0, timeToX(selectionStart))}px); width: {Math.max(1, timeToX(selectionEnd) - timeToX(selectionStart))}px;">
			</div>
			<div class="absolute top-0 h-full w-0.5 bg-white cursor-col-resize"
				style="transform: translateX({timeToX(selectionStart)}px);"
				aria-label="Export start marker">
			</div>
			<div class="absolute top-0 h-full w-0.5 bg-white cursor-col-resize"
				style="transform: translateX({timeToX(selectionEnd)}px);"
				aria-label="Export end marker">
			</div>
		{:else if selectionStart}
			<div class="absolute top-0 h-full w-0.5 bg-white pointer-events-none"
				style="transform: translateX({timeToX(selectionStart)}px);">
			</div>
		{/if}

		{#if playheadX !== null}
			<div class="absolute top-0 h-full w-0.5 bg-red-400 pointer-events-none"
				style="left: {Math.round(playheadX)}px;"></div>
		{/if}

		{#if selectionStart && selectionEnd}
			<div class="absolute -top-8 rounded bg-gray-900 px-2 py-1 text-xs text-white border border-gray-700 shadow-lg pointer-events-none whitespace-nowrap"
				style="transform: translateX(calc({timeToX(selectionStart)}px - 50%));">
				{formatTooltipTime(selectionStart)}
			</div>
			<div class="absolute -top-8 rounded bg-gray-900 px-2 py-1 text-xs text-white border border-gray-700 shadow-lg pointer-events-none whitespace-nowrap"
				style="transform: translateX(calc({timeToX(selectionEnd)}px - 50%));">
				{formatTooltipTime(selectionEnd)}
			</div>
		{/if}

		{#if hoverX !== null && !isDragging}
			<div class="absolute top-0 h-full w-px bg-gray-500 pointer-events-none"
				style="transform: translateX({hoverX}px);"></div>
			<div class="absolute -top-8 rounded bg-gray-900 px-2 py-1 text-xs text-gray-300 shadow-lg border border-gray-700 pointer-events-none whitespace-nowrap"
				style="transform: translateX(calc({hoverX}px - 50%));">
				{formatTooltipTime(xToTime(hoverX))}
			</div>
		{/if}
	</div>

	<!-- Time axis labels -->
	<div class="relative h-4 overflow-hidden">
		{#each timeLabels as label, i}
			<span class="absolute text-xs text-gray-500 whitespace-nowrap"
				style="left: {Math.max(0, Math.min(containerWidth - 40, label.x))}px; transform: translateX({i === 0 ? '0%' : i === timeLabels.length - 1 ? '-100%' : '-50%'});">{label.label}</span>
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
