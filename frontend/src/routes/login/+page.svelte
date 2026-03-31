<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';

	let username = $state('');
	let password = $state('');
	let submitting = $state(false);
	let error = $state('');

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		submitting = true;
		try {
			await api.login({ username: username.trim(), password });
			await goto('/');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Login failed. Please try again.';
		} finally {
			submitting = false;
		}
	}
</script>

<div class="flex min-h-screen items-center justify-center bg-gray-950 p-4">
	<div class="w-full max-w-sm">
		<div class="mb-8 text-center">
			<h1 class="text-3xl font-bold tracking-tight text-white">Lapsora</h1>
			<p class="mt-2 text-gray-400">Sign in to continue.</p>
		</div>

		<div class="rounded-xl border border-gray-800 bg-gray-900 p-8 shadow-xl">
			<h2 class="mb-6 text-lg font-semibold text-white">Sign In</h2>

			{#if error}
				<div class="mb-4 rounded-lg border border-red-800 bg-red-900/30 px-4 py-3 text-sm text-red-300">
					{error}
				</div>
			{/if}

			<form onsubmit={handleSubmit} class="space-y-5">
				<div>
					<label for="username" class="mb-1.5 block text-sm font-medium text-gray-300">
						Username
					</label>
					<input
						id="username"
						type="text"
						bind:value={username}
						autocomplete="username"
						class="w-full rounded-lg border border-gray-700 px-3 py-2 text-sm bg-gray-800 text-white placeholder-gray-500 outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
						placeholder="admin"
					/>
				</div>

				<div>
					<label for="password" class="mb-1.5 block text-sm font-medium text-gray-300">
						Password
					</label>
					<input
						id="password"
						type="password"
						bind:value={password}
						autocomplete="current-password"
						class="w-full rounded-lg border border-gray-700 px-3 py-2 text-sm bg-gray-800 text-white placeholder-gray-500 outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
						placeholder="Your password"
					/>
				</div>

				<button
					type="submit"
					disabled={submitting}
					class="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus:ring-2 focus:ring-blue-500"
				>
					{submitting ? 'Signing in…' : 'Sign In'}
				</button>
			</form>
		</div>
	</div>
</div>
