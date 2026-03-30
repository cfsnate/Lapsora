<script lang="ts">
	import { api } from '$lib/api';

	interface Props {
		open: boolean;
		profileId: number;
		startTime: Date;
		endTime: Date;
		onclose: () => void;
		onsubmit: (exportId: number) => void;
	}

	let { open, profileId, startTime, endTime, onclose, onsubmit }: Props = $props();

	let startStr = $state('');
	let endStr = $state('');
	let qualityPreset = $state('original');
	let resolution = $state('original');
	let submitting = $state(false);
	let error = $state<string | null>(null);

	function toDatetimeLocal(d: Date): string {
		const pad = (n: number) => String(n).padStart(2, '0');
		return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
	}

	$effect(() => {
		if (open) {
			startStr = toDatetimeLocal(startTime);
			endStr = toDatetimeLocal(endTime);
			qualityPreset = 'original';
			resolution = 'original';
			error = null;
			submitting = false;
		}
	});

	let durationDisplay = $derived.by(() => {
		const s = new Date(startStr);
		const e = new Date(endStr);
		if (isNaN(s.getTime()) || isNaN(e.getTime()) || e <= s) return '';
		const diffMs = e.getTime() - s.getTime();
		const mins = Math.floor(diffMs / 60000);
		const secs = Math.floor((diffMs % 60000) / 1000);
		return `${mins}m ${secs}s`;
	});

	function handleQualityChange() {
		if (qualityPreset === 'original') {
			resolution = 'original';
		}
	}

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		submitting = true;
		error = null;
		try {
			const result = await api.createExport({
				profile_id: profileId,
				start_time: new Date(startStr).toISOString(),
				end_time: new Date(endStr).toISOString(),
				quality_preset: qualityPreset,
				resolution: qualityPreset === 'original' ? 'original' : resolution,
			});
			onsubmit(result.id);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Export failed';
		} finally {
			submitting = false;
		}
	}

	function handleBackdrop(e: MouseEvent) {
		if (e.target === e.currentTarget) onclose();
	}
</script>

{#if open}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
		onclick={handleBackdrop}
		onkeydown={() => {}}
	>
		<div class="w-full max-w-md rounded-lg bg-gray-800 p-6">
			<h2 class="mb-4 text-lg font-bold text-gray-100">Export Clip</h2>

			{#if error}
				<p class="mb-3 rounded-md bg-red-900/50 px-3 py-2 text-sm text-red-300">{error}</p>
			{/if}

			<form onsubmit={handleSubmit} class="space-y-4">
				<div>
					<label for="export-start" class="block text-sm text-gray-300 mb-1">Start Time</label>
					<input
						id="export-start"
						type="datetime-local"
						bind:value={startStr}
						class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					/>
				</div>

				<div>
					<label for="export-end" class="block text-sm text-gray-300 mb-1">End Time</label>
					<input
						id="export-end"
						type="datetime-local"
						bind:value={endStr}
						class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					/>
					{#if durationDisplay}
						<p class="text-xs text-gray-400 mt-1">Duration: {durationDisplay}</p>
					{/if}
				</div>

				<div>
					<label for="export-quality" class="block text-sm text-gray-300 mb-1">Quality Preset</label>
					<select
						id="export-quality"
						bind:value={qualityPreset}
						onchange={handleQualityChange}
						class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
					>
						<option value="original">Original</option>
						<option value="high">High</option>
						<option value="medium">Medium</option>
						<option value="low">Low</option>
					</select>
					{#if qualityPreset === 'original'}
						<p class="text-xs text-gray-500 mt-1">Copies the stream directly — start and end may shift ~1-2s to the nearest keyframe.</p>
					{/if}
				</div>

				{#if qualityPreset !== 'original'}
					<div>
						<label for="export-resolution" class="block text-sm text-gray-300 mb-1">Resolution</label>
						<select
							id="export-resolution"
							bind:value={resolution}
							class="w-full rounded-md border border-gray-600 bg-gray-900 px-3 py-2 text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
						>
							<option value="original">Original</option>
							<option value="1080p">1080p</option>
							<option value="720p">720p</option>
							<option value="480p">480p</option>
						</select>
					</div>
				{/if}

				<div class="flex gap-3 mt-6">
					<button
						type="button"
						onclick={onclose}
						disabled={submitting}
						class="flex-1 rounded-md bg-gray-700 px-4 py-2 font-bold text-gray-300 hover:bg-gray-600"
					>
						Cancel
					</button>
					<button
						type="submit"
						disabled={submitting}
						class="flex-1 rounded-md bg-blue-600 px-4 py-2 font-bold text-white hover:bg-blue-700 disabled:opacity-50"
					>
						{submitting ? 'Exporting...' : 'Export Clip'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
