<script lang="ts">
	import '../app.css';
	import type { Snippet } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import type { Notification, AuthUser } from '$lib/types';
	import { setUse24h } from '$lib/utils';
	import NotificationBell from '$lib/components/NotificationBell.svelte';
	import NotificationToast from '$lib/components/NotificationToast.svelte';

	let { children }: { children: Snippet } = $props();

	let notifications = $state<Notification[]>([]);
	let toasts = $state<{ id: number; title: string; body: string; level: string }[]>([]);
	let toastCounter = $state(0);
	let setupChecked = $state(false);
	let setupRequired = $state(false);
	let authChecked = $state(false);
	let authUser = $state<AuthUser | null>(null);

	const navItems = [
		{ href: '/', label: 'Dashboard', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1' },
		{ href: '/streams', label: 'Streams', icon: 'M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z' },
		{ href: '/playback', label: 'Playback', icon: 'M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
		{ href: '/profiles', label: 'Templates', icon: 'M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4' },
		{ href: '/timelapses', label: 'Timelapses', icon: 'M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z' },
		{ href: '/exports', label: 'Exports', icon: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4' },
		{ href: '/files', label: 'Files', icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z' },
		{ href: '/statistics', label: 'Statistics', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
		{ href: '/settings', label: 'Settings', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' }
	];

	function loadNotifications() {
		api.getNotifications({ limit: 30 }).then((n) => {
			notifications = n;
		}).catch(() => {});
	}

	function dismissToast(id: number) {
		toasts = toasts.filter((t) => t.id !== id);
	}

	async function handleLogout() {
		try {
			await api.logout();
		} catch {}
		authUser = null;
		goto('/login');
	}

	// Load notifications, time format, and check setup status once on mount
	$effect(() => {
		const currentPath = $page.url.pathname;

		api.getSetupStatus().then((status) => {
			setupRequired = status.setup_required;
			setupChecked = true;
			if (status.setup_required && (currentPath as string) !== '/setup') {
				goto('/setup' as string);
			} else if (!status.setup_required && (currentPath as string) === '/setup') {
				goto('/');
			} else if (!status.setup_required) {
				// Setup is done — check auth
				api.getMe().then((user) => {
					authUser = user;
					authChecked = true;
					if ((currentPath as string) === '/login') {
						goto('/');
					}
				}).catch(() => {
					authChecked = true;
					if ((currentPath as string) !== '/login') {
						goto('/login');
					}
				});
			}
		}).catch(() => {
			// If setup-status fetch fails, allow the app to proceed normally
			setupChecked = true;
			authChecked = true;
		});

		loadNotifications();
		api.getTimeFormatConfig().then((cfg) => {
			setUse24h(cfg.use_24h);
		}).catch(() => {});
	});

	// SSE connection - separate effect so notification changes don't trigger reconnection
	$effect(() => {
		const es = new EventSource(api.getNotificationStreamUrl());
		es.addEventListener('notification', (e) => {
			try {
				const data = JSON.parse(e.data);

				// Transient events — dispatch to page handlers but don't persist or toast
				const transientEvents = ['timelapse_progress', 'timelapse_queued', 'timelapse_queue_updated', 'timelapse_cancelled', 'recording_status'];
				if (transientEvents.includes(data.event_type)) {
					window.dispatchEvent(new CustomEvent('lapsora:notification', { detail: data }));
					return;
				}

				const notif: Notification = {
					id: data.id,
					event_type: data.event_type,
					title: data.title,
					body: data.body,
					level: data.level,
					read: false,
					created_at: data.created_at
				};
				notifications = [notif, ...notifications.slice(0, 29)];

				const tid = ++toastCounter;
				toasts = [...toasts, { id: tid, title: data.title, body: data.body, level: data.level }];
				setTimeout(() => {
					toasts = toasts.filter((t) => t.id !== tid);
				}, 5000);

				window.dispatchEvent(new CustomEvent('lapsora:notification', { detail: data }));
			} catch {}
		});

		return () => es.close();
	});
</script>

{#if !setupChecked}
	<!-- Blank screen while checking setup status — prevents nav flash before redirect -->
	<div class="flex h-screen items-center justify-center bg-gray-950"></div>
{:else if setupRequired}
	<!-- Setup wizard — render without nav shell -->
	{@render children()}
{:else if !authChecked}
	<!-- Blank screen while checking auth — prevents nav flash before redirect -->
	<div class="flex h-screen items-center justify-center bg-gray-950"></div>
{:else if !authUser}
	<!-- Login page — render without nav shell -->
	{@render children()}
{:else}
	<div class="flex h-screen bg-gray-950 text-gray-100">
		<aside class="fixed left-0 top-0 z-50 flex h-full w-56 flex-col border-r border-gray-800 bg-gray-900">
			<div class="flex h-14 items-center justify-between border-b border-gray-800 px-4">
				<h1 class="text-lg font-bold tracking-tight text-white">Lapsora</h1>
				<NotificationBell {notifications} onRefresh={loadNotifications} />
			</div>
			<nav class="flex-1 space-y-1 overflow-y-auto p-3">
				{#each navItems as item}
					<a
						href={item.href}
						class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors {
							$page.url.pathname === item.href || (item.href !== '/' && $page.url.pathname.startsWith(item.href))
								? 'bg-gray-800 text-white font-medium'
								: 'text-gray-400 hover:bg-gray-800 hover:text-white'
						}"
					>
						<svg class="h-5 w-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d={item.icon} />
						</svg>
						{item.label}
					</a>
				{/each}
				{#if authUser?.role === 'admin'}
					<a
						href="/admin/users"
						class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors {
							($page.url.pathname as string) === '/admin/users'
								? 'bg-gray-800 text-white font-medium'
								: 'text-gray-400 hover:bg-gray-800 hover:text-white'
						}"
					>
						<svg class="h-5 w-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
						</svg>
						Users
					</a>
					<a
						href="/admin/groups"
						class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors {
							($page.url.pathname as string) === '/admin/groups'
								? 'bg-gray-800 text-white font-medium'
								: 'text-gray-400 hover:bg-gray-800 hover:text-white'
						}"
					>
						<svg class="h-5 w-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
						</svg>
						Groups
					</a>
					<a
						href="/admin/console"
						class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors {
							($page.url.pathname as string) === '/admin/console'
								? 'bg-gray-800 text-white font-medium'
								: 'text-gray-400 hover:bg-gray-800 hover:text-white'
						}"
					>
						<svg class="h-5 w-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z" />
						</svg>
						Console
					</a>
				{/if}
			</nav>
			<div class="border-t border-gray-800 p-3">
				<a
					href="/account"
					class="mb-2 flex items-center gap-2 truncate rounded-lg px-3 py-1 text-sm font-medium text-gray-300 transition-colors hover:bg-gray-800 hover:text-white"
				>
					<svg class="h-4 w-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
					</svg>
					<span class="truncate">{authUser?.display_name ?? authUser?.username ?? ''}</span>
				</a>
				<button
					onclick={handleLogout}
					class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-gray-400 transition-colors hover:bg-gray-800 hover:text-white"
				>
					<svg class="h-5 w-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
					</svg>
					Logout
				</button>
			</div>
		</aside>

		<main class="ml-56 flex-1 overflow-auto p-6">
			{@render children()}
		</main>
	</div>

	<NotificationToast {toasts} onDismiss={dismissToast} />
{/if}

