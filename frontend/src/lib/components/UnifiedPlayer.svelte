<script lang="ts">
	import Hls from 'hls.js';

	interface Props {
		mode: 'live' | 'recording';
		wsUrl?: string;
		hlsSrc?: string;
		playbackRate?: number;
		seekTo?: Date | null;
		onTimeUpdate?: (time: Date | null) => void;
		onError?: (msg: string) => void;
		onReady?: () => void;
	}

	let { mode, wsUrl, hlsSrc, playbackRate = 1, seekTo = null, onTimeUpdate, onError, onReady }: Props = $props();

	let videoEl = $state<HTMLVideoElement | null>(null);
	let hlsInstance: Hls | null = null;
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
			// go2rtc WebSocket MSE path
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
		} else if (hlsSrc) {
			// HLS path — used for recording playback AND live RTSP-via-FFmpeg
			status = 'loading';
			errorMsg = '';

			const isLiveHls = mode === 'live';

			if (Hls.isSupported()) {
				const instance = new Hls({
					// Live HLS: FFmpeg takes a few seconds to produce the first segment.
					// Retry patiently — the backend starts FFmpeg immediately but doesn't
					// wait for it before returning the URL.
					manifestLoadingMaxRetry: isLiveHls ? 20 : 2,
					manifestLoadingRetryDelay: isLiveHls ? 500 : 500,
					manifestLoadingMaxRetryTimeout: isLiveHls ? 2000 : 2000,
					levelLoadingMaxRetry: isLiveHls ? 10 : 2,
					levelLoadingRetryDelay: isLiveHls ? 500 : 500,
					// Progressive loading: start playing as bytes arrive rather than
					// waiting for the entire segment to download. Critical for large
					// segments (45-78MB for 300s of 4K).
					progressive: true,
					lowLatencyMode: isLiveHls,
					// Keep buffer modest — seek responsiveness matters more than
					// deep prebuffering for recorded playback
					maxBufferLength: isLiveHls ? 8 : 15,
					maxMaxBufferLength: isLiveHls ? 16 : 30,
					maxBufferSize: 60 * 1000 * 1000, // 60MB max buffer
					// For live, start from the live edge
					liveSyncDurationCount: 2,
					// Start playback before full segment is loaded
					startFragPrefetch: true,
				});
				instance.loadSource(hlsSrc);
				instance.attachMedia(videoEl);

				instance.on(Hls.Events.MANIFEST_PARSED, (_event, data) => {
					// An empty VOD playlist (no recordings in range) parses successfully
					// but has no levels/fragments. Surface this as a distinct state.
					if (!isLiveHls && data.levels.length === 0) {
						status = 'error';
						errorMsg = 'No recordings found in this time range';
						onError?.('No recordings found in this time range');
						return;
					}
					status = 'ready';
					onReady?.();

					// Seek to the requested time within the playlist.
					// HLS.js uses EXT-X-PROGRAM-DATE-TIME to map real-time → media time.
					if (seekTo && !isLiveHls && videoEl) {
						const details = instance.levels[0]?.details;
						if (details?.fragments?.length) {
							const seekMs = seekTo.getTime();
							// Find the fragment closest to the seek target
							for (const frag of details.fragments) {
								if (frag.programDateTime) {
									const fragStartMs = frag.programDateTime;
									const fragEndMs = fragStartMs + frag.duration * 1000;
									if (seekMs >= fragStartMs && seekMs < fragEndMs) {
										const offsetInFrag = (seekMs - fragStartMs) / 1000;
										videoEl.currentTime = frag.start + offsetInFrag;
										break;
									}
								}
							}
							// If seekTo is before all fragments, just start at the beginning
							// If after all fragments, seek to near the end
							if (videoEl.currentTime === 0 && details.fragments.length > 0) {
								const lastFrag = details.fragments[details.fragments.length - 1];
								if (lastFrag.programDateTime && seekMs > lastFrag.programDateTime) {
									videoEl.currentTime = lastFrag.start;
								}
							}
						}
					}
				});
				instance.on(Hls.Events.FRAG_LOADED, () => {
					// First fragment loaded — ensure playing state is set
					if (status === 'ready') {
						videoEl?.play().catch(() => {});
					}
				});
				instance.on(Hls.Events.ERROR, (_event, data) => {
					if (data.fatal) {
						if (isLiveHls && data.type === Hls.ErrorTypes.NETWORK_ERROR) {
							// During live startup the playlist may return 200 with no segments yet.
							// Recover by restarting the load rather than hard-failing.
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
			if (onTimeUpdate && (mode === 'recording' || (mode === 'live' && !wsUrl))) {
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
			<div class="flex flex-col items-center gap-3">
				<svg class="h-8 w-8 animate-spin text-gray-400" viewBox="0 0 24 24" fill="none">
					<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25"></circle>
					<path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" class="opacity-75"></path>
				</svg>
				{#if mode === 'live'}
					<p class="text-xs text-gray-500">Starting live stream…</p>
				{/if}
			</div>
		</div>
	{:else if status === 'error'}
		<div class="absolute inset-0 flex items-center justify-center">
			<p class="text-sm text-red-400">{errorMsg || 'Playback failed — try refreshing the page'}</p>
		</div>
	{/if}
</div>
