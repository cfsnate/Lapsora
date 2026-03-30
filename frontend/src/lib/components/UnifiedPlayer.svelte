<script lang="ts">
	import Hls from 'hls.js';

	interface Props {
		mode: 'live' | 'recording';
		wsUrl?: string;
		hlsSrc?: string;
		playbackRate?: number;
		onTimeUpdate?: (time: Date | null) => void;
		onError?: (msg: string) => void;
		onReady?: () => void;
	}

	let { mode, wsUrl, hlsSrc, playbackRate = 1, onTimeUpdate, onError, onReady }: Props = $props();

	let videoEl = $state<HTMLVideoElement | null>(null);
	let hlsInstance = $state<Hls | null>(null);
	let status = $state<'connecting' | 'loading' | 'ready' | 'playing' | 'error'>('loading');
	let errorMsg = $state('');

	function detachCurrentSource() {
		if (hlsInstance) {
			hlsInstance.destroy();
			hlsInstance = null;
		}
		if (videoEl) {
			videoEl.pause();
			videoEl.removeAttribute('src');
			videoEl.load();
		}
	}

	$effect(() => {
		if (!videoEl) return;

		detachCurrentSource();

		if (mode === 'live' && wsUrl) {
			status = 'connecting';
			errorMsg = '';

			const mediaSource = new MediaSource();
			const objectUrl = URL.createObjectURL(mediaSource);
			videoEl.src = objectUrl;

			let ws: WebSocket | null = null;
			let sourceBuffer: SourceBuffer | null = null;
			const queue: ArrayBuffer[] = [];
			let appending = false;
			let hasPlayed = false;

			function appendNext() {
				if (!sourceBuffer || appending || queue.length === 0) return;
				if (sourceBuffer.updating) return;
				appending = true;
				const chunk = queue.shift()!;
				try {
					sourceBuffer.appendBuffer(chunk);
				} catch {
					appending = false;
				}
			}

			mediaSource.addEventListener('sourceopen', () => {
				ws = new WebSocket(wsUrl!);
				ws.binaryType = 'arraybuffer';

				ws.onmessage = (event) => {
					if (typeof event.data === 'string') {
						try {
							const info = JSON.parse(event.data);
							const codecs = info.codecs || info.type;
							if (codecs && !sourceBuffer) {
								const mimeType = `video/mp4; codecs="${codecs}"`;
								if (MediaSource.isTypeSupported(mimeType)) {
									sourceBuffer = mediaSource.addSourceBuffer(mimeType);
									sourceBuffer.mode = 'segments';
									sourceBuffer.addEventListener('updateend', () => {
										appending = false;
										appendNext();
									});
								} else {
									status = 'error';
									errorMsg = `Unsupported codec: ${codecs}`;
									onError?.(`Unsupported codec: ${codecs}`);
								}
							}
						} catch {
							// Not JSON, ignore
						}
						return;
					}

					queue.push(event.data);
					appendNext();

					if (!hasPlayed && videoEl) {
						hasPlayed = true;
						videoEl.play().then(() => {
							status = 'playing';
							onReady?.();
						}).catch(() => {});
					}
				};

				ws.onerror = () => {
					status = 'error';
					errorMsg = 'WebSocket connection failed';
					onError?.('WebSocket connection failed');
				};

				ws.onclose = () => {
					if (status === 'connecting') {
						status = 'error';
						errorMsg = 'Connection closed';
					}
				};
			});

			return () => {
				ws?.close();
				URL.revokeObjectURL(objectUrl);
			};
		} else if (mode === 'recording' && hlsSrc) {
			status = 'loading';
			errorMsg = '';

			if (Hls.isSupported()) {
				const instance = new Hls({ maxBufferLength: 30, maxMaxBufferLength: 60 });
				instance.loadSource(hlsSrc);
				instance.attachMedia(videoEl);

				let retried = false;
				instance.on(Hls.Events.MANIFEST_PARSED, () => {
					status = 'ready';
					onReady?.();
				});
				instance.on(Hls.Events.ERROR, (_event, data) => {
					if (data.fatal) {
						if (data.type === Hls.ErrorTypes.NETWORK_ERROR && !retried) {
							retried = true;
							instance.startLoad();
							return;
						}
						status = 'error';
						errorMsg = data.details || 'HLS playback failed';
						onError?.(data.details || 'HLS playback failed');
					}
				});
				hlsInstance = instance;

				return () => {
					instance.destroy();
					hlsInstance = null;
				};
			} else if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {
				videoEl.src = hlsSrc;
				const el = videoEl;
				const onLoaded = () => { status = 'ready'; onReady?.(); };
				const onErr = () => { status = 'error'; errorMsg = 'Playback failed'; onError?.('Playback failed'); };
				el.addEventListener('loadedmetadata', onLoaded);
				el.addEventListener('error', onErr);

				return () => {
					el.removeEventListener('loadedmetadata', onLoaded);
					el.removeEventListener('error', onErr);
				};
			} else {
				status = 'error';
				errorMsg = 'HLS playback is not supported in this browser';
				onError?.('HLS playback is not supported in this browser');
			}
		}
	});

	$effect(() => {
		if (videoEl && mode === 'recording') {
			videoEl.playbackRate = playbackRate;
		}
	});
</script>

<div class="relative aspect-video w-full overflow-hidden rounded-lg bg-black">
	<!-- svelte-ignore a11y_media_has_caption -->
	<video
		bind:this={videoEl}
		autoplay
		muted
		playsinline
		class="h-full w-full object-contain"
		ontimeupdate={() => {
			if (onTimeUpdate && mode === 'recording') {
				onTimeUpdate(hlsInstance?.playingDate ?? null);
			}
		}}
		onplay={() => { status = 'playing'; }}
	></video>
	{#if status === 'connecting'}
		<div class="absolute inset-0 flex items-center justify-center">
			<p class="text-sm text-gray-400">Connecting to live stream...</p>
		</div>
	{:else if status === 'loading'}
		<div class="absolute inset-0 flex items-center justify-center bg-black/50">
			<svg class="h-8 w-8 animate-spin text-gray-400" viewBox="0 0 24 24" fill="none">
				<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25"></circle>
				<path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" class="opacity-75"></path>
			</svg>
		</div>
	{:else if status === 'error'}
		<div class="absolute inset-0 flex items-center justify-center">
			<p class="text-sm text-red-400">{errorMsg || 'Playback failed — try refreshing the page'}</p>
		</div>
	{/if}
</div>
